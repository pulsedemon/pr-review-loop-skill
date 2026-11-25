#!/usr/bin/env bats

load test_helper

@test "manifests/adversary-caps.yaml exists and is valid YAML" {
  python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]).read())" \
    "${REPO_ROOT}/manifests/adversary-caps.yaml"
}

@test "scripts/_adversary_caps.sh contains the adversary_caps_sh cog region (marker canary)" {
  # the generator exits 3 when a marker is missing; this names which one.
  grep -qF "# [[[cog: adversary_caps_sh ]]]" "${REPO_ROOT}/scripts/_adversary_caps.sh" || {
    echo "scripts/_adversary_caps.sh missing cog open marker '# [[[cog: adversary_caps_sh ]]]'"
    return 1
  }
  grep -qF "# [[[end]]]" "${REPO_ROOT}/scripts/_adversary_caps.sh" || {
    echo "scripts/_adversary_caps.sh missing cog end marker '# [[[end]]]'"
    return 1
  }
}

@test "docs/adversary.md contains the regen:adversary-caps region (marker canary)" {
  # same per-marker diagnostic as the helper canary above.
  grep -qF "<!-- regen:adversary-caps:start -->" "${REPO_ROOT}/docs/adversary.md" || {
    echo "docs/adversary.md missing region open marker '<!-- regen:adversary-caps:start -->'"
    return 1
  }
  grep -qF "<!-- regen:adversary-caps:end -->" "${REPO_ROOT}/docs/adversary.md" || {
    echo "docs/adversary.md missing region end marker '<!-- regen:adversary-caps:end -->'"
    return 1
  }
}

@test "templates/state.schema.json contains both adversary-cap counter fields (schema mirror canary)" {
  # _regen_schema iterates _SCHEMA_FIELDS = (shallow_adversary_runs,
  # shallow_approval_adversary_runs) and rewrites properties.<field>.maximum
  # for each. If a future refactor renames or removes one of these fields
  # from templates/state.schema.json AND drops it from _SCHEMA_FIELDS in
  # lockstep, neither --check nor --write would diff that surface — the
  # adversary-cap mirror constraint on the missing counter would silently
  # disappear. Pin the field presences so that case fails loudly here.
  python3 -c "import json,sys; d=json.loads(open(sys.argv[1]).read()); sys.exit(0 if all(f in d['properties'] and 'maximum' in d['properties'][f] for f in ('shallow_adversary_runs','shallow_approval_adversary_runs')) else 1)" \
    "${REPO_ROOT}/templates/state.schema.json" || {
    echo "templates/state.schema.json missing one of the adversary-cap counter fields or its 'maximum' constraint."
    echo "Expected properties.shallow_adversary_runs.maximum and properties.shallow_approval_adversary_runs.maximum."
    return 1
  }
}
