"""unified diff records follow the output stream's line endings."""

import io
import os
import subprocess
import sys
from contextlib import redirect_stderr
from pathlib import Path

from generator_io import emit_drift_diff
from personas_fixture import write_personas_yaml


def test_diff_on_crlf_stream_preserves_unicode_content_and_marks_unterminated_lines() -> None:
    raw = io.BytesIO()
    with io.TextIOWrapper(raw, encoding="utf-8", newline="\r\n", write_through=True) as stream:
        with redirect_stderr(stream):
            emit_drift_diff(Path("target.md"), "left\u2028right\r\nold", "left\u2028right\r\nnew")
        output = raw.getvalue()

    assert output == "\r\n".join(
        [
            "--- target.md",
            "+++ target.md (regenerated)",
            "@@ -1,2 +1,2 @@",
            " left\u2028right",
            "-old",
            r"\ No newline at end of file",
            "+new",
            r"\ No newline at end of file",
            "",
        ]
    ).encode("utf-8")


def test_generator_cli_emits_utf8_diff_under_ascii_locale(tmp_path: Path) -> None:
    manifest = write_personas_yaml(tmp_path, ["alpha"])
    target = tmp_path / "SKILL.md"
    target.write_text(
        "<!-- regen:panel-count-total:start -->\n<!-- template: café {n} -->\n"
        "café 99\n<!-- regen:panel-count-total:end -->\n",
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[1] / "regen_panel_counts.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--check",
            "--corpus-root",
            str(tmp_path),
            "--manifest",
            str(manifest),
        ],
        capture_output=True,
        env={**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"},
    )
    assert result.returncode == 5
    lines = result.stderr.decode("utf-8").splitlines()
    assert "-café 99" in lines
    assert "+café 1" in lines
