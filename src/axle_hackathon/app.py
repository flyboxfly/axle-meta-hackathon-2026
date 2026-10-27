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
