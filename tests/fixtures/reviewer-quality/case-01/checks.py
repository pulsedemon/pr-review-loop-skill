import json
import subprocess
import sys
from pathlib import Path

app = Path(__file__).with_name("app.py")


def run(raw):
    return subprocess.run(
        [sys.executable, "-B", "-X", "int_max_str_digits=4300", str(app)],
        input=raw,
        text=True,
        capture_output=True,
        check=False,
    )


valid = {"addressed": [{"pr": "", "cause": "", "metadata": True}], "deferred": []}
accepted = run(json.dumps(valid))
assert accepted.returncode == 0
assert json.loads(accepted.stdout) == valid
assert run('{"addressed":[],"deferred":[]}').returncode == 0
assert run("not json").returncode == 2
for constant in ("NaN", "Infinity", "-Infinity", "7" * 4301):
    invalid_number = run('{"addressed":[],"deferred":[],"metadata":' + constant + "}")
    assert invalid_number.returncode == 2
    assert invalid_number.stderr
large_exponent = '{"addressed":[],"deferred":[],"metadata":1e400}'
preserved = run(large_exponent)
assert preserved.returncode == 0
assert preserved.stdout == large_exponent
for field in ("addressed", "deferred"):
    for item in ({}, {"pr": "p"}, {"cause": "c"}, {"pr": 3, "cause": "c"}):
        record = {"addressed": [], "deferred": []}
        record[field] = [item]
        rejected = run(json.dumps(record))
        assert rejected.returncode == 2, (field, item, rejected.stdout)
        assert rejected.stderr
print("record checks passed")
