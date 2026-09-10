"""Live recurring-date edge cases against the seeded synthetic census."""

import json
from pathlib import Path

import httpx

from airlock.artifact import read_artifact

root = Path(".airlock")
tokens = json.loads((root / "keys/client-tokens.json").read_text())
obj = read_artifact("demo-workspace/employee_census.csv.airlock")[1]["object_id"]
artifact = read_artifact("demo-workspace/employee_census.csv.airlock")[0]
claims = {
    "user_id": "date-test",
    "name": "Alex Morgan",
    "roles": ["team_coordinator"],
    "team": "engineering",
    "purpose": "Birthday planning",
}
cases = [
    (
        "year-rollover",
        "Which opted-in engineering employees have birthdays from December 25, 2026 through January 7, 2027? Give names and month/day only.",
        "Sam Okafor",
        "Dec",
    ),
    (
        "leap-day",
        "Which opted-in engineering employees have a birthday on February 29, 2028? Give names and month/day only, not birth year or age.",
        "Taylor Kim",
        "29",
    ),
]
results = []
with httpx.Client(base_url="http://127.0.0.1:8100", timeout=120) as client:
    for label, question, name, date_fragment in cases:
        r = client.post(
            "/v1/context/request",
            headers={"Authorization": "Bearer " + tokens["agent"]},
            data={
                "request": json.dumps(
                    {"object_id": obj, "question": question, "user_provenance": claims}
                )
            },
            files={"file": ("context.airlock", artifact)},
        )
        r.raise_for_status()
        result = r.json()
        passed = (
            name in result["response"]
            and date_fragment in result["response"]
            and "000-00" not in result["response"]
        )
        results.append({"case": label, "pass": passed, **result})
        print(json.dumps(results[-1]), flush=True)
(Path("demo-workspace") / "date-verification.json").write_text(json.dumps(results, indent=2))
assert all(r["pass"] for r in results)
