# Axle × Meta — H1

Standalone hackathon implementation begun October 26, 2026. Built by a carrier, for carriers.

## Provenance and status

Axle's concept, brand, industry expertise, and production infrastructure predate this competition. This repository was written fresh for the competition; no production repository was cloned or read to implement it. FastAPI, Pydantic, HTTPX, OpenAI SDK, pytest, and their dependencies are third-party software, not original competition work.

Implemented: authenticated synthetic freight evaluation, decimal calculations, OpenAPI schema, bounded Responses API tool harness, offline tests. No native Muse/Meta connector, booking, production database, carrier data ingestion, or deployed service is claimed. A successful live Meta API tool run was executed by the owner on Mac and its output supplied in chat; see the verification record. Hosted model invocation is disabled. This H1 code is for loopback development; public deployment needs quotas, rate limiting, and further security review.

## Local setup

Python 3.11+. From this directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock.txt
pip install --no-deps -e .
pytest -q
```

Set `AXLE_DEMO_TOKEN` to a new local-only secret through your terminal or secret manager. Set `MODEL_API_KEY` the same way before running live inference. Never put secrets in source, screenshots, logs, or chat. `.env.example` documents names; this application does not automatically load `.env` files.

Start the API in one terminal with the local token set:

```sh
uvicorn axle_hackathon.app:app --host 127.0.0.1 --port 8000
```

Interactive OpenAPI docs: http://127.0.0.1:8000/docs . The evaluation route requires `Authorization: Bearer <local token>`. Server selects the sole synthetic profile; caller cannot choose another carrier.

In another terminal with both secrets set:

```sh
python -m axle_hackathon.meta_agent
```

The CLI uses `https://api.meta.ai/v1`, model `muse-spark-1.3`, and the Responses API. It requires model-selected tool execution; no fallback fabricates a model result. The tool calls the loopback HTTP evaluation endpoint. Failures exit nonzero; retries are disabled and each run has bounded model turns/output. API billing and live compatibility must be verified on the owner's account. This executes billable model requests when credentials are supplied.

## Financial meaning

Payout means complete confirmed compensation, including any already included bid/FSC. No additional compensation is inferred. All-mile RPM uses loaded plus supplied additional miles; include all relevant repositioning. Unknown costs remain null, never zero. Full costs include fuel, tolls, driver, maintenance, equipment, and allocated insurance. The remainder is estimated operating surplus after allocated costs, not guaranteed profit. The synthetic $2.00/mile revenue target is not a cost target.

Equipment categories stay distinct; only the synthetic box-truck profile currently supports a complete recommendation. Schedule feasibility is caller-supplied, not verified HOS or route clearance. A model explanation is advisory; the structured evaluation is authoritative. H1 does not independently validate every statement in generated prose.

## Verification

See docs/TEST_RESULTS.md and docs/HACKATHON_COMPLIANCE.md. Offline fake-model tests verify protocol behavior only. The owner supplied successful live Meta delegation evidence on 2026-10-26. Local H1 proof passes. This is the standalone public competition repository.
