import json
from pathlib import Path

from jsonschema import Draft202012Validator

schema_path = Path(__file__).parents[1] / "templates/state.schema.json"
schema = json.loads(schema_path.read_text())
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema)

for record in (
    {"addressed": [{"pr": "", "cause": "", "metadata": True}], "deferred": []},
    {"addressed": [], "deferred": [{"pr": "p", "cause": "c"}]},
):
    assert validator.is_valid(record), record
for record in (
    [],
    {"deferred": []},
    {"addressed": []},
    {"addressed": {}, "deferred": []},
    {"addressed": [], "deferred": {}},
):
    assert not validator.is_valid(record), record
for field in ("addressed", "deferred"):
    for item in (
        {},
        {"pr": "p"},
        {"cause": "c"},
        {"pr": 3, "cause": "c"},
        {"pr": "p", "cause": 3},
    ):
        record = {"addressed": [], "deferred": []}
        record[field] = [item]
        assert not validator.is_valid(record), (field, item)
print("schema checks passed")
