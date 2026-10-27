# H2 final review — October 27, 2026

Status: LOCAL REVIEW CANDIDATE. No H2 branch, PR, merge or deployment has been published.

## Baseline and scope

Repository: https://github.com/flyboxfly/axle-meta-hackathon-2026

GitHub main rechecked October 27: `334cf35d0c3c1d6c97b0a44f204169bf62de5424`, matching the local base. Local feature branch: `feature/h2-carrier-interface`.

Adds a carrier HTML/CSS/JavaScript interface served by FastAPI, protected local browser evaluation, staged costs/schedule entry, canonical decision figures, previous-result comparison, sanitized tool evidence, and bounded diagnostic logging. Only the synthetic box-truck profile supports a complete decision. Model prose is not displayed. Tool inputs must equal all confirmed structured facts; unknowns stay unknown. The web tool calls the H1 evaluator in process; the H1 CLI retains its HTTP path.

Unchanged H1 implementation: evaluator, schemas, Meta delegation harness, fixture, dependency lock and existing tests. App registration and package data are extended. Git ignore rules exclude Mac virtual environments and diagnostic backups.

## Validation and evidence

- Assistant workspace: 24 offline pytest cases pass; pip check, Python compilation, JavaScript syntax and diff whitespace checks pass.
- Owner Mac: initially 21 passed in 1.11s; after safe diagnostic update and three added regression cases, 24 passed in 1.54s (owner-supplied output).
- Owner live browser screenshots show NEED_MORE_INFORMATION → NEGOTIATE → ACCEPT with correct canonical figures. Expanded negotiation and acceptance evidence shows Muse Spark 1.3, evaluate_freight_opportunity and executed_and_validated. See TEST_RESULTS.md.
- Assistant previously executed actual loopback TCP health, protected HTML and missing-key failure checks. Assistant made no paid inference requests.
- Desktop layout inspected through owner screenshots. Mobile rendering, keyboard/screen-reader QA and independent browser automation remain pending; browser download failed in this environment.

The owner's extracted folder includes an equivalent diagnostic patch and separate tests/test_diagnostics.py; the candidate keeps the three regression cases in tests/test_h2.py. Their complete file trees have not been hash-compared. The candidate archive is the exact proposed publication source, not a claim of byte-for-byte Mac synchronization.

## Local security boundary

Browser sign-in uses carrier + AXLE_DEMO_TOKEN through HTTP Basic on loopback. MODEL_API_KEY stays server-side. Host/client address and Origin checks apply. One concurrent browser evaluation and four attempts/minute/process; one executed tool/request; bounded model turns/output; 20-second SDK request timeout with no retries. No persistent conversations, arbitrary tool URLs or caller-selected carrier identity. No public proxy/tunnel exposure is authorized. This is not a public judge-demo deployment design.

Failure logs contain fixed categories and numeric provider status only; no exception text, provider bodies, credentials, prompts or facts. Browser errors stay generic. Diagnostic regression cases cover ValueError, RuntimeError and unexpected exceptions; live provider failure categories are not independently exercised on the owner account.

## Unresolved limits

Two earlier browser failures were not captured with actionable exception categories. A direct live diagnostic passed and later browser runs succeeded. Root cause remains UNKNOWN; adding diagnostics is not evidence of a fix. No automatic retries or timeout changes were introduced. Do not claim reliable repeated live execution from three successful scenarios.

Schedule is supplied, not independently verified for route/HOS/legal clearance. ACCEPT means implemented economic/schedule checks pass; it does not book freight. Estimated surplus includes allocated costs and is not guaranteed profit. No native Muse/Meta connector is claimed. Full rules, track and infrastructure reuse remain unconfirmed per H1.

## Proposed publication

After owner approval: publish this candidate on feature/h2-carrier-interface and open a draft PR targeting main. Proposed title: H2: add local carrier interface and verified freight reevaluation.

PR description: Carriers can enter confirmed freight facts, delegate through Muse Spark to Axle, add missing costs and reevaluate. Canonical results show missing information, negotiation or supplied checks passing without displaying unverified model arithmetic. Adds loopback browser authentication, concurrency/rate limits and sanitized failure diagnostics. Validation: 24 offline tests; owner-supplied Mac live screenshots for the three states. Earlier intermittent failures remain undiagnosed; mobile QA and public deployment remain out of scope.

Publication approval does not authorize merging, deployment, paid tests, credential changes or production access.
