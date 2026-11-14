# Finding report

Run `python report.py` with a JSON array on stdin. Each entry has string fields
`bucket` and `summary`. Accepted buckets and required output live in
[the labeling contract](docs/label.md). Input is a validated array supplied by the
collector; this command owns rendering, not collection or input validation.

Run `python -B checks.py` for the command contract checks.
