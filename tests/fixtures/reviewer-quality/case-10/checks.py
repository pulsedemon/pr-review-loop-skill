import json
import subprocess
import sys
from pathlib import Path

report = Path(__file__).parent / "tools/recall-harness/report.py"


def run_report(records):
    return subprocess.run(
        [sys.executable, "-B", str(report)],
        input=json.dumps(records),
        capture_output=True,
        text=True,
        check=False,
    )


records = [
    {"bucket": "loop_unmatched", "summary": "anchored"},
    {"bucket": "unanchored_external", "summary": "external"},
    {"bucket": "ignored", "summary": "omit this"},
    {"bucket": "unanchored_loop", "summary": "loop"},
]
rendered = run_report(records)
assert rendered.returncode == 0, rendered.stderr
assert rendered.stdout == (
    "loop_unmatched: anchored\nunanchored_external: external\nunanchored_loop: loop\n"
)
empty = run_report([])
assert empty.returncode == 0, empty.stderr
assert empty.stdout == ""
print("bucket checks passed")
