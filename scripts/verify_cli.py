"""Live CLI errors and explicit output path; assumes the broker is running."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from airlock.artifact import read_artifact

root = Path(".airlock")
tokens = json.loads((root / "keys/client-tokens.json").read_text())
env = {**os.environ, "AIRLOCK_ADMIN_TOKEN": tokens["admin"]}
with tempfile.TemporaryDirectory(prefix="airlock-cli-") as work:
    source = Path(work) / "sample.csv"
    source.write_text("name,team\nMaya,engineering\n")
    output = Path(work) / "sample.airlock"
    original = source.read_bytes()
    cmd = [
        sys.executable,
        "-m",
        "airlock.cli",
        "protect",
        str(source),
        "--output",
        str(output),
        "--keep-source",
    ]
    ok = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    _, ref = read_artifact(output)
    assert source.read_bytes() == original
    rejected = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert rejected.returncode == 1 and "overwrite" in rejected.stderr
    missing = subprocess.run(
        [sys.executable, "-m", "airlock.cli", "protect", str(Path(work) / "missing.csv")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert missing.returncode == 1 and "readable" in missing.stderr
    bad = subprocess.run(
        [
            sys.executable,
            "-m",
            "airlock.cli",
            "protect",
            str(source),
            "--output",
            str(Path(work) / "bad.airlock"),
        ],
        env={**env, "AIRLOCK_ADMIN_TOKEN": "invalid"},
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1 and "401" in bad.stderr
    down = subprocess.run(
        [
            sys.executable,
            "-m",
            "airlock.cli",
            "protect",
            str(source),
            "--output",
            str(Path(work) / "down.airlock"),
        ],
        env={**env, "AIRLOCK_BROKER_URL": "http://127.0.0.1:1"},
        capture_output=True,
        text=True,
    )
    assert down.returncode == 1
    print(
        "CLI verified: explicit output, source preservation, no overwrite, missing file, invalid credential, unavailable broker."
    )
    print("Created object:", ref["object_id"])
