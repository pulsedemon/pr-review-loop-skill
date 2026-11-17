import os
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).parent
command = ["/bin/bash", str(root / "scripts/run_local_validation.sh")]


def validate(cwd, env):
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
    bin_dir = Path(directory) / "bin"
    bin_dir.mkdir()
    env = dict(os.environ, PATH=str(bin_dir))
    missing = validate(root, env)
    assert missing.returncode == 1, missing
    assert "npm" in missing.stderr
    manager = bin_dir / "npm"
    manager.write_text(
        '#!/bin/sh\n[ "$*" = "test" ] || exit 99\n'
        'printf "%s\\n" "tests executed"\nexit "$FIXTURE_NPM_EXIT"\n'
    )
    manager.chmod(0o755)
    for npm_exit, expected_exit in ((0, 0), (7, 3)):
        env["FIXTURE_NPM_EXIT"] = str(npm_exit)
        checked = validate(root, env)
        assert checked.returncode == expected_exit, checked
        assert checked.stdout == "tests executed\n"
    empty = Path(directory) / "empty"
    empty.mkdir()
    unrecognized = validate(empty, env)
    assert unrecognized.returncode == 2, unrecognized
    assert unrecognized.stdout == ""
print("validation checks passed")
