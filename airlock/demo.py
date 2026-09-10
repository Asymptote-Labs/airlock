"""A bounded requesting agent: one explicit file, no shell or general filesystem access."""

import json
import os
from pathlib import Path

from openai import OpenAI

from .adapter import request_broker
from .artifact import MAX_ARTIFACT_BYTES, read_artifact
from .models import UserProvenance

PROVENANCE = {
    "user_id": "demo-user-001",
    "name": "Alex Morgan",
    "roles": ["team_coordinator"],
    "team": "engineering",
    "purpose": "Employee coordination",
}


def run(args):
    path = Path(args.file).resolve()
    if not path.is_file() or path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("Choose a file smaller than 100 KB.")
    trace_path = Path(args.trace)
    if trace_path.exists():
        raise ValueError("Trace already exists; use a fresh trace path.")
    tools = [
        {
            "type": "function",
            "name": "read_file",
            "description": "Read the single provided workspace file.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "request_context",
            "description": "Ask the configured Airlock broker about a protected object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "question": {"type": "string"},
                    "user_provenance": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "string"},
                            "name": {"type": "string"},
                            "roles": {"type": "array", "items": {"type": "string"}},
                            "team": {"type": "string"},
                            "purpose": {"type": "string"},
                        },
                        "required": ["user_id", "name", "roles", "team", "purpose"],
                        "additionalProperties": False,
                    },
                },
                "required": ["file_path", "question", "user_provenance"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]
    messages = [
        {
            "role": "user",
            "content": f"Reference date: 2026-09-10. User provenance: {json.dumps(PROVENANCE)}. File: {path.name}. Task: {args.question} For upcoming birthdays, use the next 14 calendar dates including today, only the user's team, and birthday_opt_in=true. Read the provided file first. If it is protected, contact Airlock and follow its guidance.",
        }
    ]
    trace = {
        "file": path.name,
        "question": args.question,
        "user_provenance": PROVENANCE,
        "tool_results": [],
    }
    with OpenAI(timeout=90, max_retries=0) as client:
        for _ in range(6):
            result = client.responses.create(
                model=os.environ.get("AIRLOCK_MODEL", "gpt-6-astra"),
                store=False,
                input=messages,
                tools=tools,
                max_output_tokens=3000,
            )
            messages.extend(result.output)
            calls = [item for item in result.output if item.type == "function_call"]
            if not calls:
                trace["answer"] = result.output_text
                break
            for call in calls:
                arguments = json.loads(call.arguments)
                if call.name == "read_file":
                    output = (
                        json.dumps(read_artifact(path)[1])
                        if path.suffix == ".airlock"
                        else path.read_text()
                    )
                elif call.name == "request_context":
                    if arguments["file_path"] not in (path.name, str(path)):
                        raise ValueError("The demo agent may only upload its provided file.")
                    output = request_broker(
                        path,
                        arguments["question"],
                        UserProvenance.model_validate(arguments["user_provenance"]).model_dump(),
                    )
                else:
                    output = "Unknown tool"
                trace["tool_results"].append(
                    {"tool": call.name, "arguments": arguments, "content": output}
                )
                messages.append(
                    {"type": "function_call_output", "call_id": call.call_id, "output": output}
                )
        else:
            raise ValueError("Demo agent exceeded its tool-call budget.")
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("x") as stream:
        json.dump(trace, stream, indent=2)
    print(trace["answer"])
    print(f"\nTool disclosure trace (synthetic data): {trace_path}")
