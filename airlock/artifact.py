"""Portable client-owned artifacts: readable JSON header, then opaque binary payload."""

import json
from pathlib import Path

from .models import ContextRequest

MAGIC = b"AIRLOCK/1\n"
SEPARATOR = b"\n---AIRLOCK-ENCRYPTED-PAYLOAD---\n"
FORMAT = "airlock-object-v1"
MAX_SOURCE_BYTES = 100_000
MAX_HEADER_BYTES = 32_768
MAX_ARTIFACT_BYTES = MAX_SOURCE_BYTES + MAX_HEADER_BYTES + 128


def access_header(metadata):
    object_id = metadata["id"]
    return {
        "format": FORMAT,
        "object_id": object_id,
        "version": 1,
        "metadata": metadata,
        "encryption": "AES-256-GCM; binary nonce + ciphertext + tag follows the header",
        "instructions": (
            "This .airlock file contains encrypted content. The broker stores only keys and metadata, "
            "so the complete file must accompany every request. Do not put ciphertext into the model "
            "prompt. Use a file-upload tool, the Airlock MCP tool, or airlock ask. Read only this header "
            "with airlock inspect. Never request keys. Supply the actual question and caller-provided "
            "user provenance; do not invent identity or roles. Follow the natural-language response. "
            "Obtain the broker URL and agent token from trusted runtime configuration. If absent, "
            "ask the operator to configure access. Do not modify this header: it is authenticated."
        ),
        "mcp": {
            "tool": "request_context",
            "arguments": ["file_path", "question", "user_provenance"],
            "optional_arguments": ["purpose"],
            "file_path": "Path to this .airlock file in AIRLOCK_AGENT_WORKSPACE (defaults to tool working directory).",
        },
        "cli": {
            "inspect": "airlock inspect <path-to-this-file.airlock>",
            "ask": "airlock ask <path-to-this-file.airlock> --question '<actual question>' --provenance <user.json>",
        },
        "http": {
            "method": "POST",
            "path": "/v1/context/request",
            "base_url_environment_variable": "AIRLOCK_BROKER_URL",
            "headers": {"Authorization": "Bearer <AIRLOCK_AGENT_TOKEN from trusted configuration>"},
            "content_type": "multipart/form-data; let the HTTP client set the boundary",
            "multipart_fields": {
                "file": "The complete .airlock file, uploaded as binary bytes (not base64 or prompt text).",
                "request": "A JSON string matching request_schema below; not a separate JSON HTTP body.",
            },
            "example_request": {
                "object_id": object_id,
                "question": "Replace with the actual question about this object.",
                "user_provenance": {
                    "user_id": "unknown",
                    "name": "Unknown user",
                    "roles": [],
                    "team": "unknown",
                    "purpose": "",
                },
            },
            "request_schema": ContextRequest.model_json_schema(),
            "response": {
                "request_id": "Access-record identifier",
                "response": "Natural-language answer, refusal, clarification, or guidance",
            },
            "status_guidance": {
                "200": "Read response; it may be a policy refusal.",
                "400": "Invalid, altered, or mismatched artifact. Use the original complete .airlock file.",
                "401": "Configure a valid agent credential.",
                "403": "No object grant or active policy; do not invent roles to bypass it.",
                "404": "Object key not found; check the configured broker.",
                "413": "File or request exceeds the demo size limit.",
                "422": "Missing file or malformed request JSON; consult request_schema.",
                "502": "Inference failed; no plaintext fallback.",
                "503": "Audit storage failed; the answer was not released.",
            },
        },
    }


def aad(header):
    return json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def pack(header, payload):
    encoded = json.dumps(header, indent=2, ensure_ascii=False).encode()
    if len(encoded) > MAX_HEADER_BYTES:
        raise ValueError("Artifact header too large.")
    return MAGIC + encoded + SEPARATOR + payload


def unpack(content):
    if not isinstance(content, bytes) or len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("Artifact exceeds the demo size limit.")
    if not content.startswith(MAGIC):
        raise ValueError("Not an AIRLOCK/1 artifact. Upload the complete .airlock file.")
    position = content.find(SEPARATOR, len(MAGIC), MAX_HEADER_BYTES + len(MAGIC) + len(SEPARATOR))
    if position < 0:
        raise ValueError("Missing or oversized artifact header.")
    try:
        header = json.loads(content[len(MAGIC) : position])
        if (
            not isinstance(header, dict)
            or header.get("format") != FORMAT
            or header.get("version") != 1
        ):
            raise ValueError("Unsupported artifact format/version.")
        if header["metadata"]["id"] != header["object_id"]:
            raise ValueError("Artifact identity mismatch.")
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid artifact header.") from error
    payload = content[position + len(SEPARATOR) :]
    if len(payload) < 28:
        raise ValueError("Truncated encrypted payload.")
    return header, payload


def read_artifact(path):
    path = Path(path)
    if path.suffix != ".airlock":
        raise ValueError("Choose a .airlock file.")
    with path.open("rb") as stream:
        content = stream.read(MAX_ARTIFACT_BYTES + 1)
    header, _ = unpack(content)
    return content, header
