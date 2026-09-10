# Security model

Airlock separates access to an encrypted file from permission to receive its contents. Encryption is enforced by code; disclosure policy is interpreted by a language model. The current local implementation uses synthetic data and trusts the operator’s machine.

## Data flow and storage

| Location | Data held |
| --- | --- |
| Client `.airlock` file | Readable metadata/instructions and the encrypted source payload |
| Broker `keys/` | Master key and local credential recovery file |
| Broker `objects/` | Wrapped per-object keys, metadata, and artifact fingerprints |
| Broker `policies/` | Versioned natural-language policies |
| Broker `identities/` | Credential hashes, grants, and expiry |
| Broker `audit/` | Encrypted request and response records |
| OpenAI invocation | Full decrypted source records, policies, question, and user claims |
| Calling agent | File instructions and the broker’s returned answer |

The broker does not persist source-file plaintext or its encrypted payload. Upload parsing and encryption/decryption are bounded and remain in application memory. Python does not guarantee secure memory erasure; OS swap and crash dumps are outside this boundary.

Access records intentionally retain exact questions, answers, and caller claims. Full access can therefore put the complete disclosed content in an encrypted audit record. Metadata such as filenames and field names is not encrypted and should not contain secrets.

## Cryptographic controls

Each object uses a random AES-256-GCM key and nonce. The complete instruction header, including object ID and version, is authenticated with the payload. A SHA-256 fingerprint in the registry binds the exact artifact bytes. Object keys are wrapped under the broker’s local master key with separate nonces and identity-bound associated data.

Changed headers, tampered payloads, mismatched object IDs, and incorrect keys are rejected. Agents never receive decryption keys, including in Full mode. A client must upload the complete artifact for every question; the registry cannot reconstruct a missing file.

CLI protection verifies a decryption round trip and durably saves the artifact before removing the original, unless `--keep-source` is set. Browser uploads preserve the original. Neither approach erases backups, filesystem history, deleted disk blocks, or previous agent conversations.

## Identity and local access

Agent requests require a bearer credential with an applicable object grant. Credentials have separate admin/agent roles and can have expiry dates. Generated example credentials have wildcard grants and no expiry.

The dashboard deliberately has no login gate. `POST /admin/session` issues an HttpOnly, SameSite=Strict cookie scoped to `/admin`. The cookie is not an agent credential, and an explicit bearer token retains its own role. The server binds to loopback and restricts browser origins. A local process can obtain an admin session: this convenience is not protection against a malicious local agent or another same-user process.

The calling agent separately supplies a user ID, name, roles, team, and purpose. These claims are marked `caller_supplied_unverified` and used to simulate user-aware policy. A caller can forge them. Production use would require authenticated user identity and delegated authority.

The MCP adapter limits file access to its configured workspace. The comparison runner exposes only a single-file tool and broker requests. Neither is an operating-system sandbox; a process with unrestricted same-user access may read broker keys or original files directly.

## Policy and model behavior

The broker sends **every source row and column to OpenAI**, including synthetic sensitive fields. There is no deterministic PII removal, SQL execution, generated-code execution, or model browsing. Organization restrictions take precedence over object policies in the broker prompt; interpretation remains probabilistic.

The LLM chooses an access mode and writes the response. It can leak information, overblock useful tasks, mislabel decisions, or miscalculate results. Structured Outputs constrains the response shape, not its correctness or confidentiality. Reported policy IDs and disclosed fields are advisory.

OpenAI inference is external. `store: false` is used, but it is not a zero-retention guarantee. See [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data).

## Audit behavior

A request snapshots its effective policy revisions. The broker records an attempted provider disclosure before the network call and persists the exact final response before returning it. If final audit storage fails, the response is withheld. Provider failures and invalid decisions do not fall back to plaintext.

Records identify what was prepared for release, not proof that the caller received or consumed it. An attempted provider call may fail before reaching OpenAI. Response hashes and encrypted records are not independent, tamper-evident receipts against a malicious broker administrator.

## Not yet provided

- Verified identity, SSO, external key management, or a trusted execution environment.
- Cumulative disclosure budgets or protection against inference across multiple requests.
- Control over an agent’s use of information after disclosure.
- Independent audit checkpoints or rollback protection.
- Remote deployment hardening or multi-process storage coordination.

Use one broker process per state directory. Keep local keys, credentials, runtime files, and transcripts out of Git. Tests use synthetic fixtures and record observed behavior; passing tests do not establish a universal security guarantee.
