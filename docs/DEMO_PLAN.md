# Three-minute demo — H12 recording draft

Updated October 31, 2026, from H11 owner-operated live evidence and the H12 presentation changes.
This is a recording plan, not a completed video or timed rehearsal.

## Required opening disclosure

First spoken line and opening screen text:

> Axle’s concept, brand and VPS pre-existed; we built this standalone application, Meta model integrations and demonstrated workflow for the hackathon.

Owner clarification, October 27: Startup Track selected; existing VPS hosting permitted with this pre-existing-versus-new disclosure. The deterministic API is deployed; the browser and Meta orchestration remain loopback-only.

## Story and narration

| Time | Screen/action | Suggested narration |
| --- | --- | --- |
| 0:00–0:20 | Product headline and prototype disclosure | “Axle’s concept, brand and VPS pre-existed; we built this standalone application, Meta model integrations and demonstrated workflow for the hackathon. I’m Brian, a carrier and the founder of Fly Box Fly. A load can look good per loaded mile and still miss your business needs. Personal AI should know when to ask a freight specialist: Axle.” |
| 0:20–0:45 | Select synthetic fixture, show consent, request extraction | “This is a simulated Muse-facing interface using synthetic data. The Meta model requests and deployed Axle API calls are real; there is no native Muse connector. Muse Spark reads the screenshot into an unconfirmed draft. I review the equipment, complete payout, and every mile committed.” |
| 0:45–1:15 | Show $420, 180 loaded, 60 additional; enter target/costs/schedule; confirm target, then reviewed facts, then screenshot last | “The offer is $420 for 180 loaded miles, plus 60 additional miles. I supply my trip costs, schedule assessment, and a two-dollar all-mile revenue target. The carrier confirms the facts and target.” |
| 1:15–1:45 | Submit once; show NEGOTIATE and canonical figures | “Muse Spark selects Axle’s freight tool. Our local server sends the confirmed facts to the deployed Axle API and validates its canonical response. Loaded revenue is $2.33 per mile, but all-mile revenue is $1.75. That leaves a $60 gap to my target. Estimated costs are $290, leaving $130 of estimated operating surplus after allocated costs.” |
| 1:45–2:15 | Change only target to $1.75, show invalidation, renew all confirmations, submit once; show comparison | “For a sensitivity check, I change only the target to $1.75. This does not improve the load’s economics or establish that lowering my target is wise. The supplied checks now pass; costs and surplus are unchanged. The comparison explains exactly what changed.” |
| 2:15–2:40 | Expand delegation evidence | “Here is the actual model-selected tool execution. Axle delivers the validated calculation directly to the interface. The model does not receive the result or author the final decision text. This is specialized delegation with an auditable calculation.” |
| 2:40–3:00 | Result and product close | “Axle helps carriers see the tradeoffs before acting. This prototype supports a synthetic box-truck profile. Acceptance is not booking or legal clearance. The concept predates the event; this standalone application was built for the competition. Built by a carrier. For carriers.” |

## Capture procedure

- Keep authentication and credentials outside the recording; hide unrelated tabs and notifications.
- Use only fixtures/synthetic_freight_screenshot.png. No pre-existing logo or production data is required.
- Capture real extraction and both actual evaluations. Three paid operations are planned; no automatic retries.
- Complete every edit before confirming target, then reviewed opportunity facts, then screenshot facts last. Changing target clears results and requires renewed confirmations.
- Show the genuine waiting states. If editing removes typing or waiting, label the video “Edited demonstration; typing/waiting shortened.” Never present edited timing as uninterrupted live latency.
- Keep the NEGOTIATE frame long enough to read $60 / $290 / $130, then show the target-only comparison and expanded evidence.
- Skip the optional unknown-target paid call in the core video. It was verified against the deployed API in H11.
- Do an offline narration/scroll rehearsal before spending credits on recording. Target 2:50–2:55; the three-minute schedule is not yet timing-validated. If setup is too long, shorten typing footage transparently rather than weaken confirmation.
- If a request fails, preserve the inputs and inspect sanitized Terminal diagnostics before a manual retry. Do not substitute a fabricated successful response.

## Exact synthetic entries

Payout 420; loaded miles 180; additional miles 60; equipment 26-foot box truck.
Diesel 4; MPG 10; tolls 20; driver cost 80; maintenance/mile 0.10;
equipment trip cost 50; allocated insurance 20; hours 6; schedule Yes.
Target first 2.00, then 1.75. Targets are illustrative, not recommendations.

## Readiness boundaries

H11 owner screenshots establish three live Meta-selected remote evaluations:
NEGOTIATE at 2.00, ACCEPT at 1.75, and NEED_MORE_INFORMATION at an explicitly
unknown target. The deployed API returns canonical economics; browser flow does
not send the result back to Meta. H12 UI changes require a new owner Mac live
rehearsal after review; offline browser fixtures are not new live evidence.

Recording and judge access remain unresolved. Keep the browser loopback-only;
no public tunnel. Launch with `PYTHONPATH=src .venv/bin/python scripts/run_remote_browser.py`.
Respect the shared four-attempt/minute budget (extraction plus evaluation).
If recording all three target cases, allow the quota window to expire before
an additional attempt; never retry blindly.

Initial connector application was submitted October 31. Business verification
is approved, data questionnaire is in review, Technical details needs action.
No reviewer credential is provisioned and no native Muse execution is verified.
This onboarding does not block the simulated interface demo.

Startup Track and VPS reuse are confirmed by owner clarification; full official
rules were not independently retrieved in full. Do not claim native connectors,
booking, production carrier profiles, historical benchmarks, a browser model/tool-result
round trip, or a model-authored final evaluation. No H12 deployment is needed.
