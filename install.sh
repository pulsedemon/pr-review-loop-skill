#!/usr/bin/env bash
# install.sh: install this skill for Cursor, Claude Code, Codex, and opencode.
#
# A bare run installs only into detected hosts: an existing config dir at
# ~/.cursor, ~/.claude, ${CODEX_HOME:-~/.codex}, or
# ${XDG_CONFIG_HOME:-~/.config}/opencode. An explicit host flag forces that
# host regardless of detection; --force alone skips detection and (re)installs
# into all four. A per-host failure (foreign file or foreign symlink at a
# target, or a failed mkdir, copy, removal, link, or marker write) warns and
# lets the remaining hosts proceed; the script exits non-zero if any host
# failed. Foreign or stale links at the Claude, Codex, and opencode targets are
# replaced only under --force, the recovery path after the checkout moves;
# Cursor refuses foreign links with or without --force and wants manual
# removal. --uninstall never removes a link it did not make.
#
# opencode also gets the three tier agents (hosts/opencode/agent/prl-*.md)
# symlinked into its agent dir, so task dispatch by subagent_type resolves
# them. opencode reads config, skills, and agents once at startup, so restart
# it after install or skill edits.
#
# Cursor: hardlinked tree under ~/.cursor/skills/ (Cursor does not discover
# symlinked skill dirs, see https://forum.cursor.com/t/151014). Claude/Codex/opencode: symlink.
# The Cursor tree omits .git (and other dev-only paths) so git metadata is not shared.
# .worktrees is skipped too: a git worktree is gitignored local state that can
# dwarf the skill itself, and cp -al would link every file in it.
#
# Re-running install.sh refreshes the Cursor tree automatically: it compares
# the installed tree against the source (paths + per-file content) and rebuilds
# when anything diverged, e.g. a `git pull` that replaced files and broke their
# hardlinks. Pass --force to rebuild unconditionally.
#
# Usage:
#   ./install.sh                    # install into all detected hosts
#   ./install.sh --cursor           # only Cursor
#   ./install.sh --claude           # only Claude Code
#   ./install.sh --codex            # only Codex
#   ./install.sh --opencode         # only opencode (skill + tier agents)
#   ./install.sh --force            # no host flag: (re)install all hosts, skipping detection (alias: --reinstall)
#   ./install.sh --uninstall        # remove installs (all hosts, always)

set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SKILL_NAME="pr-review-loop"

CURSOR_TARGET="${HOME}/.cursor/skills/${SKILL_NAME}"
CURSOR_MARKER="${CURSOR_TARGET}/.pr-review-loop-source"
CLAUDE_TARGET="${HOME}/.claude/skills/${SKILL_NAME}"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
CODEX_TARGET="${CODEX_HOME}/skills/${SKILL_NAME}"
CODEX_SHARED_TARGET="${HOME}/.agents/skills/${SKILL_NAME}"
# One expression feeds both detection and install paths so they cannot diverge.
OPENCODE_CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/opencode"
OPENCODE_TARGET="${OPENCODE_CONFIG_DIR}/skills/${SKILL_NAME}"
OPENCODE_AGENT_DIR="${OPENCODE_CONFIG_DIR}/agent"
OPENCODE_AGENT_SRC_DIR="${SOURCE_DIR}/hosts/opencode/agent"
OPENCODE_AGENTS=(prl-cheap.md prl-standard.md prl-strong.md)

# Repo-root-anchored paths excluded from the Cursor install. Only content
# specific to this install: the dev-only trees live in the manifest below.
CURSOR_INSTALL_SKIP=(
  docs/superpowers
  tools/recall-harness/corpus
  tools/recall-harness/unmatched
  tools/recall-harness/matched
  tools/recall-harness/loop_unmatched
  tools/recall-harness/REPORT.md
)

