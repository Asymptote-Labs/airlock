"""Run the dashboard smoke test against isolated state; no OpenAI key required."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx


def main():
    with tempfile.TemporaryDirectory(prefix="airlock-dashboard-") as directory:
        env = {**os.environ, "AIRLOCK_STATE_DIR": directory}
        with (Path(directory) / "server.log").open("w") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "airlock.cli", "serve", "--port", "8182"],
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                with httpx.Client(timeout=1) as client:
                    for _ in range(100):
                        if process.poll() is not None:
                            raise RuntimeError("Isolated dashboard broker exited.")
                        try:
                            response = client.get("http://127.0.0.1:8182/health")
                            if response.status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Isolated dashboard broker did not start.")
                subprocess.run(
                    ["npm", "run", "test:smoke"],
                    cwd="web",
                    env={**env, "AIRLOCK_BROKER_URL": "http://127.0.0.1:8182"},
                    check=True,
                )
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
