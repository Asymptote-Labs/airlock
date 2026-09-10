"""Command-line entry points for protecting files and requesting context."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx

from .artifact import MAX_SOURCE_BYTES, read_artifact, unpack
from .storage import Store


def protect(args):
    source = Path(args.file).absolute()
    target = (
        Path(args.output).absolute() if args.output else source.with_name(source.name + ".airlock")
    )
    if source.is_symlink() or not source.is_file():
        raise ValueError("Input must be a regular readable CSV file, not a symlink.")
    if target.suffix != ".airlock":
        raise ValueError("Output must use the .airlock extension.")
    if target.exists() or target.is_symlink() or target.resolve() == source.resolve():
        raise ValueError("Output already exists or is the source file; refusing to overwrite.")
    if not target.parent.is_dir():
        raise ValueError("Output directory does not exist.")
    token = os.environ.get("AIRLOCK_ADMIN_TOKEN")
    if not token:
        raise ValueError("Set AIRLOCK_ADMIN_TOKEN to your admin credential.")
    with source.open("rb") as file:
        content = file.read(MAX_SOURCE_BYTES + 1)
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError("CSV exceeds the 100 KB demo limit.")
    original_hash = hashlib.sha256(content).hexdigest()
    with httpx.Client(
        base_url=os.environ.get("AIRLOCK_BROKER_URL", "http://127.0.0.1:8100"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
        follow_redirects=False,
    ) as client:
        result = client.post("/admin/objects", files={"file": (source.name, content, "text/csv")})
        if result.status_code != 200:
            raise ValueError(
                f"Upload rejected ({result.status_code}): {result.json().get('detail', 'Unknown error')}"
            )
        artifact = result.content
        header, _ = unpack(artifact)
        object_id = header["object_id"]
        if hashlib.sha256(artifact).hexdigest() != result.headers.get("X-Airlock-SHA256"):
            raise ValueError("Artifact checksum mismatch; source retained.")
        verified = client.post(
            f"/admin/objects/{object_id}/verify",
            files={"file": (target.name, artifact, "application/vnd.airlock")},
        )
        verified.raise_for_status()
        if verified.json().get("plaintext_sha256") != original_hash:
            raise ValueError("Round-trip verification failed; source retained.")
    fd, temporary = tempfile.mkstemp(dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(artifact)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as error:
        raise ValueError(
            "Could not save the artifact. Source retained; the broker does not retain a downloadable copy."
        ) from error
    finally:
        os.unlink(temporary)
    if not getattr(args, "keep_source", False):
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != original_hash:
            raise ValueError(
                f"Protected file saved at {target}, but source changed during protection and was retained."
            )
        source.unlink()
    print(
        f"Protected object: {object_id}\nClient-held artifact: {target}\n"
        + (
            "Source retained (--keep-source)."
            if getattr(args, "keep_source", False)
            else "Original replaced after verified encryption and durable artifact save."
        )
    )


def main():
    parser = argparse.ArgumentParser(prog="airlock")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create broker keys and local demo credentials")
    init.add_argument("--state-dir", default=os.environ.get("AIRLOCK_STATE_DIR", ".airlock"))
    serve = sub.add_parser("serve", help="Run the local broker and built dashboard")
    serve.add_argument("--port", type=int, default=8100)
    command = sub.add_parser(
        "protect", help="Replace a CSV with a verified client-held .airlock artifact"
    )
    command.add_argument("file")
    command.add_argument("--output")
    command.add_argument(
        "--keep-source",
        action="store_true",
        help="Keep the original plaintext (e.g. for the baseline demo)",
    )
    inspect = sub.add_parser(
        "inspect", help="Read only the artifact instructions, without ciphertext"
    )
    inspect.add_argument("file")
    ask = sub.add_parser(
        "ask", help="Upload a .airlock artifact and return a natural-language answer"
    )
    ask.add_argument("file")
    ask.add_argument("--question", required=True)
    ask.add_argument("--provenance", help="Path to caller-supplied user JSON; unknown if omitted")
    migrate = sub.add_parser(
        "migrate", help="Export legacy broker-held objects to client artifacts"
    )
    migrate.add_argument("--output-dir", required=True)
    seed = sub.add_parser("seed", help="Generate a deterministic synthetic census")
    seed.add_argument("--output", default="demo-workspace/employee_census.csv")
    sub.add_parser("mcp", help="Run the thin MCP adapter over stdio")
    demo = sub.add_parser(
        "demo", help="Run a fresh requesting agent with a file or .airlock artifact"
    )
    demo.add_argument("file")
    demo.add_argument("--question", default="Which employees have upcoming birthdays?")
    demo.add_argument("--trace", required=True, help="Save the synthetic-data tool transcript")
    args = parser.parse_args()
    try:
        if args.command == "init":
            Store(args.state_dir).initialize()
            print(
                f"Initialized {args.state_dir}. Owner-only credentials: {args.state_dir}/keys/client-tokens.json"
            )
        elif args.command == "serve":
            import uvicorn

            uvicorn.run(
                "airlock.app:create_app",
                factory=True,
                host="127.0.0.1",
                port=args.port,
                access_log=False,
            )
        elif args.command == "protect":
            protect(args)
        elif args.command == "inspect":
            _, header = read_artifact(args.file)
            print(json.dumps(header, indent=2))
        elif args.command == "ask":
            from .adapter import request_broker
            from .models import UserProvenance

            provenance = UserProvenance.model_validate(
                json.loads(Path(args.provenance).read_text()) if args.provenance else {}
            ).model_dump()
            print(request_broker(args.file, args.question, provenance))
        elif args.command == "migrate":
            store = Store(os.environ.get("AIRLOCK_STATE_DIR", ".airlock"))
            print(json.dumps(store.migrate(args.output_dir), indent=2))
        elif args.command == "seed":
            from .seed import generate

            generate(Path(args.output))
            print(f"Synthetic census: {args.output} (reference date: 2026-09-10)")
        elif args.command == "mcp":
            from .adapter import run

            run()
        elif args.command == "demo":
            from .demo import run

            run(args)
    except (ValueError, OSError, httpx.HTTPError) as error:
        print(f"airlock: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
