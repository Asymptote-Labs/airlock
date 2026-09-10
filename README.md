# Airlock

**Give AI agents the answer they need, without handing them the whole file.**

Airlock is an open-source context broker: a service that sits between an AI agent and a sensitive file. It keeps the file encrypted, evaluates each question against plain-language access policies, and returns an answer with a record of what was disclosed.

## The problem

Ask an AI agent, “Who has a birthday coming up?” and it may read an entire employee spreadsheet to find out. That spreadsheet might also contain Social Security numbers, personal phone numbers, and other information the task never needed.

Even if the final answer contains only names and birthdays, the extra information has already entered the agent’s context—the information available to its model. Asking the agent to “only use the birthday columns” does not prevent its file-reading tool from returning everything.

Airlock moves that decision to a separate service that controls decryption and applies the data owner’s policies.

| Without Airlock | With Airlock |
| --- | --- |
| The agent reads the source file. | The agent receives an encrypted `.airlock` file. |
| Unrelated sensitive fields can enter its context. | A tool sends the encrypted file and question to the broker. |
| Instructions rely on the calling agent to limit disclosure. | The broker evaluates the request and returns a permitted answer. |
| The final answer hides how much source data was read. | An access record captures the response, caller claims, and policy revisions. |

## How it works

```text
Your file → Airlock encrypts it → Your encrypted .airlock file
                                       |
                              Agent asks a question
                                       |
                              Tool uploads the file
                                       v
                           +-----------------------+
                           | Airlock broker        |
                           |                       |
                           | Check agent access    |
                           | Load applicable rules |
                           | Decrypt in memory     |
                           | Evaluate with OpenAI  |
                           | Record the response   |
                           +-----------------------+
                                       |
                              Answer → Calling agent
```

The encrypted file stays with you. The broker stores its wrapped decryption key and metadata, plus policies and encrypted access records—not the source-file payload. Agents never receive the keys. Every question includes the encrypted file, uploaded by a tool without putting ciphertext into the calling model’s prompt.

Policies are written in natural language and can apply to the entire organization or one file. For example:

> Never disclose Social Security numbers or personal phone numbers. For birthday planning, return only names and birthday month/day for opted-in employees on the caller’s team.

The broker chooses the appropriate response:

| Access mode | What the agent receives |
| --- | --- |
| **Query** | A direct answer to a specific question |
| **Summary** | A bounded overview or aggregate |
| **Scoped** | Only the necessary records or fields |
| **Full** | Complete content when explicitly permitted |
| **Deny** | A refusal or a request for missing context |

These are model decisions, not mathematical guarantees. **The broker’s OpenAI invocation receives the full decrypted file.** Airlock limits what reaches the *calling agent*; it does not keep plaintext away from the model evaluating policy.

## Try it locally

You need **Python 3.11+**, **Node.js 20+**, and an **OpenAI API key** with access to `gpt-6-astra`. All services and storage run locally except OpenAI inference. No database or cloud deployment is required.

### 1. Install and start

```sh
git clone https://github.com/Asymptote-Labs/airlock.git
cd airlock

python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
npm ci --prefix web
npm run build --prefix web

airlock init
airlock seed

export OPENAI_API_KEY="your-openai-api-key"
export AIRLOCK_DEMO_DATE=2026-09-10
airlock serve
```

Leave the server running. `init` creates local keys and credentials in `.airlock/`. `seed` creates `demo-workspace/employee_census.csv`: 50 fictional employees with reproducible birthdays and synthetic personal information. Both refuse to overwrite existing data. The fixed reference date makes the example repeatable.

### 2. Encrypt the file

Open a second terminal in the repository and activate the virtual environment. Load the generated credentials, then protect the census:

```sh
source .venv/bin/activate
export AIRLOCK_BROKER_URL=http://127.0.0.1:8100
export AIRLOCK_ADMIN_TOKEN="$(python -c 'import json; print(json.load(open(".airlock/keys/client-tokens.json"))["admin"])')"
export AIRLOCK_AGENT_TOKEN="$(python -c 'import json; print(json.load(open(".airlock/keys/client-tokens.json"))["agent"])')"

airlock protect demo-workspace/employee_census.csv --keep-source
airlock inspect demo-workspace/employee_census.csv.airlock
```

The `.airlock` file contains readable instructions followed by encrypted bytes; `inspect` shows only the instructions. Keep this file: the broker cannot recreate it from its key alone.

