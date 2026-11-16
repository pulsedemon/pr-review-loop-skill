import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

from report import render

records = [
    {"bucket": "loop_unmatched", "summary": "anchored"},
    {"bucket": "unanchored_external", "summary": "external"},
    {"bucket": "ignored", "summary": "omit this"},
    {"bucket": "unanchored_loop", "summary": "loop"},
]
expected = "loop_unmatched: anchored\nunanchored_external: external\nunanchored_loop: loop\n"
output = io.StringIO()
with contextlib.redirect_stdout(output):
    render(records)
assert output.getvalue() == expected
empty = io.StringIO()
with contextlib.redirect_stdout(empty):
    render([])
assert empty.getvalue() == ""
command = subprocess.run(
    [sys.executable, "-B", str(Path(__file__).with_name("report.py"))],
    input=json.dumps(records),
    capture_output=True,
    text=True,
    check=False,
)
assert command.returncode == 0, command.stderr
assert command.stdout == expected
print("bucket checks passed")
