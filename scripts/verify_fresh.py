"""Rehearse initialization, CLI protection, policies, inference, and restart on fresh state."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from airlock.artifact import read_artifact
from airlock.seed import OBJECT_POLICY, ORG_POLICY

Path("demo-workspace").mkdir(exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="rehearsal-", dir="demo-workspace")).resolve()
state = work / "server"
env = {
    **os.environ,
    "AIRLOCK_STATE_DIR": str(state),
    "AIRLOCK_BROKER_URL": "http://127.0.0.1:8181",
    "AIRLOCK_DEMO_DATE": "2026-09-10",
}
subprocess.run(
    [sys.executable, "-m", "airlock.cli", "init", "--state-dir", str(state)], env=env, check=True
)
source = work / "employee_census.csv"
subprocess.run(
    [sys.executable, "-m", "airlock.cli", "seed", "--output", str(source)], env=env, check=True
)
tokens = json.loads((state / "keys/client-tokens.json").read_text())
env["AIRLOCK_ADMIN_TOKEN"] = tokens["admin"]
process = None
log = (work / "server.log").open("w")


def start():
    process = subprocess.Popen(
        [sys.executable, "-m", "airlock.cli", "serve", "--port", "8181"],
        env=env,
        stdout=log,
        stderr=log,
    )
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Rehearsal broker exited")
        try:
            if httpx.get(env["AIRLOCK_BROKER_URL"] + "/health", timeout=1).status_code == 200:
                return process
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    process.terminate()
    process.wait()
    raise RuntimeError("Rehearsal broker did not start")


try:
    process = start()
    subprocess.run(
        [sys.executable, "-m", "airlock.cli", "protect", str(source)], env=env, check=True
    )
    artifact, reference = read_artifact(source.with_name(source.name + ".airlock"))
    assert not source.exists()
    assert all(
        "ciphertext" not in json.loads(p.read_text()) for p in (state / "objects").glob("*.json")
    )
    with httpx.Client(
        base_url=env["AIRLOCK_BROKER_URL"],
        headers={"Authorization": "Bearer " + tokens["admin"]},
        timeout=120,
    ) as client:
        for name, text, scope, object_id in [
            ("Privacy", ORG_POLICY, "organization", None),
            ("Coordination", OBJECT_POLICY, "object", reference["object_id"]),
        ]:
            client.post(
                "/admin/policies",
                json={"name": name, "text": text, "scope": scope, "object_id": object_id},
            ).raise_for_status()
        body = {
            "object_id": reference["object_id"],
            "question": "Which employees have upcoming birthdays?",
            "user_provenance": {
                "user_id": "fresh-demo",
                "name": "Alex Morgan",
                "roles": ["team_coordinator"],
                "team": "engineering",
                "purpose": "Birthday planning",
            },
        }
        response = client.post(
            "/v1/context/request",
            headers={"Authorization": "Bearer " + tokens["agent"]},
            data={"request": json.dumps(body)},
            files={"file": ("context.airlock", artifact)},
        )
        response.raise_for_status()
        result = response.json()
        assert "Maya Chen" in result["response"] and "Jordan Patel" in result["response"]
        assert "000-00-" not in result["response"]
        event = client.get("/admin/events/" + result["request_id"]).json()
        process.terminate()
        process.wait(timeout=10)
        process = start()
        assert client.get("/admin/events/" + result["request_id"]).json() == event
        assert client.get("/admin/objects").json()[0]["id"] == reference["object_id"]
        assert len(client.get("/admin/policies").json()) == 2
        # Same key and object still work after a real server restart.
        body["question"] = "How many employees are in each department?"
        response = client.post(
            "/v1/context/request",
            headers={"Authorization": "Bearer " + tokens["agent"]},
            data={"request": json.dumps(body)},
            files={"file": ("context.airlock", artifact)},
        )
        response.raise_for_status()
        assert "20" in response.json()["response"] and "15" in response.json()["response"]
        (work / "verification.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "birthday_request_id": result["request_id"],
                    "post_restart_request_id": response.json()["request_id"],
                    "model": event["model"],
                    "prompt_version": event["prompt_version"],
                },
                indent=2,
            )
        )
    print(
        "Fresh-state initialization, CLI, policies, scoped answer, and server restart verified:",
        state,
    )
finally:
    if process and process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    log.close()
