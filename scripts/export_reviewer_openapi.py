"""Generate static reviewer contract; never imports/enables the runtime app."""
import json
from pathlib import Path
import sys

from axle_hackathon.axle_api import AxleEvaluationRequest, AxleEvaluationResponse, evaluate_for_client
from axle_hackathon.external_agent import synthetic_request


def document():
    schemas = {}
    for model, mode in ((AxleEvaluationRequest, "validation"), (AxleEvaluationResponse, "serialization")):
        schema = model.model_json_schema(mode=mode, ref_template="#/components/schemas/{model}")
        schemas.update(schema.pop("$defs", {}))
        schemas[model.__name__] = schema
    schemas["ConfirmedBenchmark"]["properties"]["confirmed"]["const"] = True
    schemas["AxleEvaluationRequest"]["properties"]["facts_confirmed"]["const"] = True
    schemas["Evaluation"]["properties"]["synthetic"]["const"] = True
    schemas["Evaluation"]["properties"]["profile_id"]["const"] = "synthetic-box-001"
    schemas["Evaluation"]["properties"]["decision"]["enum"] = ["ACCEPT", "NEGOTIATE", "NEED_MORE_INFORMATION", "DECLINE"]
    # Runtime JSON always emits these defaults; do not hide provenance from reviewers.
    for name in ("AxleEvaluationResponse", "Evaluation"):
        schemas[name]["required"] = list(schemas[name]["properties"])
    errors = {str(code): {"description": description, "content": {"application/json": {
        "schema": {"type":"object", "properties":{"detail":{"type":"string"}}, "required":["detail"]}}}}
        for code, description in ((401,"Unauthorized; WWW-Authenticate: Bearer"),
            (403,"Host forbidden or Origin header present"), (408,"Body read timeout"),
            (413,"Request exceeds 32768 bytes"), (422,"Invalid request"),
            (429,"Global rate or concurrency limit"), (500,"Internal error"))}
    return {"openapi":"3.1.0", "info":{"title":"Axle synthetic evaluation API",
        "version":"1.0", "description":"Static reviewer contract. No native Muse integration or approval claimed. Synthetic-only; no booking, payments, model calls or application storage."},
        "servers":[{"url":"https://axle-api-demo.flyboxfly.com"}],
        "paths":{"/api/health":{"get":{"operationId":"health", "responses":{"200":{"description":"Health; not proof of evaluation authorization", "content":{"application/json":{"schema":{"type":"object", "properties":{"status":{"const":"ok"},"synthetic_only":{"const":True}},"required":["status","synthetic_only"]}}}},"403":errors["403"],"500":errors["500"]}}},
            "/api/v1/axle/evaluate":{"post":{"operationId":"evaluate_confirmed_freight_opportunity",
                "summary":"Evaluate carrier-confirmed synthetic freight facts",
                "description":"Proposed Read classification, subject to Meta review. Obtain carrier review before setting facts_confirmed and benchmark.confirmed. Null target is an explicit confirmed unknown. No Origin header. No booking or persistence.",
                "security":[{"bearerAuth":[]}],
                "requestBody":{"required":True,"content":{"application/json":{"schema":{"$ref":"#/components/schemas/AxleEvaluationRequest"},"example":synthetic_request().model_dump(mode="json")}}},
                "responses":{"200":{"description":"Evaluation completed, including NEED_MORE_INFORMATION; Cache-Control: no-store", "content":{"application/json":{"schema":{"$ref":"#/components/schemas/AxleEvaluationResponse"},"example":evaluate_for_client(synthetic_request()).model_dump(mode="json")}}},**errors}}}},
        "components":{"securitySchemes":{"bearerAuth":{"type":"http","scheme":"bearer","description":"Private server-side credential; provision only through a verified secure review flow. No OAuth/scopes or self-service accounts implemented."}},"schemas":schemas}}


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "docs/connector/openapi.json"
    rendered = json.dumps(document(), indent=2) + "\n"
    if "--check" in sys.argv:
        if not target.exists() or target.read_text() != rendered:
            raise SystemExit("Static contract differs; regenerate and review")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered)
