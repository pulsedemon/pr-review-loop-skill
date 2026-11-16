# Review record checker

Run `python app.py` with one JSON record on stdin. The record requires
`addressed` and `deferred` arrays. Every entry in either array requires string
fields `pr` and `cause`. Empty strings and additional metadata are allowed.

A valid record prints `ok` and exits 0. An invalid record prints a message to
stderr, prints nothing to stdout, and exits 2.

Python 3.12+ is required. No dependencies or network access are used.

Run `python -B checks.py` for the command contract checks.
