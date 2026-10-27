# H5 local review — October 27, 2026

## Owner verification of published browser completion — October 27

Owner approved the browser completion follow-up. Published H5 draft PR #4 head:
eddfdbb6278f35830204b19d02db6bfe5834860e. All nine published files matched the tested
local candidate. Owner Mac synchronized to eddfdbb and reported 93 passed in 3.00s;
loopback server started as process 46035.

Owner preserved the existing screenshot-derived form across restart. 14:00:00 and
14:01:36 screenshots were pre-submission settings, not a paid request or failure.
The latter shows screenshot confirmation unchecked and neutral edited-result state.
After confirmation, 14:02:57 screenshot shows ACCEPT with confirmed $1.75 target,
$1.75 all-mile RPM, $2.33 loaded RPM, $0 gap, $290 estimated costs and $130 estimated
operating surplus after allocated costs. Comparison retains prior successful main
$2.00 NEGOTIATE result ($60 gap). Expanded evidence shows Muse Spark 1.3,
executed_and_validated, canonical_ui, model_received_result=false.

14:11:28 screenshot showed disabled submission with enabled inputs during unknown
target setup; no request/failure is established from that screenshot. Owner then
reported completion. 14:12:29 result screenshot shows NEED_MORE_INFORMATION,
unknown target/gap, unchanged $290 costs/$130 surplus and next question requesting
a confirmed revenue target. Comparison is ACCEPT → NEED_MORE_INFORMATION with
$1.75 → unknown, $0 → unknown, missing facts 0 → 1. Expanded evidence again shows
executed_and_validated, canonical_ui and model_received_result=false.

These two successful evaluations are owner-executed live evidence on eddfdbb, not
assistant-paid calls. They validate updated selection/output compatibility and the
preserved screenshot-derived benchmark adjustment/unknown paths. Extraction and
$2.00 result were obtained earlier on main, not rerun on eddfdbb. Fresh-page full
sequence, repeated-run reliability, candidate mobile/accessibility QA and broad
extraction accuracy remain unverified. Initial request timeout is still possible;
no provider root cause or general reliability fix is claimed. Human confirmation
was a practical source of friction; no confirmation/reset behavior changed here.

Current local follow-up after those results: evidence/documentation only; no
additional application changes or live requests. Publication of this evidence
record and merge remain subject to owner authorization.
Owner supplied clean shutdown output for process 46035 after the unknown-target
test. Server is stopped; browser state may remain but is not persisted by the app.

## Follow-up candidate after owner diagnostic test

This section supersedes the diagnostic-only proposed change and test count below;
earlier entries preserve the sequence of evidence. Diagnostic-only head 25fd9f0
was published with owner approval as draft PR #4, not merged. All four published
files matched the tested local candidate. Owner Mac checked out 25fd9f0 and reported
75 passed in 2.36s.

Owner then reported `stage=after_tool turn=2 validated_evaluations=1 elapsed_ms=20011`,
followed by provider_timeout and HTTP 502. Supplied 13:46:51 Eastern screenshot
shows the failed $1.75 attempt; tab had not been refreshed. This evidence locates
that request failure after calculation, not its underlying provider cause. It does
not retroactively locate earlier timeouts. Owner reported server stopped.

Prepared isolated feature/h5-browser-completion worktree from published 25fd9f0.
Browser now uses delegate_for_browser: one existing model request, completed response,
exactly one completed recognized function call, schema validation, existing server
exact-fact check and deterministic evaluation/output validation. Canonical result
returns directly to UI with selection response ID and trace fields
`result_delivery: canonical_ui`, `model_received_result: false`. Model does not see
the calculation or produce a final answer in this path. This is intentionally a
different completion contract, not recovery from a failed follow-up. No follow-up
is attempted. Full CLI delegate loop and its failure-stage diagnostics remain.

Initial model request parameters are unchanged. Timeout remains 20 seconds, retries
zero; no forced tool choice, new provider, caching, fallback or schema authority
change. Auth, Origin/Host/client checks, screenshot confirmation, closed benchmark
envelope, exact-fact check and shared paid-operation limits remain. Multiple calls
are rejected before any execution. Only a completed validated selection and successful
canonical calculation can produce browser success; initial timeout still yields 502.
No HTML changes needed: existing expanded trace displays the new provenance fields.

