# H3 final review — October 27, 2026

Status: LOCAL REVIEW CANDIDATE. H3 publication, merge and deployment are not authorized by preparation alone.

Repository: https://github.com/flyboxfly/axle-meta-hackathon-2026

Baseline: merged H2 `5f9c188fe4d30d248fe1bded361a216abcb8beaa`, rechecked against public main October 27. Local branch: `feature/h3-screenshot-intake`.

## Final behavior

Carrier selects one synthetic PNG/JPEG, explicitly permits sending it to Meta, and requests extraction. Muse Spark 1.3 receives normalized image pixels through Responses input_image; strict text.format JSON Schema constrains the draft shape. No freight tool is exposed during extraction. The server independently validates values with Pydantic. Missing facts remain null; facts without supporting text are cleared. Quoted supporting text is model-reported, not independent OCR proof.

Draft facts populate editable equipment, complete payout, loaded miles and additional miles fields. Prior costs, schedule and results are cleared. Carrier must review/correct every fact and confirm before screenshot-marked evaluation. Edits invalidate confirmation. Different files clear prior draft/results; failure applies no draft. Manual entry remains available. The confirmation flag is an authenticated carrier assertion, not proof that a review occurred; manual evaluation remains supported.

The separate evaluation runs the unchanged H2 model delegation and deterministic evaluator. Complete payout is counted once, costs remain unknown when absent, and schedule is user-supplied. Only the synthetic box-truck profile can support a complete decision. Power Only remains distinct from carrier-owned trailers. ACCEPT is neither booking nor regulatory clearance.

## Changes and boundaries

- New vision.py: image validation/metadata stripping, strict extraction request, schema/numeric validation and bounded completion/schema diagnostics.
- web.py: shared paid-request guard, screenshot route, confirmation assertion validation, local blob-preview CSP permission. Existing bearer API and disabled general agent route remain unchanged.
- carrier.html: file preview, synthetic-data consent, draft review and explicit confirmation, missing-fact entry, reset/loading/failure/manual states.
- Pinned Pillow 12.3.0 in project and lock snapshot. New synthetic screenshot plus reproducible generator. New tests and verification documentation.
- H1 economics.py, schemas.py, meta_agent.py and all existing tests are unchanged.

Local-only H2 authentication, client/Host/Origin checks apply. Extraction/evaluation share one process-local concurrency slot and four attempts/minute. Extraction uses one model request, low reasoning effort, max_output_tokens 4096, 20-second SDK request timeout and no retry. These are per-request/activity controls, not a public-service wall-clock or multi-worker quota design.

Raw image stream capped at 4 MiB; normalized image also capped. PNG/JPEG MIME must match decoded format; single frame only, maximum edge 4096 pixels and maximum 8 million pixels. Pixel reconstruction strips metadata/comments/EXIF/profiles after applying orientation. No external image URLs, Files API, OCR service or new inference provider.

Application does not save or log uploads. Meta receives pixels under its service/account retention policies; zero provider retention is not claimed. API credentials stay server-side. Raw model text, private exception bodies and reasoning are not logged/displayed; fixed statuses, error types, approved paths, text length and format booleans support diagnostics. Synthetic consent is not an automated sensitive-data detector.

## Verification

Assistant workspace: **57 offline tests pass**, including all 29 H2 tests. Coverage includes image size/format/animation/metadata, strict request shape and SDK serialization through mocked HTTP transport, null/invalid data, auth/Origin/consent, shared budgets, confirmation, privacy-safe diagnostics and incomplete/non-JSON output. Fake provider tests do not establish live vision accuracy.

Owner Mac: 50 passed after initial H3 install; **56 passed in 2.10s** after format/preview/diagnostic update. The additional SDK serialization case belongs to this final candidate and has not been run on Mac. Full Mac/candidate tree equality is not claimed; candidate snapshot/checksums define proposed publication bytes.

Owner live evidence: screenshots at 09:19:41 and 09:22:19 Eastern show synthetic image extraction, review confirmation and successful evaluation with Muse Spark 1.3. Facts: 26-foot box truck; $420 complete payout; 180 loaded miles; 60 additional miles. Evaluation: NEED_MORE_INFORMATION; $1.75 all-mile RPM; $2.33 loaded RPM; $60 gap; unknown costs/surplus. Expanded freight evidence shows evaluate_freight_opportunity and executed_and_validated. Owner subsequently reported stopping the server. These are owner-executed records, not assistant-paid calls. See TEST_RESULTS.md.

Assistant inspected supplied desktop screenshots and the earlier 390 × 905 H3 mobile preview/failure-state screenshots. No apparent clipping in the shown portions; narrow buttons wrap. Successful draft/evaluated H3 mobile states and physical-device/accessibility QA remain unverified. Scratch jsdom checks passed for consent, busy state, draft population, confirmation, evaluation, edit invalidation, reset, failure and manual fallback; these are page-logic checks, not rendered QA. Actual loopback smoke passed for protected HTML, missing-key and consent failures. Dependency, compilation, JavaScript syntax and diff whitespace checks pass.

## Earlier failures and practical limits

Initial blob preview was blocked by missing img-src blob policy; fixed and visually confirmed by owner. Initial prompt-only JSON extraction failed validation. A later safe diagnostic established json_invalid at the root but did not capture whether output was empty, fenced, truncated or malformed. Strict structured output, low reasoning effort and a larger bounded budget preceded success. Do not claim a uniquely proven cause or reliability rate. H2's earlier intermittent failures also remain unexplained.

One clearly labeled synthetic fixture is not a representative OCR/vision benchmark. Ambiguous base/bid/FSC, illegible screenshots, unseen layouts and prompt injection have not been live-benchmarked. Instructions and human review reduce risk but do not guarantee extraction accuracy. All-mile additional miles must be confirmed for actual positioning. No real carrier or production data was used.

## Proposed publication

After approval, publish candidate on feature/h3-screenshot-intake and open a draft PR to main.

Title: H3: add confirmed screenshot intake with structured Muse Spark extraction

Description: Carriers can upload a synthetic freight screenshot, review/correct Muse Spark's draft, explicitly confirm facts and delegate evaluation to Axle. Adds bounded image validation, strict extraction schema, sanitized diagnostics and confirmation-aware UI using existing local auth/paid limits. Validation: 57 offline tests, owner Mac 56 tests, and owner-supplied successful extraction-to-evaluation screenshots. Earlier JSON/preview failures and remaining reliability/mobile limits are recorded. Local prototype only; no native connector or public deployment claimed.

Approval to publish does not authorize merge, deployment, new paid tests, production access or credential changes. No H3 remote mutation performed during this preparation.

## Primary technical references

Checked October 27, 2026:
- https://dev.meta.ai/docs/image-understanding
- https://dev.meta.ai/docs/cookbook/vision-input
- https://dev.meta.ai/docs/structured-output
- https://dev.meta.ai/docs/protocols/responses

Full competition rules, track and infrastructure reuse remain unconfirmed per H1; this milestone does not resolve eligibility.
