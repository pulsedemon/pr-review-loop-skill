import os
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).parent

with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
    bin_dir = Path(directory)
    env = dict(os.environ, PATH=str(bin_dir))
    command = ["/bin/bash", str(root / "scripts/validate.sh")]
    missing = subprocess.run(
        command, cwd=root, env=env, capture_output=True, text=True, check=False
    )
    assert missing.returncode == 2, missing
    assert "ruff is required" in missing.stderr
    checker = bin_dir / "ruff"
    checker.write_text(
        '#!/bin/sh\n[ "$*" = "check ." ] || exit 99\n'
        'printf "%s\\n" "checker executed"\nexit "$FIXTURE_CHECKER_EXIT"\n'
    )
    checker.chmod(0o755)
    for expected_exit in (0, 7):
        env["FIXTURE_CHECKER_EXIT"] = str(expected_exit)
        checked = subprocess.run(
            command, cwd=root, env=env, capture_output=True, text=True, check=False
        )
        assert checked.returncode == expected_exit
        assert checked.stdout == "checker executed\n"
print("validation checks passed")
