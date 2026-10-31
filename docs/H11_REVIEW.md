# H11 — local Meta delegation to deployed Axle API

Base inspected: main `567c0d75db2e42258f976f1e8f414be6d0808ab1`.
GitHub branch inventory and open PRs were checked; no H11 branch/open PR existed.
No applicable AGENTS.md found in the checkout or available parent directories.
Branch: `feature/h11-remote-integration`.

## Implementation

- `remote_client.py`: server-side HTTPX adapter to the exact configured
  `https://axle-api-demo.flyboxfly.com`. Requires separate private runtime token;
  repr excludes the token. TLS verification on, environment proxies disabled,
  redirects off, no retry. Connect/pool timeouts 5s, read/write 10s per phase;
  these are inactivity/phase timeouts, not a strict total wall-clock deadline.
  Response size capped at 64 KiB, decoded in 4096-byte chunks. Requires JSON,
  no-store, full explicit provenance, synthetic profile, supported decision,
  matching source and confirmed target. No recomputation/local fallback.
- Browser mode is explicitly `AXLE_BROWSER_EVALUATOR=remote`; default `local`
  preserves legacy calculations. Invalid mode/config fails closed before Meta.
  The exact remote base URL and private `AXLE_REMOTE_API_TOKEN` are required.
  Local auth continues to use the separate `AXLE_DEMO_TOKEN`.
- Remote requests require strict `facts_confirmed: true` and confirmed benchmark,
  including explicit null target. Browser adds facts-review checkbox; fact changes
  and new screenshot/manual workflows invalidate it. Inherited benchmark schema
  now rejects coerced numeric/string confirmation values. Existing clients in
  local mode retain their behavior for actual boolean confirmations.
- Meta receives opportunity facts and user intent only, selects one completed
  recognized call, and must preserve all facts. Benchmark, confirmation authority,
  endpoint and bearer credential remain outside tool arguments.
- The local server executes one remote POST after validated selection. Canonical
  API envelope and `remote_https` / `deployed_axle_api` trace are delivered to the
  browser. The model does not receive the evaluation result in this browser slice;
  `model_received_result` stays false. No model-authored explanation is displayed.
  H7's separate loopback CLI round trip remains unchanged.
- Remote errors emit bounded fixed categories and return a fixed error to the
  browser, preserving inputs. No raw error bodies or secrets. Local host/client,
  Basic auth, Origin checks and paid budgets remain in force.
- Added static public reviewer docs, OpenAPI generator and checked-in JSON,
  Technical specs preparation and private local launcher. No dependencies added.

## Mac terminal — private live validation

After checking out this reviewed branch in the existing Mac worktree, activate
the existing virtual environment (owner verified `.venv` for this checkout).
Do not install Docker. From the repository root:

```sh
python -m pytest -q
PYTHONPATH=src python scripts/export_reviewer_openapi.py --check
PYTHONPATH=src python scripts/run_remote_browser.py
```

The launcher reuses existing environment values or prompts privately for the
Meta key, local browser password and existing remote token. No secret is saved
to disk, printed, or passed on the shell command line. Run it directly in your
own terminal, not through model-visible tool arguments. Stop any existing server
on port 8000 through its original terminal before launching; do not kill unknown
processes. Open http://127.0.0.1:8000 and sign in as `carrier` using only the local
demo password. Never expose this local app through a tunnel/public bind.

1. Upload the synthetic fixture and consent to Meta extraction. Compare/edit all
   four draft fields. Fill costs: diesel 4, MPG 10, tolls 20, driver 80,
   maintenance .10/mile, equipment 50, insurance 20; hours 6, schedule Yes.
2. Set target 2.00, confirm target, review/confirm opportunity facts, then confirm
   screenshot review last. Submit. Expect NEGOTIATE, gap 60, costs 290,
   surplus 130. Inspect evidence: `remote_https`, `deployed_axle_api`,
   canonical API provenance, model_received_result=false.
3. Change only target to 1.75, renew confirmations, submit. Expect ACCEPT, gap 0,
   unchanged costs/surplus. Then unknown target, renew confirmations, submit:
   NEED_MORE_INFORMATION, null target/gap, unchanged costs/surplus.
4. Respect shared local paid budget (4 attempts/minute including extraction).
   No automatic retry. Failures mean no verified new decision. Do not share
   secrets or screenshots of terminal configuration. Stop server with Ctrl-C.