# Basenames excluded at any depth, so a nested copy is caught too (__pycache__
# alone lands in four places). Generated from manifests/dev-trees.yaml.
# [[[cog: dev_trees_install ]]]
CURSOR_INSTALL_SKIP_NAMES=(.git .venv .pytest_cache .ruff_cache .worktrees worktrees __pycache__ .DS_Store .claude .superpowers)
# [[[end]]]

WANT_CURSOR=1
WANT_CLAUDE=1
WANT_CODEX=1
WANT_OPENCODE=1
UNINSTALL=0
FORCE=0

# Host flags narrow the install to the named hosts; --force/--reinstall and
# --uninstall are modifiers that must not narrow it. Track whether a host was
# explicitly selected so a bare `--force` still installs into every host.
HOSTS_SPECIFIED=0
select_host() {
  if ((HOSTS_SPECIFIED == 0)); then
    WANT_CURSOR=0
    WANT_CLAUDE=0
    WANT_CODEX=0
    WANT_OPENCODE=0
    HOSTS_SPECIFIED=1
  fi
}

for arg in "$@"; do
  case "$arg" in
    --cursor)
      select_host
      WANT_CURSOR=1
      ;;
    --claude)
      select_host
      WANT_CLAUDE=1
      ;;
    --codex)
      select_host
      WANT_CODEX=1
      ;;
    --opencode)
      select_host
      WANT_OPENCODE=1
      ;;
    --force | --reinstall) FORCE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

# --uninstall always targets every host: a host flag selects what to *install*,
# never a subset to uninstall. Re-enable all hosts after parsing so order and
# any preceding host flag don't narrow the removal.
if ((UNINSTALL)); then
  WANT_CURSOR=1
  WANT_CLAUDE=1
  WANT_CODEX=1
  WANT_OPENCODE=1
fi

# Bare runs install into detected hosts only. An explicit host flag already
# forces that host, and --force alone (no host flag) means "every host,
# detection be damned", neither consults the predicates below.
if ((UNINSTALL == 0)) && ((HOSTS_SPECIFIED == 0)) && ((FORCE == 0)); then
  WANT_CURSOR=0
  WANT_CLAUDE=0
  WANT_CODEX=0
  WANT_OPENCODE=0
  if [[ -d "${HOME}/.cursor" ]]; then
    WANT_CURSOR=1
  fi
  if [[ -d "${HOME}/.claude" ]]; then
    WANT_CLAUDE=1
  fi
  if [[ -d "${CODEX_HOME}" ]]; then
    WANT_CODEX=1
  fi
  if [[ -d "${OPENCODE_CONFIG_DIR}" ]]; then
    WANT_OPENCODE=1
  fi
  if ((WANT_CURSOR == 0 && WANT_CLAUDE == 0 && WANT_CODEX == 0 && WANT_OPENCODE == 0)); then
    {
      echo "no supported hosts detected; probed:"
      echo "  ${HOME}/.cursor"
      echo "  ${HOME}/.claude"
      echo "  ${CODEX_HOME}"
      echo "  ${OPENCODE_CONFIG_DIR}"
      echo "pass --cursor, --claude, --codex, or --opencode to install regardless of detection"
    } >&2
    exit 0
  fi
fi

# Top-level entries cp -al must never descend into. The prune pass would
# delete them afterwards anyway, but linking a 46MB .venv only to remove it
# put ~3s back on every install.
cursor_should_skip_entry() {
  local name="$1"
  local skip
  for skip in "${CURSOR_INSTALL_SKIP[@]}" "${CURSOR_INSTALL_SKIP_NAMES[@]}"; do
    if [[ "$name" == "$skip" ]]; then
      return 0
    fi
  done
  return 1
}

# GNU stat uses -c; BSD uses -f. Try -c first so Linux never treats -f as filesystem metadata.
inode_of() {
  local path="$1"
  stat -c '%i' "$path" 2>/dev/null || stat -f '%i' "$path"
}

