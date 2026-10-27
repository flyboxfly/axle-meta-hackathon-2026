# Axle × Meta — local freight prototype

## H6 fresh-page rehearsal

Owner screenshots on merged main a0f82ec verify fresh-page screenshot extraction,
confirmed $2.00 NEGOTIATE → target-only $1.75 ACCEPT, unchanged $290 estimated
costs/$130 estimated operating surplus, and canonical delivery trace. This closes
the specific fresh-page gap below, not repeated-run reliability. See
[H6 review](docs/H6_REVIEW.md) and the updated [demo plan](docs/DEMO_PLAN.md).
H6 changes documentation only; final recording and judge access remain pending.

## H5 browser completion (historical verification)

The browser now requests one completed model-selected freight tool call, validates
its arguments against confirmed carrier facts, and executes Axle's deterministic
evaluation. It displays the canonical result directly. It does **not** send that
result back to Muse Spark or request a model-authored final answer. Expanded
delegation evidence records `result_delivery: canonical_ui` and
`model_received_result: false`; its response ID identifies tool selection.

This supersedes earlier descriptions of a bounded multi-turn loop for the browser.
The H1 CLI retains the full tool-result/model-response loop. Screenshot extraction
remains a separate request. Model selection is still required; no forced call,
simulated success, partial-response fallback or automatic paid retry is added.
Incomplete responses/calls, missing/multiple/unknown calls, altered facts and failed
calculations fail closed. Browser timeout remains 20 seconds per SDK request.

Owner diagnostics on H5 head 25fd9f0 located one timeout in the second request,
after one validated evaluation (20011 ms). This candidate removes that browser
dependency; it does not establish provider root cause or repeated-run reliability.
93 offline tests pass, also confirmed on the owner's Mac at eddfdbb. Owner live
screenshots verify $1.75 ACCEPT and unknown-target NEED_MORE_INFORMATION using
preserved screenshot-derived facts, unchanged $290 costs/$130 estimated operating
surplus, and explicit canonical-UI evidence. Extraction/$2.00 evaluation were
obtained earlier on main; a fresh-page full sequence and repeated-run reliability
remain unverified. See docs/H5_REVIEW.md for evidence and review boundaries.

Standalone hackathon implementation begun October 26, 2026. Built by a carrier, for carriers.

## Provenance and status

Axle's concept, brand, industry expertise, and production infrastructure predate this competition. This repository was written fresh for the competition; no production repository was cloned or read to implement it. FastAPI, Pydantic, HTTPX, OpenAI SDK, pytest, and their dependencies are third-party software, not original competition work.

Implemented: authenticated synthetic freight evaluation, decimal calculations, OpenAPI schema, bounded Responses API tool harness, offline tests. No native Muse/Meta connector, booking, production database, carrier data ingestion, or deployed service is claimed. A successful live Meta API tool run was executed by the owner on Mac and its output supplied in chat; see the verification record. H2 adds a protected local browser workflow with real model delegation and canonical result presentation. The original agent route remains disabled. Public deployment requires a separate security design and approval.

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

## H2 local carrier interface

Start the same server with both `MODEL_API_KEY` and `AXLE_DEMO_TOKEN` present in its shell, then open http://127.0.0.1:8000 . Browser sign-in: username `carrier`, password is your existing local demo token. Keep this token private; enter it only in the browser's local authentication dialog. No token is embedded in HTML or JavaScript. Use the Python.org Python installation on Mac; no Homebrew installation is needed. Existing `.venv-h1` users can activate it and run `python -m pip install --no-deps -e .` after updating the source.

1. Submit the prefilled synthetic $420 / 180 loaded / 60 additional mile example.
2. Expect missing information, $1.75 all-mile RPM, $2.33 loaded RPM, and a $60 revenue gap.
3. Open **Add costs & schedule**. For a clearly synthetic complete example enter diesel 4, MPG 10, tolls 20, driver cost 80, maintenance 0.10/mile, equipment 50, insurance 20, hours 6, schedule Yes.
4. Reevaluate: expected estimated costs $290, operating surplus $130, NEGOTIATE.
5. Change confirmed synthetic payout to $500 and reevaluate: expected ACCEPT, with the stated economic/schedule limitations.

Every submission makes live, billable Meta requests. There is no offline success mode in the interface. Credentials remain server-side; the browser uses HTTP Basic authentication over loopback only. Host, client address and Origin are checked; do not expose this service through a tunnel, proxy, public bind address, or public deployment. Limits: one concurrent browser evaluation, four attempts per minute per process, one executed tool per request, existing bounded model turns/output, 20-second SDK request timeout, no retries. Restarting resets the local limiter. This is not a public judge-demo security design.

The browser submits explicit structured facts with a short intent. Muse selects the freight tool; delegated inputs must equal confirmed facts exactly. The tool invokes the same deterministic evaluator in process (H1 CLI retains its HTTP path). Model prose is not displayed: concise decision copy and figures come from canonical results. No shared conversation history is stored. Reevaluation resubmits the full form. Previous result comparison is browser-local. Costs stay unknown when blank. Other equipment choices require a matching profile and cannot pass acceptance.

The original `/api/v1/agent` remains disabled. H2 uses the separately protected `/api/v1/browser/evaluate`. The owner completed the three live browser scenarios on Mac on October 26, 2026; see docs/TEST_RESULTS.md. Two earlier failures remain undiagnosed. Offline tests do not establish live reliability.

## H3 local screenshot intake (review candidate)

