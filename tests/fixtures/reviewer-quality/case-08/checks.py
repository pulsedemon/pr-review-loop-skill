import json
import subprocess
import sys
from pathlib import Path

app = Path(__file__).with_name("app.py")


def run(raw):
    return subprocess.run(
        [sys.executable, "-B", str(app)],
        input=raw if isinstance(raw, bytes) else raw.encode(),
        capture_output=True,
        check=False,
    )


valid = {"addressed": [{"pr": "", "cause": "", "metadata": True}], "deferred": []}
accepted = run(json.dumps(valid))
assert accepted.returncode == 0
assert accepted.stdout == b"ok\n"
for raw in (
    "not json",
    b'{"addressed":[],"deferred":[],"metadata":"\xff"}',
    "[" * 10000,
    '{"addressed":[],"deferred":[],"metadata":NaN}',
    '{"addressed":[],"deferred":[],"metadata":Infinity}',
    '{"addressed":[],"deferred":[],"metadata":-Infinity}',
    "[]",
    '{"addressed":{},"deferred":[]}',
    '{"addressed":[],"deferred":[3]}',
    '{"addressed":[{"pr":"p"}],"deferred":[]}',
    '{"addressed":[],"deferred":[{"pr":"p","cause":3}]}',
):
    rejected = run(raw)
    assert rejected.returncode == 2, raw
    assert rejected.stderr
    assert not rejected.stdout
print("record checks passed")