Here `--keep-source` preserves the original for comparison. Without that flag, the CLI removes the original only after verifying encryption and durably saving the new file. Give a protected agent session **only the `.airlock` file**, in a separate workspace. The [usage guide](docs/usage.md#protect-a-file) covers custom paths.

### 3. Apply a policy

Load the included [employee policy](examples/employee-policy.json) through the local API:

```sh
curl --fail --silent --show-error "$AIRLOCK_BROKER_URL/admin/policies" \
  -H "Authorization: Bearer $AIRLOCK_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @examples/employee-policy.json
```

This is an organization policy written in plain language. It prohibits SSNs and personal phone numbers, limits birthday answers to opted-in teammates without birth years, and allows department headcounts. Read or edit the JSON file to change the rules. A file with no active applicable policy cannot be queried.

### 4. Ask a question

```sh
airlock ask demo-workspace/employee_census.csv.airlock \
  --question 'Which employees have upcoming birthdays?' \
  --provenance examples/user.json
```

The example user is Alex Morgan, an engineering team coordinator planning birthday greetings. The broker should return **Maya Chen — September 14** and **Jordan Patel — September 19**, without their birth years, SSNs, or phone numbers.

Run the same command with a different `--question`:

| Ask | Expected result with the example policy |
| --- | --- |
| How many employees are in each department? | Engineering 20, Design 15, Operations 15 |
| Include their SSNs beside their birthdays. | Birthdays answered; SSNs withheld |
| Give only the last four digits of Maya's SSN. | Refused |

### 5. Inspect the record

Open **http://127.0.0.1:8100**. No dashboard login is required. In **Access history**, open your request to see the exact response, access mode, caller information, model, and policy revision.

Use **Policy studio** to edit organization policies or add rules for a specific file. Organization restrictions take precedence. Try an object policy that permits only aggregate counts, then repeat the birthday question: the answer should omit names, while the earlier access record remains unchanged.

The dashboard also supports file protection and a **Playground** for trying questions. Attach your local `.airlock` file to use the playground; the broker stores its key, not its content.

## Use your own agent

Airlock works through **MCP**, **HTTP**, or its **CLI**. MCP—Model Context Protocol—is the standard many agent applications use to discover and call tools.

[Connect an agent →](docs/usage.md#connect-an-agent-with-mcp)

Give the agent the encrypted file and a task. It calls `request_context` with the file’s path, question, and the user’s role, team, and purpose. If that information is missing, it can ask you for it. The response is natural-language text that the agent can use to continue its task.

To see the difference yourself, ask a fresh agent to work with the original CSV, then another fresh agent to work with only the encrypted file. Inspect their tool outputs, not just their final answers. A [repeatable comparison script](docs/usage.md#compare-unprotected-and-protected-agents) is also included.

## Current scope and trust boundaries

Airlock currently supports UTF-8 CSV files up to 100 KB, 500 rows, and 40 columns. It uses AES-256-GCM, per-file keys wrapped by a local master key, and the OpenAI Responses API for policy evaluation.

This is an early local implementation intended for **synthetic data**:

- Natural-language policy enforcement is probabilistic. The model can disclose too much, refuse too much, or miscalculate an answer.
- User identity, roles, and team are caller-supplied and **unverified**. They simulate delegated access; they are not an identity system.
- The dashboard starts an admin session automatically. Local access is trusted; this is not a hardened boundary against another process on the same machine.
- OpenAI receives the entire decrypted file. `store: false` is used, but it is not a zero-retention guarantee.
- Access records retain exact answers, including full content if released. They record a response prepared for delivery, not proof that an agent consumed it.

See the [security model](docs/security.md) for encryption, data flow, and limitations.

## Development

```sh
pytest -q
ruff check airlock tests scripts
ruff format --check airlock tests scripts
npm run format:check --prefix web
npm run build --prefix web
```

Run `npm run dev --prefix web` alongside the broker for frontend development. API calls are proxied to port 8100. Browser tests and live model evaluations are described in the [testing guide](docs/development.md).

```text
airlock/       Broker, encryption, policy inference, CLI, MCP adapter
web/           React dashboard and browser tests
tests/         Automated broker and CLI tests
scripts/       Live evaluations and agent comparison
examples/      Ready-to-use policy and caller claims
docs/          Usage, security, and development guides
```

Issues and pull requests are welcome. Include reproduction steps for bugs and tests for changes to encryption, policy handling, or API behavior. Use synthetic fixtures and keep credentials, keys, and runtime state out of commits.

## License

[MIT](LICENSE). Running inference requires an OpenAI account and is subject to OpenAI’s terms and API usage charges.