Validation: 93 offline tests pass. H5 coverage now checks browser initial timeout,
CLI after-tool timeout, one-request canonical $2.00/$1.75/unknown decisions with
preserved costs, no-call/multiple/unknown/malformed/changed-fact/benchmark-injection
and incomplete/failed/cancelled output rejection, calculation errors/invalid output,
confirmation gating, redaction, lock release and installed-SDK mocked HTTP behavior.
Updated two existing fake-model fixtures with documented completion statuses; their
assertions remain. No live candidate inference, owner Mac candidate tests, new
rendered QA, publication or deployment yet. This change removes an observed failing
browser dependency but is not a proven provider fix or reliability result.

Rechecked official Meta tool-calling and Responses documentation October 27, 2026:
https://dev.meta.ai/docs/tool-calling and
https://dev.meta.ai/docs/protocols/responses . Documentation distinguishes local tool
execution from the follow-up used to return results to the model. Stopping after
local execution for canonical UI delivery is our application design decision; it
is not claimed as a model-completed result round trip. No API parameters changed.

Publication proposal after owner approval: add a follow-up commit to existing H5
draft PR #4 and rewrite its title/description around final browser behavior. No
merge/deployment authorization implied. Mac can retain the existing tab because
only server behavior changes; refresh is not required for the diagnostic test.

Baseline: GitHub main verified at 4491d4a18e44318d5d1589f247bacfdf4bf949c4.
Isolated local branch: feature/h5-demo-validation. Baseline: 73 tests pass.

## Owner live evidence on merged main

Owner Mac credentials reported present, commit 4491d4a; loopback server started.
10:23:14 / 10:23:41 Eastern screenshots show successful synthetic extraction,
unconfirmed review state, box truck, $420 payout, 180 loaded and 60 additional miles.
Owner supplied all complete synthetic costs, schedule Yes and confirmed $2.00 target.
First evaluation failed: provider_timeout, status=None, HTTP 502 (10:26:14 screenshot).
One unchanged owner retry succeeded (10:27:57): NEGOTIATE, $1.75 all-mile RPM,
$2.33 loaded RPM, $60 gap, $290 costs, $130 estimated operating surplus after
allocated costs; Muse Spark 1.3 trace shows executed_and_validated.

Owner changed only target to $1.75 and reconfirmed as instructed. Evaluation failed
again: provider_timeout, status=None, HTTP 502 (10:29:43 screenshot shows target
and preserved costs). Paid testing paused. These are owner-executed calls.
Combined screenshot-to-$2.00 evaluation recovered successfully; combined benchmark
adjustment and unknown-target evaluation remain pending. No reliability rate or
timeout cause is established. Successful main behavior is not evidence for this patch.

## Narrow proposed change

meta_agent.py wraps existing model requests with failure-only diagnostics:
fixed stage (tool_selection or after_tool), model-request turn, count of validated
evaluations, elapsed milliseconds. Original exception is re-raised unchanged.
No request parameters, model call budget, SDK timeout, retries, calculations,
browser output or success requirements change. No raw exception, submitted facts,
credentials, IDs, provider text or reasoning are included in the added logs.

Current browser success requires model-selected exact-fact delegation, deterministic
calculation, then a subsequent model response completing without another tool call.
That follow-up prose is discarded by the browser. Existing logs cannot locate the
observed timeout. New diagnostics can distinguish initial selection from a request
after validated calculation; they do not fix timeouts or prove provider root cause.
Even if calculation preceded a timeout, response remains HTTP 502 with no decision.

## Validation and remaining work

75 offline tests pass (73 baseline plus two injected timeout cases). New tests cover
both request stages through the browser boundary, original timeout classification,
sanitized logs, no retry/fallback, no partial evaluation in response, lock release,
unchanged timeout/retry configuration. git diff --check passes.
No live call, Mac patch test, new rendered QA, remote publication or deployment of
this candidate performed. No dependencies changed.

Owner approval required before publishing a feature branch and draft PR. No merge
or deployment authorized. Stop Mac server before source synchronization; preserve
browser inputs for reference and do not refresh until ready to repeat the flow.

## Remaining acceptance checklist

1. Run candidate offline suite on Mac after approved publication/synchronization.
2. Controlled screenshot extraction; complete costs/target edits, target confirmation,
   then screenshot-facts confirmation last. Evaluate confirmed $2.00 target.
3. Change only target to $1.75; verify old result clears, reconfirm target then
   screenshot, evaluate ACCEPT with $0 gap and unchanged $290 costs/$130 surplus.
4. Unknown target: reconfirm both, expect NEED_MORE_INFORMATION, null target/gap,
   unchanged costs/surplus. Respect shared four attempts/minute process limit.
5. Record failure-stage metadata if timeout recurs; choose further changes from
   evidence. Never present partial/failed delegation as success.
