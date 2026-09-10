"""MCP file-upload adapter and shared HTTP transport for agent requests."""

import json
import os
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

from .artifact import read_artifact
from .models import UserProvenance


def request_broker(file_path, question, user_provenance, purpose=""):
    """Transport uploads bytes; the calling model never has to read ciphertext."""
    content, header = read_artifact(file_path)
    token = os.environ.get("AIRLOCK_AGENT_TOKEN")
    if not token:
        raise ValueError("Set AIRLOCK_AGENT_TOKEN for the requesting agent.")
    metadata = {
        "object_id": header["object_id"],
        "question": question,
        "user_provenance": user_provenance,
        "purpose": purpose,
    }
    with httpx.Client(timeout=120, follow_redirects=False) as client:
        response = client.post(
            os.environ.get("AIRLOCK_BROKER_URL", "http://127.0.0.1:8100") + "/v1/context/request",
            headers={"Authorization": f"Bearer {token}"},
            data={"request": json.dumps(metadata)},
            files={"file": (Path(file_path).name, content, "application/vnd.airlock")},
        )
    body = response.json()
    return (
        body.get("response")
        or f"Airlock request failed ({response.status_code}): {body.get('detail', 'Check the upload and credential.')}"
    )


def run():
    mcp = FastMCP("Airlock")
    workspace = Path(os.environ.get("AIRLOCK_AGENT_WORKSPACE", ".")).resolve()

    @mcp.tool()
    def request_context(
        file_path: str, question: str, user_provenance: UserProvenance, purpose: str = ""
    ) -> str:
        """Upload a client-held .airlock file and ask a question. file_path must be within the configured agent workspace. File bytes are uploaded by this tool, never returned to the model. Supply the user's unverified identity, roles, team and purpose. Follow the natural-language answer and guidance."""
        path = (workspace / file_path).resolve()
        if not path.is_relative_to(workspace):
            raise ValueError("File must be inside AIRLOCK_AGENT_WORKSPACE.")
        return request_broker(path, question, user_provenance.model_dump(), purpose)

    mcp.run(transport="stdio")