# Device:inode pair, a filesystem-wide unique file identity. Inode numbers
# alone repeat across filesystems, so a cross-device copy could coincidentally
# match the source inode; pairing the device id avoids that false match.
#
# Resolved once rather than probed per call: GNU takes -c and prints the bare
# path as %n, BSD takes -f and prints it as %N. The two are not interchangeable.
# GNU's %N quotes the name and expands symlinks, and GNU's -f is
# --file-system, which would swallow the format string as a filename and still
# exit 0, so a try-then-fallback would fail silently on Linux.
#
# Probe the format itself rather than --version: a non-GNU stat that implements
# the -c interface without --version (busybox, toybox) would otherwise be
# treated as BSD and produce filesystem output or nothing at all.
if stat -c '%n:%d:%i' "$SOURCE_DIR" >/dev/null 2>&1; then
  STAT_ID_ARGS=(-c '%n:%d:%i')
else
  STAT_ID_ARGS=(-f '%N:%d:%i')
fi

# Sorted "path:dev:inode" lines for each newline-separated path in $rels. Runs
# from $dir so the emitted path matches the relative one the caller passed in.
# A path stat cannot resolve simply has no line, so it survives the comm as a
# difference and falls through to a content compare.
#
# `--` terminates option parsing: a tracked file named `--version` would
# otherwise be read as a stat flag and could suppress or forge id records.
file_ids_in() {
  local dir="$1" rels="$2"
  (cd "$dir" && printf '%s\n' "$rels" | tr '\n' '\0' |
    xargs -0 stat "${STAT_ID_ARGS[@]}" -- 2>/dev/null) | LC_ALL=C sort
}

canonical_dir() {
  (cd "$1" && pwd -P)
}

# True when $1 is this checkout itself, not a link to it. A clone living at a
# host's skill path is already the install: Cursor's legacy inode check would
# match its SKILL.md against itself and rm -rf the checkout.
target_is_source() {
  [[ ! -L "$1" && -d "$1" ]] && [[ "$(canonical_dir "$1")" == "$SOURCE_DIR" ]]
}

