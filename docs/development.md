# Development and testing

Install the project with `pip install -e '.[test]'` and the frontend with `npm ci --prefix web`. Run all commands from the repository root unless otherwise noted.

## Local checks

```sh
pytest -q
ruff check airlock tests scripts
ruff format --check airlock tests scripts
npm run format:check --prefix web
npm run build --prefix web
```

Automated tests do not need an OpenAI key. They cover authenticated encryption, tampering and object substitution, policy revision snapshots, credential roles/grants/expiry, source preservation on failed protection, provider errors, audit failure, multipart limits, automatic dashboard sessions, and legacy export recovery.

Use `ruff format airlock tests scripts` and `npm run format --prefix web` to format changes. For frontend development, start `airlock serve` and `npm run dev --prefix web` in separate terminals. Vite proxies API calls to the broker on port 8100. Rebuild before using the dashboard served directly by the broker.

## Browser tests

With the broker running and frontend built:

```sh
cd web
npx playwright install chromium
npm run test:smoke
```

The smoke test checks automatic entry, navigation, reload, and admin/agent separation without an OpenAI key or source fixture. Set `AIRLOCK_BROKER_URL` to target a different local broker.

For the complete live workflow, follow the README through seeding and applying the example policy, then run `npm run test:e2e` from `web/`. It uploads the synthetic CSV, downloads and reattaches the encrypted file, creates and edits policies, makes real model requests, verifies historical snapshots, and checks desktop/mobile layouts. Set `AIRLOCK_TEST_CSV` to use a different fixture path; the assertions expect the seeded census. Screenshots and downloads are saved in Git-ignored directories.

## Live evaluations

These scripts call the real OpenAI API, consume API quota, and create objects, policies, and access records. Keep the broker on the example reference date `2026-09-10`. Use synthetic data and an isolated state directory for experimentation.

| Command | What it verifies |
| --- | --- |
| `python scripts/verify_fresh.py` | Fresh state, CLI protection, example policies, scoped answers, persistence across a server restart |
| `python scripts/verify_live.py` | Default census protection, policy setup, and common requests |
| `python scripts/verify_access_levels.py` | All five access modes, repeated canonical cases, exact audit responses and policy snapshots |
| `python scripts/verify_edges.py` | PII, encoded/partial values, opt-outs, team restrictions, injection, conflicting policies, missing facts, aggregates, and anniversaries |
| `python scripts/verify_dates.py` | Year rollover and leap day |
| `python scripts/verify_cli.py` | Live CLI output handling and connection/credential errors |
| `python scripts/verify_mcp.py` | MCP discovery, workspace limits, and a real scoped answer |
| `python scripts/demo_pair.py` | Separate baseline/protected agent contexts and their actual tool disclosures |

`verify_fresh.py` starts its own broker on port 8181 and needs an exported `OPENAI_API_KEY`. Other scripts use the running broker on port 8100 and its `.airlock/` state. Census-based scripts expect `demo-workspace/employee_census.csv` and its encrypted counterpart; follow the CLI quickstart with `--keep-source` first. `verify_live.py` can add the example policies if they are absent.

The mode matrix creates its own harmless schedule and object policy. Repeated cases check Query, Summary, Scoped, Full, and Deny. Edge-case checks compare exact fixture names and counts with independently calculated expectations, and look for prohibited values in actual answers. These assertions are deliberately not a second LLM grading the first one.

Reports and transcripts are saved under `demo-workspace/`. Preserve failed runs while adjusting policy or prompt wording, and rerun the relevant allowed cases as well as refusals. Do not change assertions solely to accept an incorrect answer. Changing the model, prompt, or policies can change observed behavior.

## Repository conventions

- Keep source-file payloads on the client; do not add a server content cache accidentally.
- Use maintained cryptographic primitives and verify failures preserve the source.
- Keep agent responses natural-language and audit metadata separate.
- Record policy revisions and exact responses before release.
- Make identity assumptions explicit; schema validation is not identity verification.
- Do not commit `.env` files, local keys, credentials, generated artifacts, or private transcripts.

The repository uses GitHub Actions for formatting, automated tests, frontend builds, and a browser smoke check. Live OpenAI evaluations remain explicit local commands.
