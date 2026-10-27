# H1 test results — 2026-10-26

Executed `.venv/bin/python -m pytest -q`: **16 passed**.

Coverage includes known arithmetic ($420 / 240 miles = $1.75; target $480; gap $60), complete estimated costs $290 and surplus $130, acceptance/negotiation/decline gates, missing profile protection, invalid numeric values, prohibited caller-controlled profile fields, API authentication, OpenAPI generation, and bounded delegation behavior.

The protocol test uses fake model responses and real in-process FastAPI HTTP handling. It is NOT evidence of live Meta usage or a running network server.

Live Meta delegation: **PASS — owner-executed on Mac, output supplied in chat on 2026-10-26**. This runtime did not execute the paid request itself.

Owner's Python 3.14.10/macOS 15.7.9 run: **16 passed in 1.45s**.
Live model: `muse-spark-1.3`.
Final response ID: `resp_6adfbbba55652e7f476c4d8f`.
Tool request response ID: `resp_6adfbbac56664c8640db46b6`.
Tool call ID: `call_17af5947-5032-4957-bb1a-fad1cf82fd25`.
HTTP evaluation: POST /api/v1/freight/evaluate returned 200.
Tool execution status: executed_and_validated.
Result: 240 total miles; $2.33 loaded RPM; $1.75 all-mile RPM; $480 target revenue; $60 gap; NEED_MORE_INFORMATION. Unknown costs remained null.
Final-response usage reported 1,815 input and 1,313 output tokens (3,128 total). This is the final response's usage, not a verified aggregate of the full multi-request run.
Owner also supplied clean server shutdown output.
Public repository: **CREATED — flyboxfly/axle-meta-hackathon-2026**.
Deployment: **NOT PERFORMED**.
Native connector: **NOT IMPLEMENTED**.
H1 local functional acceptance: **PASS based on local tests and owner-supplied live evidence; public source publication performed separately after owner approval**.

Additional checks: actual loopback TCP server health/evaluation PASS; installed SDK initialization/Responses method PASS; pip check reports no broken requirements. A missing SOCKS proxy dependency found during SDK initialization was added before final verification. No outbound inference request was made.

## H2 owner-executed live verification — October 26, 2026

Owner reported 21 passing tests in 1.11 seconds on Mac. Screenshots supplied in this conversation show the browser progression using Muse Spark 1.3:

| Supplied scenario | Decision | All-mile RPM | Loaded RPM | Revenue gap | Estimated costs | Estimated operating surplus after allocated costs |
| --- | --- | --- | --- | --- | --- | --- |
| $420, 180 loaded + 60 additional miles, costs/schedule unknown | NEED_MORE_INFORMATION | $1.75 | $2.33 | $60 | unknown | unknown |
| Same opportunity; complete synthetic costs and feasible schedule | NEGOTIATE | $1.75 | $2.33 | $60 | $290 | $130 |
| Payout changed to $500; other facts retained | ACCEPT | $2.08 | $2.78 | $0 | $290 | $210 |

Expanded evidence in negotiation and acceptance screenshots identifies model `muse-spark-1.3`, tool `evaluate_freight_opportunity`, and status `executed_and_validated`. These are owner-supplied live execution records, not paid requests from the assistant workspace. Desktop rendering was visually inspected through owner screenshots; mobile rendering remains unverified. Owner reports local server stopped after verification.

Two earlier browser attempts displayed a generic delegation failure. A separate owner-executed direct diagnostic returned PASS: NEED_MORE_INFORMATION. No failing exception category was captured before later browser success; root cause remains unknown. Success after diagnostic instrumentation is not proof the instrumentation fixed the issue. No reliability rate or comprehensive live acceptance is claimed.

Follow-up local change replaces broad exception-text debugging with bounded server-side failure categories and numeric provider status only. Provider responses, arbitrary exception text, credentials and submitted facts are not logged. Offline tests verify this redaction. No automatic paid retries or timeout changes were introduced.