Use only synthetic screenshots with no personal details, carrier IDs or credentials. Install the updated requirements (adds pinned Pillow 12.3.0), then run the same loopback server. Read docs/H3_REVIEW.md for exact scope and limitations.

The page now accepts one PNG/JPEG up to 4 MiB. Select the included `fixtures/synthetic_freight_screenshot.png`, check the synthetic-data consent, then click **Read screenshot with Muse Spark**. This is one live, billable extraction request, not a freight evaluation. Read the supporting text/issues, compare and edit the facts below, fill any missing mileage and select equipment if unknown. Check **I reviewed and corrected…**, then submit through the existing evaluation flow (a separate live delegation). Extraction and evaluation share the local paid-request budget.

Changing facts invalidates screenshot confirmation. A new screenshot clears prior costs, schedule and results. On extraction failure no draft is applied; use **Use manual entry** to clear the upload workflow and enter facts manually. Model-reported supporting text is not independent OCR proof. Ambiguous payout and unshown miles stay unknown; never add a displayed bid/FSC twice. No screenshots are saved by the application; image pixels are sent to Meta under its service/account policies.

For the synthetic fixture, expect draft payout $420, loaded miles 180, additional miles 60, and 26-foot box truck. After carrier confirmation, unknown expenses/schedule should produce NEED_MORE_INFORMATION. The owner supplied a successful live screenshot extraction and confirmed-facts evaluation on October 27, 2026. See docs/TEST_RESULTS.md. This single synthetic example does not establish general screenshot accuracy or repeated-run reliability.

H3 extraction now uses strict Responses `text.format` JSON Schema, low reasoning effort and a bounded 4096-token output budget. Empty, incomplete and invalid results fail closed; only bounded format/status diagnostics are logged. The initial version relied on prompt-only JSON and failed parsing on the owner's live attempt; the earlier preview policy also blocked blob images. Both implementation gaps were corrected before the successful run. The exact form of the earlier invalid JSON is unknown.

## H4 carrier-confirmed benchmarks (local review)

The browser now requires a target choice and confirmation for each evaluation. Enter an all-mile **revenue** target, or select **I don’t know yet** to enter known costs without inventing a target. No benchmark is saved. Changing the target clears confirmation and displayed results. Screenshot changes clear opportunity facts/costs as before, but preserve the separate carrier benchmark.

The authenticated browser request carries `benchmark` separately from `opportunity`. Only the server closure passes it into deterministic calculations. Neither screenshot extraction nor the model tool schema accepts a benchmark. Numeric targets must be greater than zero, at most $100/mile, and have at most two decimal places; this is a demo validation range, not an industry recommendation. Unknown targets produce null target revenue/gap and NEED_MORE_INFORMATION, even when all costs are supplied. Returned results identify benchmark source.

Compatibility: H1 API/CLI and older browser requests omitting `benchmark` retain the explicitly labeled $2.00 synthetic default. The new browser always sends an explicit confirmed choice, including null for unknown. Confirmation is an authenticated assertion, not independent verification. The synthetic equipment/profile restriction remains.

Owner verification after approved publication and checkout: run `python -m pytest -q`, start the usual loopback server, then use the complete $420 / 240-mile / $290-cost example above. Confirm $2.00/mile: NEGOTIATE, target $480, gap $60. Change only target to $1.75, reconfirm and reevaluate: ACCEPT, target $420, gap $0. Choose unknown, confirm and reevaluate: NEED_MORE_INFORMATION, unknown target/gap, unchanged $290 costs and $130 surplus. Each evaluation is billable; pause if the shared local limit is reached. For screenshot testing, confirm the target choice before the final screenshot confirmation.

## H7 axleAPI local preview (unpublished candidate)

`POST /api/v1/axle/evaluate` adds a confirmed external-client contract without
invoking a model. Supply `opportunity`, required `benchmark` with
`target_all_mile_rpm` (decimal string or null) and `confirmed: true`, plus
`facts_confirmed: true` and `source: "manual"` or `"screenshot"`.
Use the existing local bearer token. Only loopback use is supported.

Returns canonical `evaluation`, field-linked `next_questions`, schema version,
source and explicit caller-assertion/delivery provenance. Null target remains
unknown; no synthetic default is silently applied on this new route. Existing
routes retain their behavior. Only the synthetic box-truck profile is supported.
See [H7 review](docs/H7_REVIEW.md) for tests, authority and remaining remote work.
This endpoint alone is not native Muse integration or a demonstrated agent round trip.

### H7 external delegation harness (local follow-up candidate)

`python -m axle_hackathon.external_agent` tests model-selected delegation through
the new loopback HTTP API, followed by sending the canonical result back to the
model. Requires both existing credentials, running local server, and explicit
CONFIRM of the displayed synthetic case. Up to two paid requests, no automatic
retry. Success requires completed follow-up; failure never becomes partial success.
No native Muse connector is claimed; model prose is not validated or displayed.
See H7_REVIEW.md before running. Browser behavior is unchanged.

### H7 owner live verification

On published d842e32, owner Mac reported 121 passing tests and demonstrated a
real Muse Spark 1.3 tool selection → loopback HTTP axleAPI → canonical result
return → completed model follow-up. Result: NEGOTIATE, $60 gap, $290 costs and
$130 estimated operating surplus after allocated costs. Model prose was not
validated or displayed. This later evidence supersedes earlier pending local
round-trip statements; remote/native integration and repeated reliability remain
unverified. See H7_REVIEW.md. Server stopped cleanly after verification.
