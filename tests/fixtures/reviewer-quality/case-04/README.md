# Local validation

Run `bash scripts/validate.sh` from this project root. The Python source must
pass `ruff check .`. Exit 0 certifies that the check actually ran and passed;
an unavailable checker must exit 2. A checker failure retains its exit status.

Ruff is supplied by the developer environment. The command must not install
dependencies or use the network. `app.py` supplies the application code; `checks.py` verifies the command contract.

Run `python -B checks.py` for the command contract checks.
