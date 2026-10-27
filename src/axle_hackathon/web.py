"""Loopback-only carrier interface. No public deployment boundary is claimed."""
import base64
import logging
import os
from pathlib import Path
import secrets
import threading
import time
from collections import deque
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from .economics import evaluate
from .meta_agent import BASE_URL, MODEL, delegate
from .schemas import Opportunity

logger = logging.getLogger(__name__)
router = APIRouter()
_gate = threading.Lock()
_attempts = deque()

class WebRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(default="Ask Axle to evaluate this opportunity.", min_length=1, max_length=1500)
    opportunity: Opportunity


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
        valid = scheme.lower() == "basic" and user == "carrier" and secrets.compare_digest(password, token)
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise HTTPException(401, "Sign in locally", headers={"WWW-Authenticate": 'Basic realm="Axle local demo"'})


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(local_access)])
def interface():
    return HTMLResponse(Path(__file__).with_name("carrier.html").read_text(), headers={
        "Cache-Control": "no-store", "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})


def live_run(body: WebRequest):
    from openai import OpenAI
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise HTTPException(503, "Meta credentials are not configured on this server")
    canonical = body.opportunity
    executions = 0
    def execute(op):
        nonlocal executions
        executions += 1
        if executions > 1:
            raise ValueError("One evaluation per browser request")
        # The model must preserve every supplied fact, including unknowns.
        if op != canonical:
            raise ValueError("Delegated facts differ from confirmed carrier inputs")
        return evaluate(op)
    with OpenAI(api_key=key, base_url=BASE_URL, timeout=20, max_retries=0) as client:
        result = delegate(client, body.message + "\nConfirmed structured facts follow. Use these exactly; null means unknown.\n" + canonical.model_dump_json(), execute)
    if len(result["evaluations"]) != 1:
        raise ValueError("Expected exactly one freight evaluation")
    return {"model": MODEL, "evaluation": result["evaluations"][0], "trace": result["trace"],
            "response_id": result["response_id"], "integration": "Meta API prototype; no native connector"}


@router.post("/api/v1/browser/evaluate", dependencies=[Depends(local_access)])
def browser_evaluate(body: WebRequest):
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
            return live_run(body)
        except HTTPException:
            raise
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
