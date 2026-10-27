# H5 local review — October 27, 2026

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
