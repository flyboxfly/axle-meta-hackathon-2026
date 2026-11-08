# Authenticated GET probe — isolated release plan

Prepared November 8, 2026. Offline implementation; no deployment authorized.

## Source and isolation

Inspected main: ef8b1e5e5c41a8458111e6768598b78782c26a62.
Historical deployed pin: ef6baa65d9c6fed97daba83b1ad270aa9b5b0d13.
Repository H10 evidence records the latter; a public health 200 on November 8
confirms availability and no-store, but does not identify the running source.
Current Coolify pin/image digest and environment must be inspected privately,
read-only, before release approval. No infrastructure administration connection
was available in this implementation session. Do not infer the pin from health.

The main-to-historical-pin comparison has 91 changed files, including pilot work.
The remote module closure (__init__, remote_app, axle_api, schemas, economics),
Dockerfile.remote, Dockerfile.remote.dockerignore, remote lock and healthcheck
are byte-identical before this feature. Only remote_app changes at runtime.
Do not deploy main wholesale. Prepare a release commit rooted directly at the
verified deployed pin containing only this PR's remote_app patch. Record its
exact SHA and diff before requesting deployment approval. If the actual deployed
pin differs, stop and compare it first. Prepared isolated candidate: `15eea1148478ec41ebb65a2baeada2ce199e933f`,
branch `release/muse-probe-isolated`, parent exactly the historical pin above.
Its diff contains only remote_app.py (18 insertions, 3 deletions).
The draft PR records this candidate
SHA; that candidate is conditional on confirming the current deployed pin.

## Approved release procedure (not executed)

1. Obtain separate merge approval for the feature PR. Obtain read-only evidence
   of existing Coolify source pin, image digest, startup command, health status,
   network isolation and resource limits without exposing environment values.
2. Confirm the isolated release commit changes only remote_app versus that pin.
   Test it with the existing remote dependency lock and Python 3.11 container;
   the local Python environment is not a substitute for this container check.
3. Resolve credential ownership separately: one service-wide AXLE_API_TOKEN exists
   in code. No second-token/account mechanism is implemented. If it is already a
   dedicated synthetic-reviewer credential, owner may enter it privately. Otherwise
   obtain separate approval for a dedicated reviewer token/runtime change and
   identify affected clients first. Never print, read into chat, or commit its value.
4. Request approval naming exact release SHA, existing runtime config and rollback
   pin/image. Change only this synthetic application's source pin and redeploy
   that application. Keep Dockerfile, worker count, limits, environment, networks,
   firewall, shared proxy, website and databases unchanged. No proxy restart,
   Docker restart, VPS reboot or infrastructure changes.
5. Check health 200/no-store; verify missing/wrong Bearer 401, valid Bearer 200,
   forbidden host and Origin 403 where safely observable; run synthetic POST
   regression cases (targets 2.00, 1.75 and null). Keep secrets out of logs/output.
6. Owner privately enters label `Axle synthetic reviewer API`, API key/Bearer mode,
   raw service credential (after prefix handling is verified), and path
   `/api/v1/axle/verify`. Confirm API URL remains the documented base
   https://axle-api-demo.flyboxfly.com and record actual documentation URLs in
   Technical specs; repository values are evidence of intent, not portal readback.
   Observe the Test outcome without exposing credentials. Probe success establishes
   access only, not freight evaluation, native workflow compatibility or approval.
   Review any final submission action and obtain separate authorization.

## Rollback

On failed auth/health/evaluation smoke checks, restore the recorded prior source
pin/image for this application only and redeploy it with unchanged runtime config.
Confirm original health and synthetic POST behavior. No data migration exists.
The new GET will disappear (404) after rollback; do not submit its path until release
checks pass. A separately approved token change needs its own client/rollback plan.

## Documentation and evidence limits

Public guidelines checked November 8: https://platform.muse.ai/docs, sections
4.4 and 5.4–5.5 require secure credentials, documented behavior and dedicated test
access. The owner's observed GET help does not explicitly mandate authentication.
No successful Muse test, portal submission, credential issuance or live source-pin
verification is claimed. Application payload persistence remains absent;
infrastructure logging/retention remains incompletely verified.

## Offline validation

Python 3.12.14 virtualenv with requirements.lock.txt installed; no dependency changes.
`python -m pytest -q`: 401 passed.
Focused probe/H8/H11/H9 run: 72 passed.
`PYTHONPATH=src python scripts/export_reviewer_openapi.py --check`: passed.
`pip check` and `git diff --check`: passed.
No Docker binary was available; pinned Python 3.11 container build/run was not tested.
Public curl GET /api/health returned 200, application JSON and no-store.
This is availability evidence only, not authenticated live validation.

Isolated candidate source with current probe/H8/H7/H9 test files: 60 passed
using `python -m pytest -q -o pythonpath=/tmp/axle-probe-release/src` with
`tests/test_muse_probe.py tests/test_h8_remote.py tests/test_h7.py tests/test_h9_packaging.py`.
