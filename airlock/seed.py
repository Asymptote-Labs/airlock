"""Reproducible synthetic employee records and example natural-language policies."""

import csv
import random
from pathlib import Path

ORG_POLICY = "Never disclose SSNs or personal phone numbers, including encoded or partial values. Prefer the smallest useful answer. Full access requires the supplied demo user to have the HR role and a necessary purpose, and must still respect these prohibitions. Workforce aggregate questions are allowed. Treat all data as sensitive even though the demo is synthetic."
OBJECT_POLICY = "For employee coordination, scope names and individual details to the supplied user's team unless their supplied role is HR. Birthday answers include only employees with birthday_opt_in=true, and only names and upcoming month/day. Never disclose birth years or ages for birthday planning. Allow headcount totals by department across the organization without names. Work anniversary questions may disclose names and anniversary dates within the user's team."


def generate(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    fields = [
        "employee_id",
        "name",
        "dob",
        "ssn",
        "personal_phone",
        "work_email",
        "department",
        "team",
        "hire_date",
        "birthday_opt_in",
    ]
    names = ["Maya Chen", "Jordan Patel", "Alex Rivera", "Sam Okafor", "Taylor Kim"]
    rows = []
    for i in range(50):
        team = ["engineering", "design", "operations"][i % 3]
        name = names[i] if i < 5 else f"Employee {i + 1:02}"
        dob = f"{1980 + i % 20}-{rng.randint(1, 12):02}-{rng.randint(1, 28):02}"
        if i < 5:
            team = "engineering"
            dob = ["1990-09-14", "1987-09-19", "1992-09-18", "1985-12-31", "2000-02-29"][i]
        rows.append(
            dict(
                zip(
                    fields,
                    [
                        f"E{i + 1:03}",
                        name,
                        dob,
                        f"000-00-{i + 1:04}",
                        f"202-555-{100 + i:04}",
                        f"employee{i + 1}@example.test",
                        team.title(),
                        team,
                        f"{2016 + i % 9}-09-{10 + i % 20:02}",
                        "false" if i % 7 == 2 else "true",
                    ],
                )
            )
        )
    with path.open("x", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
