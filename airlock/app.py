"""HTTP API, local dashboard sessions, and the audited access-request pipeline."""

import hashlib
import os
import secrets
import time
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.formparsers import MultiPartException, MultiPartParser

from . import inference
from .artifact import MAX_ARTIFACT_BYTES, unpack
from .models import ContextRequest, Decision, PolicyInput
from .storage import Store, now


def create_app(state_dir=None, evaluator=None):
    app = FastAPI(title="Airlock", docs_url=None, redoc_url=None, openapi_url=None)
    store = Store(state_dir or os.environ.get("AIRLOCK_STATE_DIR", ".airlock"))
    app.state.store = store
    evaluator = evaluator or inference.evaluate
    dashboard_session = secrets.token_urlsafe(32)

    @app.middleware("http")
    async def headers(request, call_next):
        origin = request.headers.get("origin")
        port = request.url.port or 80
        allowed = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        }
        if origin and origin not in allowed:
            return JSONResponse({"detail": "Browser origin not allowed."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    def auth(kind):
        def dependency(request: Request):
            token = request.headers.get("authorization", "").removeprefix("Bearer ")
            # Local demo: the dashboard starts an admin session automatically.
            # Explicit bearer credentials keep their own role and never inherit it.
            if kind == "admin" and not request.headers.get("authorization"):
                cookie = request.cookies.get("airlock_dashboard", "")
                if secrets.compare_digest(cookie, dashboard_session):
                    return {"id": "local-dashboard", "kind": "admin", "grants": ["*"]}
            identity = store.authenticate(token, kind)
            if not identity:
                # Record authentication failures without retaining attacker-controlled content.
                store.save_event(
                    {
                        "id": "req_" + secrets.token_hex(8),
                        "started_at": now(),
                        "finished_at": now(),
                        "status": "authentication_rejected",
                        "origin": "authentication",
                        "mode": "deny",
                        "credential_identity": None,
                        "response": "Invalid or expired credential.",
                        "policies": [],
                    }
                )
                raise HTTPException(401, "Invalid or expired credential.")
            return identity

        return dependency

    admin, agent = auth("admin"), auth("agent")

    @app.exception_handler(FileNotFoundError)
    async def missing(request, error):
        return JSONResponse({"detail": "Resource not found."}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/admin/session")
    def start_dashboard_session():
        # Deliberately unauthenticated convenience for this local-only prototype.
        response = Response(status_code=204)
        response.set_cookie(
            "airlock_dashboard", dashboard_session, httponly=True, samesite="strict", path="/admin"
        )
        return response

    @app.get("/admin/status")
    def status(identity=Depends(admin)):
        return {
            "identity": identity["id"],
            "model": os.environ.get("AIRLOCK_MODEL", "gpt-6-astra"),
            "api_key_configured": bool(os.environ.get("OPENAI_API_KEY")),
            "reference_date": os.environ.get("AIRLOCK_DEMO_DATE")
            or datetime.now(UTC).date().isoformat(),
        }

    async def read_form(request):
        if (
            request.headers.get("content-type", "").split(";", 1)[0].lower()
            != "multipart/form-data"
        ):
            raise HTTPException(
                422, "Send multipart/form-data with a file and, for access, request JSON."
            )
        # Bound the complete body before multipart parsing. Even UploadFile's temporary
        # spool stays in RAM because its threshold exceeds this enforced total limit.
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_ARTIFACT_BYTES + 30_000:
                raise HTTPException(413, "Upload exceeds the demo request limit.")

        async def chunks():
            yield bytes(raw)

        parser = MultiPartParser(
            request.headers, chunks(), max_files=1, max_fields=1, max_part_size=25_000
        )
        parser.spool_max_size = MAX_ARTIFACT_BYTES + 30_001
        try:
            return await parser.parse()
        except MultiPartException as error:
            raise HTTPException(
                422, "Send multipart/form-data with a file and, for access, request JSON."
            ) from error

    async def uploaded_bytes(form):
        file = form.get("file")
        if not hasattr(file, "read"):
            raise HTTPException(422, "Missing file upload.")
        return await file.read(), file.filename

    @app.post("/admin/objects")
    async def upload(request: Request, identity=Depends(admin)):
        form = await read_form(request)
        try:
            content, filename = await uploaded_bytes(form)
            artifact = await run_in_threadpool(store.protect, filename, content)
            header, _ = unpack(artifact)
            return Response(
                artifact,
                media_type="application/vnd.airlock",
                headers={
                    "X-Airlock-Object-ID": header["object_id"],
                    "X-Airlock-SHA256": hashlib.sha256(artifact).hexdigest(),
                },
            )
        finally:
            await form.close()

    @app.post("/admin/objects/{object_id}/verify")
    async def verify_artifact(object_id: str, request: Request, identity=Depends(admin)):
        form = await read_form(request)
        try:
            artifact, _ = await uploaded_bytes(form)
            plaintext = await run_in_threadpool(store.decrypt, object_id, artifact)
            return {
                "object_id": object_id,
                "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
            }
        finally:
            await form.close()

    @app.get("/admin/objects")
    def objects(identity=Depends(admin)):
        return store.objects()

    @app.get("/admin/objects/{object_id}")
    def object_detail(object_id: str, identity=Depends(admin)):
        return {**store.object(object_id)["metadata"], "policies": store.effective(object_id)}

    @app.get("/admin/policies")
    def policies(identity=Depends(admin)):
        return store.policies()

    @app.post("/admin/policies")
    def create_policy(body: PolicyInput, identity=Depends(admin)):
        return store.save_policy(body.model_dump())

    @app.patch("/admin/policies/{policy_id}")
    def update_policy(policy_id: str, body: PolicyInput, identity=Depends(admin)):
        return store.save_policy(body.model_dump(), policy_id)

    @app.get("/admin/events")
    def events(object_id: str | None = None, mode: str | None = None, identity=Depends(admin)):
        return [
            e
            for e in store.events()
            if (not object_id or e.get("object_id") == object_id)
            and (not mode or e.get("mode") == mode)
        ]

    @app.get("/admin/events/{event_id}")
    def event(event_id: str, identity=Depends(admin)):
        return store.event(event_id)

    def process(body, identity, origin, artifact):
        started = time.monotonic()
        reference_date = os.environ.get("AIRLOCK_DEMO_DATE") or datetime.now(UTC).date().isoformat()
        date.fromisoformat(reference_date)
        event = {
            "id": "req_" + secrets.token_hex(8),
            "started_at": now(),
            "origin": origin,
            "credential_identity": identity["id"],
            "object_id": body.object_id,
            "question": body.question,
            "purpose": body.purpose,
            "user_provenance": body.user_provenance.model_dump(),
            "provenance_status": "caller_supplied_unverified",
            "reference_date": reference_date,
            "prompt_version": inference.PROMPT_VERSION,
            "policies": [],
            "status": "started",
        }
        code = 200
        try:
            if "*" not in identity["grants"] and body.object_id not in identity["grants"]:
                raise HTTPException(403, "Credential does not grant access to this object.")
            obj = store.object(body.object_id)["metadata"]
            event.update(
                object_name=obj["name"],
                object_version=obj["version"],
                source_fields=obj["fields"],
                source_rows=obj["rows"],
            )
            event["policies"] = store.effective(body.object_id)
            if not event["policies"]:
                raise HTTPException(
                    403, "No active policies. Ask the administrator to configure access."
                )
            plaintext = store.decrypt(body.object_id, artifact).decode("utf-8-sig")
            payload = {
                "question": body.question,
                "purpose": body.purpose,
                "user_provenance": event["user_provenance"],
                "provenance_status": event["provenance_status"],
                "credential_identity": identity["id"],
                "reference_date": reference_date,
                "policies": event["policies"],
                "csv": plaintext,
            }
            event["provider_exposure"] = (
                "Full decrypted object supplied to OpenAI; no columns removed."
            )
            # Persist attempted provider disclosure before the network call.
            event["status"] = "provider_attempted"
            store.save_event(event)
            try:
                decision, provider = evaluator(payload)
                decision = Decision.model_validate(decision).model_dump()
                if not decision["response"].strip():
                    raise ValueError("Empty response")
            except Exception as error:
                raise RuntimeError("Provider inference failed") from error
            event.update(decision)
            event.update(provider)
            event["status"] = "prepared_for_release"
        except HTTPException as error:
            code = error.status_code
            event.update(mode="deny", response=error.detail, status="rejected")
        except ValueError as error:
            code = 400
            event.update(mode="deny", response=str(error), status="rejected")
        except FileNotFoundError:
            code = 404
            event.update(mode="deny", response="Object not found.", status="rejected")
        except Exception as error:
            code = 502
            # Do not echo provider exceptions, which may contain sensitive request data.
            event.update(
                mode="deny",
                response="Airlock could not safely complete this request. Retry or contact the administrator.",
                status="error",
                error_type=type(error).__name__,
            )
        event.update(
            finished_at=now(),
            latency_ms=round((time.monotonic() - started) * 1000),
            response_sha256=hashlib.sha256(event["response"].encode()).hexdigest(),
            delivery_status="Prepared response; client consumption is not confirmed.",
        )
        try:
            store.save_event(event)
        except Exception:
            raise HTTPException(503, "Audit storage unavailable; response was not released.")
        return JSONResponse(
            {"request_id": event["id"], "response": event["response"]}, status_code=code
        )

    async def access(request, identity, origin):
        form = await read_form(request)
        try:
            artifact, _ = await uploaded_bytes(form)
            data = form.get("request")
            if not isinstance(data, str):
                raise HTTPException(
                    422, "Missing request field: send the request metadata as a JSON string."
                )
            try:
                body = ContextRequest.model_validate_json(data)
            except ValidationError as error:
                raise HTTPException(
                    422, "Invalid request JSON. Consult the request schema in the artifact header."
                ) from error
            return await run_in_threadpool(process, body, identity, origin, artifact)
        finally:
            await form.close()

    @app.post("/v1/context/request")
    async def context(request: Request, identity=Depends(agent)):
        return await access(request, identity, "agent")

    @app.post("/admin/playground")
    async def playground(request: Request, identity=Depends(admin)):
        return await access(request, identity, "playground")

    dist = Path(__file__).resolve().parent.parent / "web/dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def dashboard():
            return FileResponse(dist / "index.html")

    return app
