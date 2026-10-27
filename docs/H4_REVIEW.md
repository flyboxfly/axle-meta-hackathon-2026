# H4 local review — October 27, 2026

Baseline verified through GitHub: main 01c9f45308c5e12247dbb373323fe5aed4d2c5a0, merged H3 PR #2. Local isolated branch: feature/h4-carrier-benchmarks. No remote publication, paid inference, production access or deployment performed.

## Behavior and authority

Compact form requires an explicit all-mile revenue target or unknown choice and confirmation. No prefilled carrier threshold. Costs and target remain distinct. Unknown targets preserve costs/surplus but prevent acceptance and leave target revenue/gap null. Results show source and compare prior/current target, decision and gap. Changing a target invalidates target confirmation and results; existing screenshot confirmation is also invalidated by form edits. Screenshot reset preserves the separate benchmark while clearing opportunity facts/costs.

Closed server-validated benchmark envelope travels separately from Opportunity. The evaluation closure captures it directly; the model receives the unchanged Opportunity schema and cannot supply/override target. Vision extraction remains unchanged and excludes benchmark fields. No persistence, identity selector or shared profile mutation. Old clients omitting benchmark preserve the labeled synthetic default; new UI always sends a choice. This compatibility path is intentional, not a personalized benchmark. Confirmation remains an authenticated assertion.

## Canonical evidence

Same complete $420 opportunity, 240 total miles: $290 estimated costs, $130 estimated operating surplus after allocated costs in all three scenarios.

| Target | Target revenue | Gap | Decision |
| --- | --- | --- | --- |
| $2.00 | $480 | $60 | NEGOTIATE |
| $1.75 | $420 | $0 | ACCEPT |
| Unknown | null | null | NEED_MORE_INFORMATION |

ACCEPT remains supplied economic/schedule checks only, with no booking or legal clearance. Only synthetic box-truck profile supported. No inference pricing or API request parameters changed.

## Validation

73 offline pytest tests pass: all 57 pre-existing cases plus 16 H4 cases. Added target bounds/nonfinite/precision checks, confirmation/extra-field rejection before paid calls, target-driven decision changes, unknown preservation, prompt/model authority rejection and request isolation. Existing H3 SDK serialization remains mocked HTTP. Dependency check, compilation, JavaScript syntax and diff whitespace checks pass. No paid H4/live owner test performed. Scratch jsdom checks pass for payload separation, target confirmation reset, target comparison, unknown choice and screenshot separation. These are DOM logic checks, not visual QA. Browser rendering remains unverified in this workspace: Chromium download returned an invalid archive. README provides exact owner verification sequence after publication approval.

## Review scope

Changes: schemas.py nullable benchmark figures/source; economics.py explicit target argument; web.py separate confirmed benchmark validation/captured authority; carrier.html compact control/provenance/comparison; tests/test_h4.py; README and build/test/review documentation. No dependency changes. Review the staged local diff with `git diff --cached`; no commit or remote branch has been created.

Owner approval is required before pushing a feature branch and opening a draft PR, per the supplied handoff. No merge or deployment authorization is implied.
