"""Local key registry, authenticated encryption, policy revisions, and audit persistence."""

import base64
import csv
import hashlib
import io
import json
import os
import re
import secrets
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def now():
    return datetime.now(UTC).isoformat()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    return json.loads(Path(path).read_text())


def seal(key, value: bytes, aad: str):
    nonce = secrets.token_bytes(12)
    return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, value, aad.encode())).decode()


def unseal(key, value, aad):
    raw = base64.b64decode(value)
    return AESGCM(key).decrypt(raw[:12], raw[12:], aad.encode())


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        for part in ("keys", "objects", "policies", "identities", "audit"):
            (self.root / part).mkdir(parents=True, exist_ok=True, mode=0o700)
        key_path = self.root / "keys/master.key"
        if not key_path.exists():
            if any((self.root / "objects").iterdir()) or any((self.root / "audit").iterdir()):
                raise RuntimeError(
                    "Master key missing for existing state; restore the original key."
                )
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(AESGCM.generate_key(bit_length=256))
        self.key = key_path.read_bytes()

    def initialize(self):
        path = self.root / "identities/credentials.json"
        with self.lock:
            if path.exists():
                raise ValueError("Already initialized. Existing credentials were not changed.")
            admin, agent = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            atomic_json(
                path,
                [
                    {
                        "id": "local-admin",
                        "hash": hashlib.sha256(admin.encode()).hexdigest(),
                        "kind": "admin",
                        "grants": ["*"],
                        "expires_at": None,
                    },
                    {
                        "id": "demo-agent",
                        "hash": hashlib.sha256(agent.encode()).hexdigest(),
                        "kind": "agent",
                        "grants": ["*"],
                        "expires_at": None,
                    },
                ],
            )
            # Local owner-only recovery file; never served by the broker.
            atomic_json(self.root / "keys/client-tokens.json", {"admin": admin, "agent": agent})
            return {"admin": admin, "agent": agent}

    def authenticate(self, token, kind):
        path = self.root / "identities/credentials.json"
        if not path.exists():
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        for item in read_json(path):
            if secrets.compare_digest(item["hash"], digest) and item["kind"] == kind:
                if item["expires_at"] and datetime.fromisoformat(
                    item["expires_at"]
                ) <= datetime.now(UTC):
                    return None
                return {k: v for k, v in item.items() if k != "hash"}
        return None

    def object(self, object_id):
        if not re.fullmatch(r"obj_[a-f0-9]{16}", object_id):
            raise FileNotFoundError("Object not found")
        return read_json(self.root / "objects" / f"{object_id}.json")

    def objects(self):
        return sorted(
            [read_json(p)["metadata"] for p in (self.root / "objects").glob("*.json")],
            key=lambda o: o["created_at"],
            reverse=True,
        )

    def protect(self, filename, content):
        if not content or len(content) > 100_000:
            raise ValueError("Upload a nonempty CSV smaller than 100 KB.")
        try:
            text = content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text), strict=True)
            fields = reader.fieldnames
            rows = list(reader)
            if not fields or len(fields) != len(set(fields)) or any(not f.strip() for f in fields):
                raise ValueError("CSV needs unique, nonempty headers.")
            if (
                len(fields) > 40
                or not rows
                or len(rows) > 500
                or any(None in r or None in r.values() for r in rows)
            ):
                raise ValueError("CSV must have 1–500 rectangular rows and at most 40 columns.")
        except (UnicodeError, csv.Error) as error:
            raise ValueError("Upload a valid UTF-8 CSV.") from error
        object_id = "obj_" + secrets.token_hex(8)
        data_key = AESGCM.generate_key(bit_length=256)
        meta = {
            "id": object_id,
            "name": Path(filename or "untitled.csv").name,
            "version": 1,
            "created_at": now(),
            "rows": len(rows),
            "fields": fields,
            "bytes": len(content),
            "cipher": "AES-256-GCM",
            "storage": "client-held",
        }
        artifact, record = self._encrypt(meta, data_key, content)
        atomic_json(self.root / "objects" / f"{object_id}.json", record)
        return artifact

    def _encrypt(self, metadata, data_key, content):
        from .artifact import aad, access_header, pack

        header = access_header(metadata)
        nonce = secrets.token_bytes(12)
        payload = nonce + AESGCM(data_key).encrypt(nonce, content, aad(header))
        artifact = pack(header, payload)
        key_aad = f"airlock-object-v1:{metadata['id']}:{metadata['version']}:key"
        record = {
            "metadata": metadata,
            "wrapped_key": seal(self.key, data_key, key_aad),
            "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
        }
        return artifact, record

    def decrypt(self, object_id, artifact):
        from cryptography.exceptions import InvalidTag

        from .artifact import aad, unpack

        header, payload = unpack(artifact)
        obj = self.object(object_id)
        if "ciphertext" in obj:
            raise ValueError(
                "Legacy object: export it using airlock migrate before requesting access."
            )
        if header["object_id"] != object_id or header["version"] != obj["metadata"]["version"]:
            raise ValueError("Artifact does not match the requested object/version.")
        if not secrets.compare_digest(hashlib.sha256(artifact).hexdigest(), obj["artifact_sha256"]):
            raise ValueError("Artifact has been altered or does not match this object.")
        key_aad = f"airlock-object-v1:{object_id}:{header['version']}:key"
        try:
            key = unseal(self.key, obj["wrapped_key"], key_aad)
            return AESGCM(key).decrypt(payload[:12], payload[12:], aad(header))
        except InvalidTag as error:
            raise ValueError("Artifact authentication failed.") from error

    def migrate(self, output_dir):
        """Export legacy ciphertext durably before removing it from the key registry."""
        from .artifact import aad, unpack

        output_dir = Path(output_dir).resolve()
        if output_dir.is_relative_to(self.root.resolve()):
            raise ValueError("Export artifacts outside the broker state directory.")
        exported = []
        for meta in self.objects():
            obj = self.object(meta["id"])
            if "ciphertext" not in obj:
                continue
            old_aad = f"{meta['id']}:{meta['version']}"
            key = unseal(self.key, obj["wrapped_key"], old_aad + ":key")
            plaintext = unseal(key, obj["ciphertext"], old_aad)
            meta = {**meta, "storage": "client-held"}
            artifact, record = self._encrypt(meta, key, plaintext)
            header, payload = unpack(artifact)
            assert AESGCM(key).decrypt(payload[:12], payload[12:], aad(header)) == plaintext
            directory = output_dir / meta["id"]
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / (meta["name"] + ".airlock")
            if target.exists():
                raise ValueError(
                    f"Migration target exists: {target}. Preserve it and choose a fresh directory."
                )
            fd, temporary = tempfile.mkstemp(dir=directory)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(artifact)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(temporary, target)
                directory_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                os.unlink(temporary)
            # Only now discard the broker's copy; old keys and policies retain their identities.
            atomic_json(self.root / "objects" / f"{meta['id']}.json", record)
            exported.append({"object_id": meta["id"], "file": str(target)})
        return exported

    def policies(self):
        result = []
        for directory in (self.root / "policies").iterdir():
            if directory.is_dir():
                revisions = sorted(directory.glob("*.json"))
                if revisions:
                    result.append(read_json(revisions[-1]))
        return sorted(result, key=lambda p: (p["scope"] != "organization", p["created_at"]))

    def save_policy(self, value, policy_id=None):
        with self.lock:
            if value["scope"] == "object":
                self.object(value["object_id"] or "")
            elif value.get("object_id"):
                raise ValueError("Organization policies cannot target an object.")
            old = None
            if policy_id:
                old = next((p for p in self.policies() if p["id"] == policy_id), None)
                if not old:
                    raise FileNotFoundError("Policy not found")
                if (old["scope"], old["object_id"]) != (value["scope"], value["object_id"]):
                    raise ValueError("Policy scope is immutable. Create a new policy instead.")
            result = {
                **value,
                "id": policy_id or "pol_" + secrets.token_hex(8),
                "revision": old["revision"] + 1 if old else 1,
                "created_at": old["created_at"] if old else now(),
                "updated_at": now(),
            }
            atomic_json(
                self.root / "policies" / result["id"] / f"{result['revision']:08}.json", result
            )
            return result

    def effective(self, object_id):
        return [
            p
            for p in self.policies()
            if p["enabled"] and (p["scope"] == "organization" or p["object_id"] == object_id)
        ]

    def save_event(self, event):
        with self.lock:
            encrypted = seal(self.key, json.dumps(event).encode(), event["id"])
            atomic_json(
                self.root / "audit" / f"{event['id']}.json",
                {"id": event["id"], "encrypted": encrypted},
            )

    def event(self, event_id):
        if not re.fullmatch(r"req_[a-f0-9]{16}", event_id):
            raise FileNotFoundError("Event not found")
        item = read_json(self.root / "audit" / f"{event_id}.json")
        return json.loads(unseal(self.key, item["encrypted"], item["id"]))

    def events(self):
        return sorted(
            [self.event(p.stem) for p in (self.root / "audit").glob("*.json")],
            key=lambda e: e["started_at"],
            reverse=True,
        )
