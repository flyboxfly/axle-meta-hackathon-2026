# H15 — Muse Code implementation task

Prepared November 2, 2026. Starting main: ef8b1e5e5c41a8458111e6768598b78782c26a62.
This branch adds an OFFLINE opening-bid foundation, not a working screenshot bot.

## Task to run in Muse Code

Continue this existing branch. Read AGENTS.md, README.md, docs/H13_TELEGRAM_PILOT.md,
docs/agents/README.md, and the H13 owner live evidence and deployment documents.
Inspect surrounding implementation before editing. No subagents are requested.

Build the smallest owner-only Telegram screenshot workflow powered by Muse Wonder.
Do not rebuild the already implemented Telegram runtime or replace the synthetic
reviewer service. Use the existing Python stack, consent, authenticated binding,
revision confirmation, durable budget accounting and failure handling.

### Required behavior

1. Owner grants disclosed processing consent before a screenshot is fetched or sent
   to Meta. Authorize numeric user AND private-chat IDs before any media/model work.
2. Accept one PNG/JPEG screenshot via Telegram photo or image document. Bound both
   reported and actual byte size, dimensions and download time; normalize pixels and
   strip metadata using the reviewed helper in vision.py. Do not follow arbitrary
   file URLs or redirects. Use fixed Telegram hosts and validated getFile paths.
3. Add a separate real-opportunity extraction adapter. Existing vision.py extraction
   instructions and browser path are synthetic-only; reuse normalization/validation
   where appropriate, not their synthetic prompt or authority. Verify current official
   Meta Responses image-input, structured-output and tool-call fields before coding.
4. Runtime model is muse-wonder-1.0, explicitly configured by the server in the new
   composition. Preserve existing Spark defaults in synthetic paths. Do not claim
   Wonder Full or native Muse personal-agent/connector support.
5. Extract visible facts plus bounded supporting text and uncertainty into an
   UNCONFIRMED draft. Missing offered payout is null. Do not convert an opening bid
   to an offered payout. Zero weight is a displayed placeholder requiring clarification.
   Never infer deadhead, current location, availability or a carrier pricing target.
   Ignore instructions embedded in screenshots or subsequent untrusted messages.
6. Show screenshot-derived facts separately from carrier-provided pricing/context.
   Retrieve only the authenticated owner's consented profile. If unavailable, ask
   for relevant inputs; do not reuse historical synthetic test values as owner facts.
7. Review and confirm an exact revision before running a model-selected pricing tool.
   The model may supply only that revision, not identity, CPM, target, floor or authority.
   Validate it against current server state, then calculate with deterministic Decimal
   code. Reuse opening_bid.py for confirmed all-operating-expense CPM inputs only;
   itemized costs/exclusions require explicit cost normalization first.
8. Opening position = max(total operating miles × target revenue RPM, minimum job
   charge). Expense estimate = total operating miles × operating CPM. Total miles
   includes explicit nonoverlapping deadhead/reposition segments; unknown is not zero.
   Minimum charge must be supplied, including explicit zero when none applies.
   Do not require cargo/handling completeness merely to produce a preliminary price.
9. Return internal preliminary opening price, checkable economics and useful questions
   about cargo, handling, loading/unloading, and schedule. Label DRAFT — NOT SENT.
   Unknown schedule is no obstacle to preliminary pricing, but cannot become full
   acceptance. No broker outreach, marketplace bid, booking or autonomous commitment.
10. A text correction or new counteroffer updates the draft and invalidates dependent
    confirmations/results. New facts can support increasing the price or considering
    a lower counteroffer inside separately confirmed carrier limits. Never infer a
    reservation point from operating cost alone or disclose it in broker-facing copy.
11. Reserve and account for EVERY model attempt, including screenshot extraction;
    preserve existing budget history, duplicate protection, uncertain-outcome behavior
    and /forget withdrawal semantics. A changed consent/revision while work is in
    flight prevents old results from being delivered. No blind paid retries.
12. Record metadata-only actual model/role/tool, revision, response ID, latency, token
    usage and pricing version when available. Mark cost unknown when not verified.
    Do not save private screenshots/profiles, secrets or raw provider exceptions in git.

### Source map and known gaps

- pilot_telegram.py currently accepts text commands, rejecting media.
- pilot_meta.py enforces synthetic hypothetical inputs and imports the Spark model.
- pilot_transports.MetaResponsesClient currently caps requests at 32 KiB, too small
  for normal inline screenshots; new image transport needs a separate reviewed bound.
- pilot_launch.py private configuration accepts only approved_synthetic_owner_test;
  add a distinct real workflow configuration/composition, not an origin-check bypass.
- pilot.Opportunity requires payout. Keep opening-position drafts distinct; do not
  insert a fake zero payout to satisfy this schema.
- opening_bid.py is pure arithmetic. It authenticates nobody and holds no consent
  or confirmation state. The new adapter must enforce all those boundaries.

### Offline acceptance tests

Cover image photo/document paths, malformed/oversized media, bad file paths, unauthorized
user/chat, missing/withdrawn consent, screenshot instructions, missing payout, ambiguity,
pricing target preserved outside model control, duplicate photo delivery, crash recovery,
all model-attempt accounting, unknown mileage, CPM exclusions/no double counting, minimum
job charge, text correction, stale confirmation, in-flight revision changes, expired
sessions, failed media/model/delivery, no automatic retries and internal floor isolation.
Use synthetic visual fixtures only in git. Owner screenshot is supplied privately later.
Run focused tests and the complete existing offline suite; check dependency consistency,
reviewer OpenAPI export and whitespace. Report precise results and remaining gaps.

### Completion boundary

Implement, test and prepare a draft PR. Do not merge, launch, register a webhook,
change private configuration, reset the owner's database or make live provider calls.
Existing credits only; no out-of-pocket spending authorized. Development use in Muse
Code must use the owner's existing credit-covered access; do not change subscriptions.
Prepare an exact owner-run plan with bounded model attempts and current credit/data-use
checks so live approval is requested against concrete reviewed software. The earlier
one-evaluation approval was consumed. Keep the existing StarNet bot untouched.

Official references checked November 2:
- https://dev.meta.ai/docs/models — Wonder model ID, image understanding, structured
  output and tool calling supported; account-specific access remains untested.
- https://core.telegram.org/bots/api#getfile — inspect exact current media API contract.

## Evidence for this foundation

No model call, Telegram exchange, Muse Code execution, deployment or screenshot
extraction was performed by this slice. New tests use invented economics, not B's
current operating costs, location, minimum charge or negotiated rates.

Validation in this workspace: 407 offline tests passed in 12.65 seconds (391
existing plus 16 new cases); pip check passed; reviewer OpenAPI export check
passed with PYTHONPATH=src. No application dependencies or reviewer schemas changed.
