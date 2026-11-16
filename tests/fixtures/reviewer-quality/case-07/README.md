# Review record schema

The review-record schema is `state.schema.json` in the `templates` directory.
The record requires `addressed` and `deferred` arrays. Every entry in either
array requires string fields `pr` and `cause`. Empty strings and additional
metadata are allowed.

Python 3.12+ and jsonschema are required. No network access is used.

Run `python -B tests/test_state_schema.py` for the schema contract checks.
