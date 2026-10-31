# H12 — truthful demo presentation

Base: main `38bf1ae534a7717e103b9e49927f8b37de4a4387`.
Branch: `feature/h12-demo-story`.

## Inspection

Fresh GitHub main/branch inventory and open PR search matched the H11 handoff;
no open PR existed at inspection. Fresh clone was clean. No applicable AGENTS.md
was found in the repository or available ancestor paths. Read H11 adapter,
launcher, static contract generator, web flow, carrier HTML, integration tests,
review notes and connector preparation before editing.

## Changes

- Explicit simulated Muse-facing interface label and four numbered demo steps.
- Returned-evidence summary distinguishes deployed HTTPS execution from the
  legacy local evaluator. It is shown only with a successful current result;
  edits, pending work and errors hide the result container.
- Mileage explanation uses confirmed input amounts and canonical total miles;
  no new economic computation or model-authored explanation.
- Connector docs record the October 31 owner handoff: initial Submitted,
  business Approved, questionnaire In review, Technical details Action needed.
  Credential UI observed, key empty, reviewer provisioning deferred. Historical
  preparation is marked as historical; initial terms/submission is not repeated.
- Recording plan now describes real deployed evaluation, simulation labeling,
  current confirmation order, and remaining recording/judge-access work.

No backend, economics, schema, dependency, deployment, credential, infrastructure
or product website change. No second model round trip, replay mode, fabricated
live result, or automated retries added. Deployed pin remains outside this change.

## Validation — assistant Linux, October 31

- Existing lockfile installed in isolated `/tmp/axle-h12-venv`; no repo dependency change.
- Full pytest suite: **183 passed in 2.79s**.
- `pip check`, static OpenAPI `--check`, browser JavaScript syntax compilation,
  and `git diff --check`: passed.
- One-off jsdom execution of the actual inline script: passed target 2.00 /
  NEGOTIATE / gap 60.00; 1.75 / ACCEPT / gap 0.00; explicit unknown /
  NEED_MORE_INFORMATION / unknown gap; confirmation invalidation; hidden stale
  results; failure preserving payout; and local provenance avoiding deployed
  execution claims. Five mocked fetch calls; zero Meta/deployed API calls.
  jsdom was installed outside the repo for this check only.
- Playwright rendering was attempted but Chromium download returned invalid
  archives. No rendered screenshots, mobile layout or accessibility QA passed
  in this session. DOM checks do not substitute for visual browser verification.

## Owner Mac review after PR review

Fetch this branch into the existing checkout without discarding local changes.
Run `.venv/bin/python -m pytest -q` and
`PYTHONPATH=src .venv/bin/python scripts/export_reviewer_openapi.py --check`.
Stop the known local server using Ctrl+C in its original terminal, then launch
`PYTHONPATH=src .venv/bin/python scripts/run_remote_browser.py`.
Keep prompts private and browser loopback-only. No deployment is required.

Rehearse with the synthetic screenshot and H11 figures. Confirm target, reviewed
facts, screenshot last. Inspect the new simulation label, numbered sequence,
RPM explanation and execution summary. Exercise the three targets within the
four-attempt/minute shared paid budget; each extraction/evaluation spends credits.
Check desktop/mobile layout and readable evidence before recording. H11 live
screenshots remain evidence for H11; H12 owner live evidence is recorded below.

Merge and any deployment remain owner approval steps. Native connector credential
provisioning remains separate and deferred.

## Owner-operated H12 evidence — October 31, 2026, America/New_York

Tested branch head before this documentation update:
`e2c7a235736a1895979c96ddc423f9c511295840`.
Owner terminal reported **183 passed in 4.07s**. The requested static OpenAPI
check produced no reported error; no separate exit-status capture was supplied.

Owner screenshots at approximately 9:43–9:52 show the opening disclosure,
simulation label, numbered sequence and three live screenshot-source results:

| Confirmed target | Decision | Target revenue | Gap |
| --- | --- | --- | --- |
| 2.00 | NEGOTIATE | 480.00 | 60.00 |
| 1.75 | ACCEPT | 420.00 | 0.00 |
| Explicitly unknown | NEED_MORE_INFORMATION | null | null |

All retain 240 total miles, loaded RPM 2.33, all-mile RPM 1.75, costs 290.00
and surplus 130.00. Unknown target retains `carrier_unknown`, missing
`carrier_revenue_target`, and its next question. Target-change comparisons
render correctly. Screenshots alone do not establish the intermediate
confirmation-invalidation interaction; that remains covered by offline checks.

Each expanded trace shows `muse-spark-1.3`, recognized freight tool,
`executed_and_validated`, `remote_https`, `deployed_axle_api`, canonical delivery,
and `model_received_result: false`. API provenance shows synthetic box profile,
`source: screenshot`, `model_invoked: false`, `native_connector: false`.
The API model flag describes the deterministic evaluator, not external Meta
selection. This evidence is owner-operated UI evidence, not independent
network capture, repeated reliability or native connector execution.

Owner Chrome responsive screenshots at approximately 9:53–9:55 use a
390 × 905 emulated viewport. Header, 2 × 2 steps, screenshot preview,
confirmations, form, stacked result, economics, execution summary, wrapped JSON
and footer remain within the visible content width without apparent clipping.
Upload buttons wrap heavily into multiple lines but remain legible; this is
minor polish, not an observed blocker. These are desktop Chrome emulation
screenshots, not physical-device, touch, keyboard or accessibility testing.
The Network panel was empty; it adds no request-capture evidence. The retained
unknown-target result is the same evaluation, not another live run.

No new code change or paid rerun was needed for this documentation update.
Remaining: owner merge approval, final timed recording and judge access plan.