Each extraction/evaluation spends Meta credits. Offline tests do not establish
live model compatibility, screenshot accuracy or public remote reliability.

## Validation evidence

Executed in the assistant Linux workspace with Python 3.12 and the unchanged
project lockfile in an isolated temporary virtual environment:

- Full suite: **183 passed in 2.51s** (157 existing + 26 H11 cases).
- Installed dependencies: `pip check` passed.
- Static OpenAPI regeneration `--check`: passed.
- Browser JavaScript syntax compilation with Node: passed.
- Python `compileall` for source/scripts and `git diff --check`: passed.
- Public GET health via curl with normal TLS verification: HTTP/2 200,
  `Cache-Control: no-store`, `{"status":"ok","synthetic_only":true}`.
  This is an unauthenticated health check, not the new adapter or Meta workflow.

Tests use fake Meta selections, HTTPX MockTransport and actual isolated API
handlers. They cover three target outcomes, private credential separation,
confirmation/config preflight, changed model facts, timeout/connection/status/
redirect/JSON/size/provenance failures, secret redaction, local-mode compatibility
and static contract drift. No paid inference or external authenticated request
is used by tests. Browser script syntax is not rendered/interactive UI QA.

### Owner-operated Mac live evidence — October 30, 2026 (America/New_York)

Tested checkout: `9733fd38ba0e6ba5066bd8e1b47c43810a71cc33`.
Owner terminal reported **183 passed in 4.08s**, static OpenAPI `--check`
succeeded in the chained command, and `pip check` reported no broken requirements.
The existing Mac environment is `.venv`.

Owner supplied browser screenshots after synthetic screenshot extraction and
carrier confirmation. All three live Meta-selected evaluations returned validated
public API envelopes. Each trace shows model `muse-spark-1.3`, tool
`evaluate_freight_opportunity`, `executed_and_validated`, `remote_https`,
`deployed_axle_api`, canonical UI delivery and `model_received_result: false`.

| Confirmed target | Decision | Target revenue | Revenue gap |
| --- | --- | --- | --- |
| 2.00 | NEGOTIATE | 480.00 | 60.00 |
| 1.75 | ACCEPT | 420.00 | 0.00 |
| Explicitly unknown | NEED_MORE_INFORMATION | null | null |

All cases retain 240 total miles, loaded RPM 2.33, all-mile RPM 1.75,
estimated costs 290.00 and operating surplus 130.00. Unknown-target evidence
shows `benchmark_source: carrier_unknown`, null target, missing
`carrier_revenue_target` and the corresponding next question. Returned envelopes
identify `source: screenshot`, synthetic profile `synthetic-box-001`,
`model_invoked: false` and `native_connector: false`. The model flag describes
the deterministic API evaluator; actual Meta tool selection is shown separately.

An initial live attempt failed with bounded category `authorization`; the UI
preserved inputs and displayed no decision. After the owner privately re-entered
the existing deployed API credential and restarted only the local launcher,
the three cases above succeeded. No credential value was shared in chat or
changed on the deployed service. This is authentication-failure recovery evidence,
not proof of which credential value was entered initially.

Evidence was reviewed from owner-operated browser screenshots, not direct access
to the Mac or independent network capture. It establishes the three demonstrated
live cases and interactive result rendering, not repeated reliability, exhaustive
visual/accessibility QA, independent extraction-accuracy measurement or native
Muse integration. Credentials remain owner-held and unavailable to this workspace.

## Native connector preparation

See [reviewer documentation](connector/README.md), [static contract](connector/openapi.json)
and [submission preparation](connector/SUBMISSION_PREPARATION.md).
The observed Raw API option supports this proposed submission path; it does not
verify bearer compatibility or credential delivery. Review-stage instructions,
dedicated reviewer access and pre-approval testing remain unresolved.

## Deployment boundary

No remote app, economics, request/response schema module, packaging, deployment
pin, runtime secret, VPS, firewall, network, database, Docker or shared proxy
change. Retain pin `ef6baa65d9c6fed97daba83b1ad270aa9b5b0d13`.
Repository pin identity comes from H10/owner handoff, not a fresh VPS inspection.
The website policy/branding release is separate and was not changed here.
No merge, redeployment, final connector submission or legal acceptance.
