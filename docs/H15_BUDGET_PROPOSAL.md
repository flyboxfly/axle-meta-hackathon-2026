# H15 attempt-budget recovery proposal (review only, not executed)

Prepared November 3, 2026. Planning evidence only. This proposal changes
nothing by itself; execution requires a reviewed commit plus separate owner
approval at rehearsal time. Do not merge, reset the ledger, refund attempts,
or spend outside existing credits.

## Current ledger state

Global cap 4, per-carrier cap 4, on one durable ledger: 3 attempts reserved
(one earlier uncertain screenshot, one completed screenshot, one completed
opening-price action). One attempt remains. The uncertain record and all
history must persist; refunds are impossible because an uncertain attempt
may have executed server-side.

## Requirement

A fresh rehearsal of the fixed journey needs 2 attempts: 1 screenshot
extraction plus 1 model-selected pricing evaluation. That does not fit the
1 remaining attempt under the existing cap.

## Options

A. Recommended: one-time reviewed cap raise from 4 to 6 (global and
   carrier), applied as a code change to the launcher constants on a
   reviewed commit that the owner checks out before rehearsal. The same
   ledger is kept: 3 used + 2 planned = 5 of 6, leaving 1 spare for a
   single failed attempt. No reset, no refund, no evasion.
B. Extraction-only rehearsal within the remaining 1 attempt, deferring
   evaluation. Partial verification; the evaluation path stays offline-only.
C. New database to evade the ledger. Rejected: lifetime accounting exists
   to bound spend, and a fresh ledger would hide real history.
D. Refunding the uncertain attempt. Rejected: violates the no-refund
   invariant; the attempt may have run and billed.

## Execution sketch for option A (gated on approval)

1. Reviewed PR commit changing only the two cap constants in
   `main_real` (4 to 6) with a comment citing this proposal; full suite
   green on the pin.
2. Owner updates the isolated checkout to that pin and re-runs the
   offline suite before any live step.
3. Owner confirms the ledger still reads 3 used (no reset), then runs
   the bounded rehearsal: at most 2 further attempts, no retries.
4. Any failure keeps its reservation; the spare covers one failed
   attempt only, then testing ends under the existing recovery rules.

## Expected model use per rehearsal

- 2 model calls: Wonder extraction (image request bounded by the 4 MiB
  screenshot cap, response parsed up to 12,000 chars, `max_output_tokens`
  4096, reasoning effort low) plus Wonder revision-only tool selection
  (input under 16 KiB, 1000 output tokens). No model calls are made for
  parsing ordinary numeric fields.
- Token and dollar totals are account-specific and cannot be predicted
  here; usage is recorded per attempt when the provider returns it, and
  cost stays unknown until metered.
