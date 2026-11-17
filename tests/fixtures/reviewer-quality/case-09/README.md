# Local validation

Run `bash scripts/run_local_validation.sh` from this project root. It detects
the project's stack and runs that stack's checks. A `package.json` marks a Node
project, whose check is `npm test`.

Exit 0 certifies that the detected stack's checks actually ran and passed. A
detected stack whose package manager is not on `PATH` must exit 1. A directory
with no recognized stack exits 2. A failing check exits 3.

npm is supplied by the developer environment. The command must not install
dependencies or use the network. `greeting.js` supplies the application code
and `greeting.test.js` its test; `checks.py` verifies the command contract.

Run `python -B checks.py` for the command contract checks.
