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
screenshots remain evidence for H11; H12 has not had a new live Mac rehearsal.

Merge and any deployment remain owner approval steps. Native connector credential
provisioning remains separate and deferred.
