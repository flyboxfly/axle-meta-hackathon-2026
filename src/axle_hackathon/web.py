"""Loopback-only carrier interface. No public deployment boundary is claimed."""
import base64
import logging
import os
from pathlib import Path
import secrets
import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Literal
from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from .axle_api import AxleEvaluationRequest, ConfirmedBenchmark
from .remote_client import RemoteFailure, browser_transport, load_client_config, evaluate_remote
from .economics import evaluate
from .meta_agent import BASE_URL, MODEL, delegate_for_browser
from .schemas import Opportunity

logger = logging.getLogger(__name__)
router = APIRouter()
_gate = threading.Lock()
_attempts = deque()

class CarrierBenchmark(ConfirmedBenchmark):
    """Authenticated form assertion, separate from model tool and screenshot facts."""


class WebRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(default="Ask Axle to evaluate this opportunity.", min_length=1, max_length=1500)
    opportunity: Opportunity
    benchmark: CarrierBenchmark | None = None
    source: Literal["manual", "screenshot"] = "manual"
    screenshot_confirmed: bool = False
    facts_confirmed: StrictBool = False

    @model_validator(mode="after")
    def require_screenshot_confirmation(self):
        if self.source == "screenshot" and not self.screenshot_confirmed:
            raise ValueError("Confirm the extracted screenshot facts before evaluation")
        return self


def local_access(request: Request):
    if request.url.hostname not in {"127.0.0.1", "localhost"} or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "Local browser access only")
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Same-origin access required")
    token = os.environ.get("AXLE_DEMO_TOKEN")
    if not token:
        raise HTTPException(503, "Set the local demo token before opening the interface")
    try:
        scheme, value = request.headers.get("authorization", "").split(" ", 1)
        user, password = base64.b64decode(value, validate=True).decode().split(":", 1)
        valid = scheme.lower() == "basic" and user == "carrier" and secrets.compare_digest(password.encode("utf-8"), token.encode("utf-8"))
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise HTTPException(401, "Sign in locally", headers={"WWW-Authenticate": 'Basic realm="Axle local demo"'})


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(local_access)])
def interface():
    return HTMLResponse(Path(__file__).with_name("carrier.html").read_text(), headers={
        "Cache-Control": "no-store", "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})


def live_run(body: WebRequest):
    from openai import OpenAI
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise HTTPException(503, "Meta credentials are not configured on this server")
    mode = browser_transport()
    remote_config = None
    remote_request = None
    remote_result = None
    if mode == "remote":
        if body.benchmark is None or not body.facts_confirmed:
            raise HTTPException(422, "Confirm the opportunity facts and revenue target choice before remote evaluation")
        remote_config = load_client_config()
        remote_request = AxleEvaluationRequest(opportunity=body.opportunity,
            benchmark=body.benchmark, facts_confirmed=body.facts_confirmed, source=body.source)
    canonical = body.opportunity
    executions = 0
    def execute(op):
        nonlocal executions, remote_result
        executions += 1
        if executions > 1:
            raise ValueError("One evaluation per browser request")
        # The model must preserve every supplied fact, including unknowns.
        if op != canonical:
            raise ValueError("Delegated facts differ from confirmed carrier inputs")
        if mode == "remote":
            remote_result = evaluate_remote(remote_request, remote_config)
            return remote_result.evaluation
        if body.benchmark is None:
            # Compatibility for H1/H2 clients; explicitly labeled synthetic default.
            return evaluate(op)
        return evaluate(op, target=body.benchmark.target_all_mile_rpm,
                        benchmark_source="carrier_confirmed" if body.benchmark.target_all_mile_rpm is not None else "carrier_unknown")
    with OpenAI(api_key=key, base_url=BASE_URL, timeout=20, max_retries=0) as client:
        result = delegate_for_browser(client, body.message + "\nConfirmed structured facts follow. Use these exactly; null means unknown.\n" + canonical.model_dump_json(), execute)
    if len(result["evaluations"]) != 1:
        raise ValueError("Expected exactly one freight evaluation")
    for item in result["trace"]:
        item["transport"] = "remote_https" if mode == "remote" else "in_process"
        item["evaluation_origin"] = "deployed_axle_api" if mode == "remote" else "local_evaluator"
    extra = {"canonical_api_result": remote_result.model_dump(mode="json")} if remote_result is not None else {}
    return {"model": MODEL, "evaluation": result["evaluations"][0], "trace": result["trace"],
            "response_id": result["response_id"], "integration": "Meta API prototype; no native connector", **extra}


@contextmanager
def paid_slot():
    if not _gate.acquire(blocking=False):
        raise HTTPException(429, "An evaluation is running. Please wait.")
    try:
        now = time.monotonic()
        while _attempts and now - _attempts[0] > 60:
            _attempts.popleft()
        if len(_attempts) >= 4:
            raise HTTPException(429, "Local limit reached. Try again in one minute.")
        _attempts.append(now)
        try:
            yield
        except HTTPException:
            raise
        except RemoteFailure as exc:
            logger.warning("Axle remote evaluation failed category=%s", exc.category)
            code = 503 if exc.category == "configuration" else 502
            raise HTTPException(code, "Remote Axle evaluation could not be verified. Your inputs are preserved; no local fallback was used.") from None
        except Exception as exc:
            # Log only bounded metadata, never provider bodies, tool arguments or secrets.
            from openai import APITimeoutError, APIConnectionError, APIStatusError
            from pydantic import ValidationError
            category = "unexpected_error"
            status = None
            if isinstance(exc, APITimeoutError):
                category = "provider_timeout"
            elif isinstance(exc, APIConnectionError):
                category = "provider_connection"
            elif isinstance(exc, APIStatusError):
                category = "provider_status"
                status = exc.status_code if isinstance(exc.status_code, int) else None
            elif isinstance(exc, ValidationError):
                category = "tool_schema_validation"
            elif isinstance(exc, ValueError):
                category = "delegation_validation"
            elif isinstance(exc, RuntimeError):
                category = "delegation_protocol"
            logger.warning("Axle delegation failed category=%s status=%s", category, status)
            raise HTTPException(502, "Meta delegation could not be verified. Your inputs are preserved; try again.") from None
    finally:
        _gate.release()


@router.post("/api/v1/browser/evaluate", dependencies=[Depends(local_access)])
def browser_evaluate(body: WebRequest):
    with paid_slot():
        return live_run(body)


@router.post("/api/v1/browser/screenshot", dependencies=[Depends(local_access)])
async def screenshot_route(request: Request):
    from .vision import MAX_IMAGE_BYTES, extract_screenshot
    if request.headers.get("x-axle-synthetic") != "true":
        raise HTTPException(422, "Confirm that this screenshot contains synthetic, non-sensitive data")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {"image/png", "image/jpeg"}:
        raise HTTPException(415, "Use a PNG or JPEG screenshot")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Choose one image up to 4 MiB")
        raw.extend(chunk)
    def run():
        with paid_slot():
            return extract_screenshot(bytes(raw), content_type)
    from fastapi.responses import JSONResponse
    return JSONResponse(await run_in_threadpool(run), headers={"Cache-Control": "no-store"})