## H2 diagnostic verification and final candidate — October 27, 2026

Owner applied the safe diagnostic update, reported 21 passed in 1.49s, added three diagnostic regression cases, then reported **24 passed in 1.54s**. These cases confirm ValueError, RuntimeError and unexpected failures log a fixed category without the private exception text. Mac tests use a separate test_diagnostics.py; candidate tests consolidate those cases in test_h2.py. Exact Mac/candidate tree equality is not established. Diagnostics were verified offline, not by deliberately provoking a paid provider failure. Earlier live failures remain undiagnosed.

Final candidate: 24 offline cases rerun in the assistant workspace on October 27. No additional paid request made. See H2_REVIEW.md for the publication scope and remaining checks.

## H2 follow-up review — October 27, 2026

Assistant workspace: **28 passed** after four offline failure-injection cases for provider timeout, connection failure, provider HTTP 429 and invalid tool-schema data. Each verifies generic browser errors, safe category logging, exclusion of private exception text, lock release and successful next request using a fake client. No paid provider request made; earlier live failure root cause remains unknown. Owner Mac remains at 24 reported passing tests until the follow-up tests are installed there.

Mobile visual evidence: three owner-supplied Chrome responsive-emulation screenshots at 390 × 905 show the header, opportunity form, expanded costs/schedule form, button, initial decision panel and footer. Visible content fits and stacks without apparent clipping. Limited visual PASS only; evaluated metrics/evidence states, physical devices and broader interaction/accessibility testing remain unverified. No inference requested for this check.

## Final review correction — October 27, 2026

Review reproduced a 500 for an incorrect browser password containing a non-ASCII character. String compare_digest rejects non-ASCII text; browser authentication now compares UTF-8 byte sequences, preserving constant-time comparison. A regression case confirms that an incorrect non-ASCII password returns 401 with the Basic challenge. Assistant workspace: **29 tests pass**. No paid request or change to H1 bearer authentication. This correction is not yet installed in the owner's extracted Mac folder.

## H3 owner execution and final review — October 27, 2026

Owner Mac initial H3 suite: 50 passed in 2.06s. After preview/schema diagnostic patch: 50 passed in 1.99s. After structured-output/completion update: **56 passed in 2.10s**. No credentials were supplied to the assistant.

Earlier attempts: browser preview blocked by CSP; image request returned generic 502/tool_schema_validation. Preview permission was fixed. A subsequent safe diagnostic showed root json_invalid. Raw output was not recorded; exact invalid format is unknown. Strict Responses text.format, low reasoning effort and bounded 4096-token output replaced prompt-only JSON/1600 tokens. Successful execution followed, without proving which change resolved which generation problem.

Owner screenshot at 09:19:41 Eastern shows the synthetic screenshot, model muse-spark-1.3, extracted supporting text (26-foot box truck, $420, 180 loaded miles, 60 additional miles), mileage-confirmation caveat and a draft awaiting review. Screenshot at 09:22:19 shows review checked and confirmed values in form, followed by NEED_MORE_INFORMATION, all-mile RPM $1.75, loaded RPM $2.33, revenue-target gap $60 and unknown costs/surplus. Expanded evidence identifies evaluate_freight_opportunity with executed_and_validated status. Screenshots remain conversation evidence and are not included in the public candidate. Owner reported server stopped afterward.

This demonstrates one owner-executed synthetic screenshot → draft → confirmation → real delegation → canonical evaluation. It is not an assistant live call, an accuracy benchmark or proof of general repeated reliability. Successful mobile draft/evaluated states remain unverified.

Final candidate: **57 offline tests** in assistant workspace (29 H2 + 28 H3). The additional final test uses the installed OpenAI SDK and mocked HTTP to verify image and strict structured-output serialization without reaching Meta. It is not yet owner-executed. Dependencies, Python compilation, JavaScript syntax and whitespace checked. Complete binary patch is checked against an isolated H2 tree and every reconstructed source file is compared byte-for-byte before delivery.