symlink_points_to_source() {
  local link_path="$1"
  local current resolved
  current="$(readlink "$link_path")"
  [[ "$current" == "$SOURCE_DIR" ]] && return 0
  if [[ "$current" != /* ]]; then
    current="$(dirname "$link_path")/$current"
  fi
  if [[ -d "$current" ]]; then
    resolved="$(canonical_dir "$current")"
  else
    return 1
  fi
  [[ "$resolved" == "$SOURCE_DIR" ]]
}

cursor_write_marker() {
  printf '%s\n' "$SOURCE_DIR" >"$CURSOR_MARKER"
}

cursor_is_our_install() {
  if [[ -f "$CURSOR_MARKER" ]] && [[ "$(<"$CURSOR_MARKER")" == "$SOURCE_DIR" ]]; then
    return 0
  fi
  # Legacy hardlink install (pre-marker): same inode as source SKILL.md.
  if [[ -f "${CURSOR_TARGET}/SKILL.md" && -f "${SOURCE_DIR}/SKILL.md" ]]; then
    [[ "$(inode_of "${CURSOR_TARGET}/SKILL.md")" == "$(inode_of "${SOURCE_DIR}/SKILL.md")" ]]
    return
  fi
  return 1
}

cursor_needs_upgrade() {
  [[ -e "${CURSOR_TARGET}/.git" ]]
}

# A tree built before an entry joined CURSOR_INSTALL_SKIP still holds that entry.
# cursor_tree_files prunes it from the source and target lists alike, so the
# path-set comparison cannot see the difference and the install would report
# "already installed" forever.
cursor_tree_has_excluded_paths() {
  local skip
  for skip in "${CURSOR_INSTALL_SKIP[@]}"; do
    [[ -e "${CURSOR_TARGET}/${skip}" || -L "${CURSOR_TARGET}/${skip}" ]] && return 0
  done
  # Anchored paths are a cheap existence test, but an any-depth basename needs
  # a walk. -quit stops at the first hit, so a clean tree barely pays for it.
  cursor_prune_expr
  [[ -n "$(cd "$CURSOR_TARGET" && find . "${CURSOR_PRUNE_EXPR[@]}" -print -quit)" ]]
}

# find expression shared by the installer's prune pass and cursor_tree_files, so
# the two cannot disagree about what belongs in the tree. An out-variable rather
# than command substitution: a string round-trip would destroy argv word
# boundaries for paths containing spaces.
cursor_prune_expr() {
  local first=1 skip
  CURSOR_PRUNE_EXPR=('(')
  for skip in "${CURSOR_INSTALL_SKIP[@]}"; do
    ((first)) && first=0 || CURSOR_PRUNE_EXPR+=(-o)
    CURSOR_PRUNE_EXPR+=(-path "./$skip")
  done
  for skip in "${CURSOR_INSTALL_SKIP_NAMES[@]}"; do
    ((first)) && first=0 || CURSOR_PRUNE_EXPR+=(-o)
    CURSOR_PRUNE_EXPR+=(-name "$skip")
  done
  # Callers that need an extra term append it before closing the group: the
  # parens bound what -prune applies to, so a term added after them would be
  # ORed against the whole match instead and stop filtering.
  for skip in "$@"; do
    CURSOR_PRUNE_EXPR+=(-o -name "$skip")
  done
  CURSOR_PRUNE_EXPR+=(')')
}

# Sorted recursive relative file list under $dir, applying the installer's skip
# rules and omitting the source marker. Used to detect divergence between
# source and install.
cursor_tree_files() {
  local dir="$1"
  cursor_prune_expr .pr-review-loop-source
  (cd "$dir" && find . "${CURSOR_PRUNE_EXPR[@]}" -prune -o -type f -print) | LC_ALL=C sort
}

cursor_tree_needs_refresh() {
  cursor_needs_upgrade && return 0
  [[ -d "$CURSOR_TARGET" ]] || return 0
  cursor_tree_has_excluded_paths && return 0

  local src_files tgt_files
  src_files="$(cursor_tree_files "$SOURCE_DIR")"
  tgt_files="$(cursor_tree_files "$CURSOR_TARGET")"
  # Added/removed paths (including nested ones) always force a refresh.
  [[ "$src_files" != "$tgt_files" ]] && return 0

  # Same path set: refresh if any file's content diverged from source. An
  # intact hardlink shares the source device+inode (cheap check); otherwise
  # compare bytes, which also catches a stale copy-fallback install on another
  # volume.
  #
  # Both id sets are collected in one stat call per tree. Statting per file
  # instead cost a process per file per tree, ~1800 of them for a 447-file
  # install, which was the whole runtime of an unchanged re-run.
  local rel rels
  rels="$(printf '%s\n' "$src_files" | sed 's|^\./||')"
  [[ -n "$rels" ]] || return 1

  # comm -23 leaves the source lines with no identical counterpart in the
  # install: exactly the files whose hardlink is broken or missing. Sorted
  # streams rather than an associative array so this still runs under the bash
  # 3.2 that macOS ships.
  # Same C collation the producers sort under: GNU comm rejects C-ordered input
  # as unsorted in a UTF-8 locale, and then emits nothing, which would read as
  # "no files differ" and leave a stale install in place.
  local changed
  changed="$(LC_ALL=C comm -23 \
    <(file_ids_in "$SOURCE_DIR" "$rels") \
    <(file_ids_in "$CURSOR_TARGET" "$rels") |
    sed 's|:[0-9]*:[0-9]*$||')"

  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    cmp -s "${SOURCE_DIR}/${rel}" "${CURSOR_TARGET}/${rel}" || return 0
  done <<<"$changed"

  return 1
}

# Install skill files into CURSOR_TARGET. Prefer hardlinks; fall back to copy per entry
# when linking fails (e.g. cross-filesystem). Prints "hardlink", "copy", or "mixed".
cursor_install_tree() {
  local entry base mode="" entry_mode
  local had_hardlink=0 had_copy=0

  mkdir -p "$CURSOR_TARGET" || {
    echo "ERROR: cannot create $CURSOR_TARGET (Cursor)" >&2
    return 1
  }

  shopt -s dotglob nullglob
  for entry in "$SOURCE_DIR"/*; do
    base="$(basename "$entry")"
    if cursor_should_skip_entry "$base"; then
      continue
    fi

    if cp -al "$entry" "$CURSOR_TARGET/$base" 2>/dev/null; then
      entry_mode=hardlink
    elif rm -rf "${CURSOR_TARGET:?}/$base" && cp -a "$entry" "$CURSOR_TARGET/$base"; then
      entry_mode=copy
      echo "note: copied $base (hardlink unavailable, different filesystem?)" >&2
    else
      echo "ERROR: failed to install $base into $CURSOR_TARGET (Cursor)" >&2
      return 1
    fi

    case "$entry_mode" in
      hardlink) had_hardlink=1 ;;
      copy) had_copy=1 ;;
    esac
  done
  shopt -u dotglob nullglob

  # cp -al recurses unfiltered, so nested exclusions can only be applied after
  # the fact. -prune stops the descent, making a pruned directory one rm -rf
  # rather than one per file inside it. The marker is spared because an earlier
  # run's copy is still valid; cursor_write_marker rewrites it either way.
  cursor_prune_expr
  (cd "$CURSOR_TARGET" && find . "${CURSOR_PRUNE_EXPR[@]}" \
    ! -name '.pr-review-loop-source' -prune -exec rm -rf {} +) || {
    echo "ERROR: prune pass failed in $CURSOR_TARGET (Cursor)" >&2
    return 1
  }

  if ((had_hardlink && had_copy)); then
    mode=mixed
  elif ((had_copy)); then
    mode=copy
  else
    mode=hardlink
  fi
  printf '%s\n' "$mode"
}

cursor_install_one() {
  local parent install_mode refresh=0
  parent="$(dirname "$CURSOR_TARGET")"

  if target_is_source "$CURSOR_TARGET"; then
    echo "skipped (target is this source checkout): $CURSOR_TARGET (Cursor)"
    return
  fi

  if ((UNINSTALL)); then
    if [[ -L "$CURSOR_TARGET" ]]; then
      local current
      current="$(readlink "$CURSOR_TARGET")"
      if symlink_points_to_source "$CURSOR_TARGET"; then
        rm "$CURSOR_TARGET" || {
          echo "ERROR: cannot remove $CURSOR_TARGET (Cursor)" >&2
          return 1
        }
        echo "removed symlink: $CURSOR_TARGET (Cursor)"
      else
        echo "skipped (symlink points elsewhere): $CURSOR_TARGET -> $current (Cursor)" >&2
      fi
    elif cursor_is_our_install; then
      rm -rf "$CURSOR_TARGET" || {
        echo "ERROR: cannot remove $CURSOR_TARGET (Cursor)" >&2
        return 1
      }
      echo "removed Cursor install: $CURSOR_TARGET"
    elif [[ -e "$CURSOR_TARGET" ]]; then
      echo "skipped (not our install): $CURSOR_TARGET (Cursor)"
    else
      echo "not installed: $CURSOR_TARGET (Cursor)"
    fi
    return
  fi

  mkdir -p "$parent" || {
    echo "ERROR: cannot create $parent (Cursor)" >&2
    return 1
  }

  if [[ -L "$CURSOR_TARGET" ]]; then
    local current
    current="$(readlink "$CURSOR_TARGET")"
    if symlink_points_to_source "$CURSOR_TARGET"; then
      rm "$CURSOR_TARGET" || {
        echo "ERROR: cannot remove $CURSOR_TARGET (Cursor)" >&2
        return 1
      }
    else
      echo "ERROR: $CURSOR_TARGET is a symlink to $current. Remove it manually." >&2
      return 1
    fi
  elif [[ -e "$CURSOR_TARGET" ]] && ! cursor_is_our_install; then
    echo "ERROR: $CURSOR_TARGET exists and is not this skill. Remove it manually." >&2
    return 1
  elif cursor_is_our_install && ! ((FORCE)) && ! cursor_tree_needs_refresh; then
    cursor_write_marker || {
      echo "ERROR: cannot write marker $CURSOR_MARKER (Cursor)" >&2
      return 1
    }
    echo "already installed: $CURSOR_TARGET (Cursor)"
    return
  elif cursor_is_our_install; then
    refresh=1
    rm -rf "$CURSOR_TARGET" || {
      echo "ERROR: cannot remove $CURSOR_TARGET (Cursor)" >&2
      return 1
    }
  fi

  install_mode="$(cursor_install_tree)" || return 1
  cursor_write_marker || {
    echo "ERROR: cannot write marker $CURSOR_MARKER (Cursor)" >&2
    return 1
  }
  if ((refresh)); then
    case "$install_mode" in
      hardlink) echo "refreshed (hardlink): $CURSOR_TARGET (Cursor)" ;;
      copy) echo "refreshed (copy): $CURSOR_TARGET (Cursor)" ;;
      mixed) echo "refreshed (hardlink + copy): $CURSOR_TARGET (Cursor)" ;;
    esac
  else
    case "$install_mode" in
      hardlink) echo "installed (hardlink): $CURSOR_TARGET (Cursor)" ;;
      copy) echo "installed (copy): $CURSOR_TARGET (Cursor)" ;;
      mixed) echo "installed (hardlink + copy): $CURSOR_TARGET (Cursor)" ;;
    esac
  fi
}

link_one() {
  local target="$1"
  local label="$2"
  local parent
  parent="$(dirname "$target")"

  if target_is_source "$target"; then
    echo "skipped (target is this source checkout): $target ($label)"
    return
  fi

  if ((UNINSTALL)); then
    if [[ -L "$target" ]]; then
      local current
      current="$(readlink "$target")"
      if symlink_points_to_source "$target"; then
        rm "$target" || {
          echo "ERROR: cannot remove $target ($label)" >&2
          return 1
        }
        echo "removed symlink: $target ($label)"
      else
        echo "skipped (symlink points elsewhere): $target -> $current ($label)" >&2
      fi
    elif [[ -e "$target" ]]; then
      echo "skipped (not a symlink): $target ($label)"
    else
      echo "not installed: $target ($label)"
    fi
    return
  fi

  mkdir -p "$parent" || {
    echo "ERROR: cannot create $parent ($label)" >&2
    return 1
  }

  if [[ -L "$target" ]]; then
    local current
    current="$(readlink "$target")"
    if symlink_points_to_source "$target"; then
      if ! ((FORCE)); then
        echo "already linked: $target ($label)"
        return
      fi
    elif ! ((FORCE)); then
      echo "skipped (symlink points elsewhere): $target -> $current ($label)" >&2
      echo "rerun with --force to replace this symlink" >&2
      return 1
    fi
    # Reaching here means --force: re-establish the link even when foreign or
    # stale. It is also the recovery path after the checkout moved.
    rm "$target" || {
      echo "ERROR: cannot remove $target ($label)" >&2
      return 1
    }
    ln -s "$SOURCE_DIR" "$target" || {
      echo "ERROR: failed to link $target ($label)" >&2
      return 1
    }
    echo "re-linked: $target -> $SOURCE_DIR ($label)"
    return
  elif [[ -e "$target" ]]; then
    echo "ERROR: $target exists and is not a symlink. Remove it manually." >&2
    return 1
  fi

  ln -s "$SOURCE_DIR" "$target" || {
    echo "ERROR: failed to link $target ($label)" >&2
    return 1
  }
  echo "linked: $target -> $SOURCE_DIR ($label)"
}

# Per-file variant of link_one for the opencode agent files: the identity
# oracle compares the link value to one specific source file, not the repo
# root. On install, a foreign file or foreign symlink is refused with a
# non-zero return; --force re-establishes a foreign or stale symlink, while a
# foreign regular file is never replaced, with or without --force. On uninstall
# a foreign-symlink skip warns on stderr and a non-symlink skip prints to
# stdout; both stay non-fatal, because removing links we did not create is
# never the installer's job.
link_file_one() {
  local src="$1"
  local target="$2"
  local label="$3"
  local parent
  parent="$(dirname "$target")"

  if ((UNINSTALL)); then
    if [[ -L "$target" ]]; then
      local current
      current="$(readlink "$target")"
      if [[ "$current" == "$src" ]]; then
        rm "$target" || {
          echo "ERROR: cannot remove $target ($label)" >&2
          return 1
        }
        echo "removed symlink: $target ($label)"
      else
        echo "skipped (symlink points elsewhere): $target -> $current ($label)" >&2
      fi
    elif [[ -e "$target" ]]; then
      echo "skipped (not a symlink): $target ($label)"
    else
      echo "not installed: $target ($label)"
    fi
    return 0
  fi

  mkdir -p "$parent" || {
    echo "ERROR: cannot create $parent ($label)" >&2
    return 1
  }

  if [[ -L "$target" ]]; then
    local current
    current="$(readlink "$target")"
    if [[ "$current" == "$src" ]]; then
      if ! ((FORCE)); then
        echo "already linked: $target ($label)"
        return 0
      fi
    elif ! ((FORCE)); then
      echo "skipped (symlink points elsewhere): $target -> $current ($label)" >&2
      return 1
    fi
    # Reaching here means --force: re-establish the link even when foreign or
    # stale. It is also the recovery path after the checkout moved.
    rm "$target" || {
      echo "ERROR: cannot remove $target ($label)" >&2
      return 1
    }
    ln -s "$src" "$target" || {
      echo "ERROR: failed to link $target ($label)" >&2
      return 1
    }
    echo "re-linked: $target -> $src ($label)"
    return 0
  elif [[ -e "$target" ]]; then
    echo "ERROR: $target exists and is not a symlink ($label). Remove it manually." >&2
    return 1
  fi

  ln -s "$src" "$target" || {
    echo "ERROR: failed to link $target ($label)" >&2
    return 1
  }
  echo "linked: $target -> $src ($label)"
}

opencode_install_one() {
  local rc=0
  local agent
  link_one "$OPENCODE_TARGET" "opencode" || rc=1
  for agent in "${OPENCODE_AGENTS[@]}"; do
    link_file_one "${OPENCODE_AGENT_SRC_DIR}/${agent}" \
      "${OPENCODE_AGENT_DIR}/${agent}" "opencode agent ${agent%.md}" || rc=1
  done
  return "$rc"
}

# Hosts are attempted independently: a conflict at one target warns and the
# remaining hosts still install. The failure resurfaces as the exit code only
# after every host has been attempted.
install_rc=0

if ((WANT_CURSOR)); then
  cursor_install_one || install_rc=1
fi

if ((WANT_CLAUDE)); then
  link_one "$CLAUDE_TARGET" "Claude Code" || install_rc=1
fi

if ((WANT_CODEX)); then
  link_one "$CODEX_TARGET" "Codex" || install_rc=1
  link_one "$CODEX_SHARED_TARGET" "Codex shared skills" || install_rc=1
fi

if ((WANT_OPENCODE)); then
  opencode_install_one || install_rc=1
fi

if ((install_rc == 0)); then
  echo
  echo "Done."
fi

exit "$install_rc"
