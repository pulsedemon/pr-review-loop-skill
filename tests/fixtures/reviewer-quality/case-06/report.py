import json
import sys


def render(records):
    for record in records:
        if record["bucket"] in ("loop_unmatched", "unanchored_external", "unanchored_loop"):
            print(f"{record['bucket']}: {record['summary']}")


if __name__ == "__main__":
    render(json.load(sys.stdin))
