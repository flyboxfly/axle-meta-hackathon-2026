import os
import secrets
from fastapi import Depends, FastAPI, Header, HTTPException
from .economics import evaluate
from .schemas import AgentRequest, Evaluation, Opportunity

app = FastAPI(title="Axle Hackathon Freight API", version="0.1.0")


def authorize(authorization: str = Header(default="")) -> None:
    token = os.environ.get("AXLE_DEMO_TOKEN")
    if not token:
        raise HTTPException(503, "Demo authorization is not configured")
    if not secrets.compare_digest(authorization, "Bearer " + token):
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})


@app.get("/api/health")
def health():
    return {"status": "ok", "synthetic_only": True}


@app.get("/api/v1/capabilities")
def capabilities():
    return {"tools": ["evaluate_freight_opportunity"], "synthetic_only": True,
            "supported_profile": "synthetic-box-001", "native_connector": False}


@app.post("/api/v1/freight/evaluate", response_model=Evaluation, dependencies=[Depends(authorize)])
def evaluate_route(opportunity: Opportunity):
    return evaluate(opportunity)


@app.post("/api/v1/agent", dependencies=[Depends(authorize)])
def agent_route(request: AgentRequest):
    # H1 harness only: no public paid-model endpoint until quotas/rate limiting exist.
    raise HTTPException(501, "Use the local CLI delegation harness; hosted model invocation is not enabled")

# Separate local browser boundary; the H1 bearer API and CLI remain available.
from .web import router
app.include_router(router)

# New external-client contract is a local preview until remote access is reviewed.
from .axle_api import (AxleEvaluationRequest, AxleEvaluationResponse,
                       evaluate_for_client, local_api_access)


@app.post("/api/v1/axle/evaluate", response_model=AxleEvaluationResponse,
          operation_id="evaluate_confirmed_freight_opportunity",
          dependencies=[Depends(authorize), Depends(local_api_access)])
def axle_evaluate_route(body: AxleEvaluationRequest):
    """Evaluate confirmed synthetic freight facts; no booking, storage or model call.

    Caller must obtain carrier review before asserting confirmation. Confirmation
    is a caller assertion, not independently verified consent or identity.
    Unknown costs and explicitly unknown revenue targets remain unknown.
    """
    from fastapi.responses import JSONResponse
    return JSONResponse(evaluate_for_client(body).model_dump(mode="json"),
                        headers={"Cache-Control": "no-store"})
