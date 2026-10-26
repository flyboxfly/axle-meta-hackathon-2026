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
