import contextlib
import io

from report import render

records = [
    {"bucket": "loop_unmatched", "summary": "anchored"},
    {"bucket": "unanchored_external", "summary": "external"},
    {"bucket": "ignored", "summary": "omit this"},
    {"bucket": "unanchored_loop", "summary": "loop"},
]
output = io.StringIO()
with contextlib.redirect_stdout(output):
    render(records)
assert output.getvalue() == (
    "loop_unmatched: anchored\nunanchored_external: external\nunanchored_loop: loop\n"
)
empty = io.StringIO()
with contextlib.redirect_stdout(empty):
    render([])
assert empty.getvalue() == ""
print("bucket checks passed")
