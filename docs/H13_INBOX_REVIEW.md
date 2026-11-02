# H13 durable inbox and privacy recovery candidate

October 31, 2026. Based on draft head 2d90727. Offline SQLite development component;
no webhook, credentials, paid calls or real carrier records. No deployment or merge.

PilotMemory now commits a carrier deletion intent before deleting a profile. Failed
deletion retains the intent across restart, and renewed consent must complete deletion
before profile access. If storage fails before intent commits, the request has NOT been
durably accepted: report failure and do not acknowledge success. Backup restores can
still restore older state; backup suppression/deletion remains deployment work.

File-backed memory now holds a nonblocking POSIX flock on a persistent sibling .owner
file. A second instance/process using the same resolved path is rejected. The lock is
released on close or process termination, not by unlinking the file. Use one canonical
private database path; aliases via hardlinks/network filesystems and hostile filesystem
access are outside this enforcement. Linux/macOS supported; Windows is not supported.
Database initialization failures release the owner lock. Host permissions and encryption
remain separate work. Never delete the .owner file while a process could be running.

PilotInbox extends the owning facade with a metadata-only inbox for evaluate/forget.
An update ID is unique within this dedicated bot/database. It stores carrier key,
action, revision, consent-token hash, claim token and status, with no raw messages,
images, profiles, results or consent tokens. Metadata is private operational data.
Submission checks approved numeric user/chat binding before storage. Evaluation
submission additionally requires current consent and a confirmed revision.

Duplicate IDs have no repeated effects; mismatched carrier/action is rejected. A
claim requires the original consent generation and current confirmed revision and
commits processing status before the caller may invoke the model. Only one claim
is issued. The future worker MUST invoke paid work only after successful claim and
use PilotDelegator's fresh state checks. This component does not invoke that worker.
Finish only records status, never authorizes message delivery. On restart, interrupted
processing becomes uncertain and cannot be claimed again. Queued work from an old
consent generation cannot execute after re-consent. No automatic paid retries.

Forget submission atomically records the update and deletion intent, then clears
active consent. Its worker completes deletion idempotently. If re-consent already
completed that deletion, a delayed worker marks the old command done without deleting
a newly saved profile. Direct forget also uses durable intent. Operator recovery is
still needed when storage cannot commit at all.

Capacity is 10,000 retained update records; overflow is rejected. There is no automatic
pruning: dedup records remain until an explicit future retention/migration design.
The host must not acknowledge rejected updates as accepted. This is bounded admission,
not a final service capacity or retention policy. No raw payload queue exists yet;
current opportunities remain volatile and must be supplied again after restart.

Remaining transport work: authenticated webhook/private-chat validation, ordered
commands and callbacks, reviewed disclosure UI, safe error responses, task worker
wiring, per-carrier/global paid budgets, bounded media handling, and consent/revision
checks at outbound delivery. Replayed unknown/out-of-order privacy commands require
an explicit ordering policy before transport use. This slice does not claim exactly-once
external inference or message delivery. Re-review integrated boundaries before real use.

Offline cases: duplicate/single claim, cross-carrier update scope, uncertain restart,
failed deletion across restart, queued privacy recovery without deleting newer data,
second-owner rejection and changed-consent rejection. Invented records only.

Validation: full pytest **267 passed in 2.79s** (261 prior + 6 inbox cases), pip check,
exported reviewer OpenAPI compatibility and git diff --check passed. No dependency change.
