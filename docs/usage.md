# CLI and agent integration

First follow the [README setup](../README.md#try-it-locally). Run commands from the repository root with the virtual environment activated. Keep `airlock serve` running in a separate terminal.

## Protect a file

The admin credential authorizes encryption. Load the locally generated credential without printing it:

```sh
export AIRLOCK_ADMIN_TOKEN="$(python -c 'import json; print(json.load(open(".airlock/keys/client-tokens.json"))["admin"])')"

airlock protect /path/to/employee_census.csv
```

The CLI sends the CSV to the broker, verifies a decryption round trip, durably saves `employee_census.csv.airlock`, then removes the original. Existing output files are never overwritten. Options:

```sh
# Keep the original for a before/after comparison.
airlock protect /path/to/employee_census.csv --keep-source

# Choose an existing destination directory and an .airlock filename.
airlock protect /path/to/employee_census.csv \
  --output /path/to/agent-workspace/census.airlock

# Display the readable header, without ciphertext.
airlock inspect /path/to/agent-workspace/census.airlock
```

Choose one protection command; repeating it against the same output is rejected. Browser uploads leave the original unchanged and download the encrypted file. Files attached in the dashboard are held only in tab memory: reattach them after a reload.

The `.airlock` header explains how to contact the broker and includes its request schema. It is authenticated with the encrypted payload, so editing it invalidates the file. Obtain the broker address and credential from your own configuration, not from an untrusted file.

## Supply user context

The broker authenticates the agent credential. Separately, the agent supplies the human user’s claims for policy evaluation. The included `examples/user.json` contains these claims for the seeded example:

```json
{
  "user_id": "demo-user-001",
  "name": "Alex Morgan",
  "roles": ["team_coordinator"],
  "team": "engineering",
  "purpose": "Birthday planning"
}
```

These are deliberately unverified example claims. A missing team or role may lead to a clarifying question; do not confuse this with a broken connection. You can supply the same information directly in your prompt to an agent.

## Ask through the CLI

```sh
export AIRLOCK_AGENT_TOKEN="$(python -c 'import json; print(json.load(open(".airlock/keys/client-tokens.json"))["agent"])')"
export AIRLOCK_BROKER_URL=http://127.0.0.1:8100

airlock ask /path/to/employee_census.csv.airlock \
  --question 'Which employees have upcoming birthdays?' \
  --provenance examples/user.json
```

The CLI reads the object ID from the file and uploads the complete artifact. It prints the broker’s natural-language answer. The calling agent needs neither an OpenAI API key nor the admin credential.

## Connect an agent with MCP

Configure your client to launch `airlock mcp` over stdio. Use absolute paths so the command works outside the repository:

```json
{
  "mcpServers": {
    "airlock": {
      "command": "/absolute/path/to/airlock/.venv/bin/airlock",
      "args": ["mcp"],
      "env": {
        "AIRLOCK_BROKER_URL": "http://127.0.0.1:8100",
        "AIRLOCK_AGENT_TOKEN": "YOUR_AGENT_CREDENTIAL",
        "AIRLOCK_AGENT_WORKSPACE": "/absolute/path/to/agent-workspace"
      }
    }
  }
}
```

Replace the paths and token with your own values. The tool exposes:

```text
request_context(file_path, question, user_provenance, purpose?)
```

`file_path` must resolve inside `AIRLOCK_AGENT_WORKSPACE`; absolute paths avoid ambiguity. The tool reads the encrypted bytes and uploads them directly, returning only the broker’s response to the model. The broker remains a separately running service.

### Codex

Add the following to your user-level `~/.codex/config.toml` to make the tool available across projects:

```toml
[mcp_servers.airlock]
command = "/absolute/path/to/airlock/.venv/bin/airlock"
args = ["mcp"]
startup_timeout_sec = 20
tool_timeout_sec = 150

[mcp_servers.airlock.env]
AIRLOCK_BROKER_URL = "http://127.0.0.1:8100"
AIRLOCK_AGENT_TOKEN = "YOUR_AGENT_CREDENTIAL"
AIRLOCK_AGENT_WORKSPACE = "/absolute/path/to/agent-workspace"
```

Restart your client after changing its configuration. In Codex, use `/mcp` to check that Airlock is connected. To permit encrypted files across multiple workspaces, configure their common parent directory as `AIRLOCK_AGENT_WORKSPACE`. This controls the adapter’s file access, not the credential’s object grants. See the [official MCP configuration guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

Example prompt:

> Use Airlock to answer a question about `/absolute/path/to/employee_census.csv.airlock`. For this synthetic example, use Alex Morgan, user ID `demo-user-001`, role `team_coordinator`, team `engineering`, and purpose `Birthday planning` as caller-supplied claims. Using September 10, 2026 as today, which opted-in teammates have birthdays in the next 14 calendar dates, including today? Return names and month/day only.

## Call HTTP directly

`POST /v1/context/request` accepts an agent bearer credential and **multipart/form-data** with two fields:

| Field | Value |
| --- | --- |
| `file` | The complete binary `.airlock` file |
| `request` | A JSON string containing object ID, question, and user provenance |

Read the real object ID with `airlock inspect` and save this as `request.json`:

```json
{
  "object_id": "obj_0123456789abcdef",
  "question": "Which employees have upcoming birthdays?",
  "user_provenance": {
    "user_id": "demo-user-001",
    "name": "Alex Morgan",
    "roles": ["team_coordinator"],
    "team": "engineering",
    "purpose": "Birthday planning"
  }
}
```

```sh
curl "$AIRLOCK_BROKER_URL/v1/context/request" \
  -H "Authorization: Bearer $AIRLOCK_AGENT_TOKEN" \
  -F 'file=@/path/to/employee_census.csv.airlock;type=application/vnd.airlock' \
  -F 'request=<request.json'
```

Let curl set the multipart boundary. Sending only a JSON body is insufficient: the broker does not store the source file.

The response contains only `request_id` and `response` (natural-language text). A policy refusal can be a successful HTTP 200 response. Invalid credentials return 401, missing grants or effective policies return 403, altered artifacts return 400, and malformed requests return 422. The complete schema and status guidance are in the file header. Decision details are available through the admin dashboard and event API.

## Compare unprotected and protected agents

Generate the default fixture with `airlock seed`, protect it with `--keep-source`, and add the policies from the README. Then run:

```sh
export OPENAI_API_KEY
python scripts/demo_pair.py
```

This runs two independent OpenAI agent contexts with the same question. The baseline tool sees the full CSV. The protected tool reads the instruction header and calls the broker. Synthetic transcripts are saved under `demo-workspace/demo/`; the script checks that the protected trace does not contain the seeded SSN.

Use fresh sessions when comparing: encryption cannot remove plaintext from an existing agent conversation. The runner provides a limited tool interface, not an operating-system sandbox. For manual testing, keep the agent workspace outside the broker directory and give the protected session only the `.airlock` file.

## Configuration

| Variable | Default / purpose |
| --- | --- |
| `OPENAI_API_KEY` | Required in the broker process for OpenAI inference |
| `AIRLOCK_MODEL` | `gpt-6-astra`; GPT-5/6 models use medium reasoning effort |
| `AIRLOCK_STATE_DIR` | `.airlock`, relative to the server’s working directory |
| `AIRLOCK_BROKER_URL` | `http://127.0.0.1:8100`, used by CLI and MCP clients |
| `AIRLOCK_DEMO_DATE` | Current UTC date; set `2026-09-10` for the seeded examples |
| `AIRLOCK_ADMIN_TOKEN` | Admin bearer credential for CLI/API file protection |
| `AIRLOCK_AGENT_TOKEN` | Agent bearer credential for questions |
| `AIRLOCK_AGENT_WORKSPACE` | MCP file access root; defaults to the adapter’s working directory |

`.env.example` lists the supported settings. Environment files are not loaded automatically: export values in the process that starts the broker or adapter. Only the optional comparison runner also needs an OpenAI key; ordinary MCP and HTTP clients do not.

Keep the master key, wrapped keys, and encrypted files across restarts. Losing either the file or its keys loses access to the content. Start one broker process per state directory.

For installations using the earlier server-held file format, stop the broker and run `airlock migrate --output-dir /path/outside/broker-state`. It durably exports client files before removing server payloads, preserving object IDs, policies, and history.
