# Review record validator

Run `python app.py` with one JSON record on stdin. It validates the record and
prints the accepted record unchanged. Validation and input failures exit 2.

The record requires `addressed` and `deferred` arrays. Every entry in either
array requires string fields `pr` and `cause`. Empty strings and additional
metadata are allowed. The schema is consumed by the command's production path.

Python 3.12+ and jsonschema are required. No network access is used.

Run `python -B checks.py` for the command contract checks.
