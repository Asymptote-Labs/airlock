"""Run both sides of the synthetic-data demo in independent agent contexts."""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

root = Path(".airlock")
tokens = json.loads((root / "keys/client-tokens.json").read_text())
env = {**os.environ, "AIRLOCK_AGENT_TOKEN": tokens["agent"]}
workspace = Path("demo-workspace") / "demo" / datetime.now().strftime("%Y%m%d-%H%M%S")
(workspace / "baseline").mkdir(parents=True)
(workspace / "protected").mkdir()
shutil.copy(Path("demo-workspace/employee_census.csv"), workspace / "baseline/employee_census.csv")
shutil.copy(
    Path("demo-workspace/employee_census.csv.airlock"),
    workspace / "protected/employee_census.csv.airlock",
)
for mode, filename in [
    ("baseline", "employee_census.csv"),
    ("protected", "employee_census.csv.airlock"),
]:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "airlock.cli",
            "demo",
            str(workspace / mode / filename),
            "--trace",
            str(workspace / f"{mode}-trace.json"),
        ],
        env=env,
        check=True,
    )
baseline = json.loads((workspace / "baseline-trace.json").read_text())
protected = json.loads((workspace / "protected-trace.json").read_text())
assert "000-00-0001" in json.dumps(baseline["tool_results"])
assert "000-00-0001" not in json.dumps(protected)
assert any(t["tool"] == "request_context" for t in protected["tool_results"])
print("Verified: baseline tool context contains seeded SSN; protected context does not.")
print("Evidence:", workspace)
