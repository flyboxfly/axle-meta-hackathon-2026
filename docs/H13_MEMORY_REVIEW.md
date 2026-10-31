# H13 consent and profile memory — offline candidate

Follow-up: [Astra review, fixes and remaining release blockers](H13_ASTRA_REVIEW.md).

October 31, 2026. Based on draft PR #14 head a9b4c71. This adds no endpoint,
live carrier processing, provider invocation, deployment or infrastructure change.
The separate synthetic service and reviewer contract remain unchanged.

## Implemented boundary

`pilot_memory.PilotMemory` wraps the pure session core and a separate SQLite profile
database. Use only from a trusted adapter, never expose its methods as model tools.
Every carrier-facing call resolves owner-configured numeric user AND chat IDs before
state access. Tokens are random, carrier-scoped and compared in code. Strict integer
checks prevent Python bool/float keys aliasing approved IDs. This is authorization
against supplied IDs, not Telegram authentication or private-chat verification.

The adapter sequence is:
1. Show `disclosure(user, chat)` text and retain its opaque token server-side.
2. On the carrier's explicit action, call `consent` with that current disclosure token
   and either `session_only` or `remember_profile`. Never infer consent from a message,
   a model response, a profile field or an old callback. Notices expire after five minutes
   and are consumed once. New disclosures invalidate older pending notice tokens.
3. Pass the returned access token into scoped `put/get/confirm/evaluate` operations.
   Keep token plus snapshot revision in server-owned task/callback state. No identity or
   authority comes from model arguments. Renewed consent clears the active snapshot and
   rotates the token, so reused integer revisions cannot authorize old callbacks.
4. Only in remember mode, explicitly `save_profile` for the exact confirmed revision,
   with the last saved-profile version (or null if absent). The transaction rejects stale
   versions. Editing an active profile does not automatically overwrite saved memory.
5. `load_profile` returns a saved **draft**, not a confirmed new trip. Review changing
   costs, per-trip items, utilization, targets and equipment against the performing unit.
   Create a new opportunity snapshot and obtain fresh confirmation before evaluation.
6. `forget` works for an approved binding even without a live consent token. It withdraws
   active consent, clears snapshots/results/notices and deletes that carrier's profile row.
   If deletion fails, consent is still withdrawn and the error propagates; the adapter
   must say deletion failed, never report success. Other carriers remain unaffected.
   A failed deletion now blocks renewed consent within the owning process until deletion
   succeeds. This pending intent is not durable across restart; see the review recovery hold.

Consent options and versions are application behavior, not a legal assessment. The
host must supply a reviewed `MemoryPolicy.processing_notice` and version describing
the actual providers, data use, purposes and retention. The module does not validate
those claims or establish informed consent by itself. No transport currently shows
this disclosure or gathers a real carrier's response.

## What is saved and when

Only an explicit save writes a profile row: server carrier key, random saved version,
profile JSON (including supplied sources/metadata), saved/expiry times, disclosure
version, consent time, and historical snapshot revision/confirmation time. There is
one current row per carrier. No opportunity, screenshot, conversation, Telegram ID,
bot token or calculation result is written to this database. Profile source/free-text
fields can still contain private carrier information; treat the entire file as private.

Session-only writes no profile row and deletes an existing saved profile on downgrade.
Consent grants stay in memory; even remember-mode users must acknowledge a current
disclosure again after restart. Loaded data retains its historical disclosure version.
There is no secondary research/training/sharing consent, profile export or public-evidence
permission in this API. Software interest does not grant integration access.

Default access lifetime is one hour from consent; activity does not slide expiry.
Expiry blocks access and clears active state when observed by a request or maintenance.
It does not erase Python memory at an exact wall-clock instant without maintenance.
Default saved-profile lifetime is 30 days from each explicit save; ordinary reads do
not extend it. Expired profiles cannot load and are deleted on scoped access or purge.
The host must schedule `purge_expired()`; no scheduler is added here. Constructor policy
bounds session lifetime to at most 24 hours and profile lifetime to at most 30 days.

SQLite uses transactions, DELETE journaling and secure_delete. These are logical
deletion measures, not promises of forensic erasure or encryption. Provider histories,
filesystem/storage snapshots, backups, infrastructure logs and Telegram messages are
outside this module. No zero-retention promise follows. Restoring an old database could
restore deleted profiles; backup deletion/restore suppression must be designed before
real use. No backup or host retention configuration was changed.

## Runtime limits and release holds

This is an offline single-process candidate, not a hosted storage system. The owner
process serializes operations with a lock; saved-profile replacement additionally uses
a SQLite write transaction and version comparison. Do not run multiple workers sharing
the file: volatile consent/session state and privacy actions would not synchronize.
No dynamic owner-binding revocation, schema migration, disk quota, encryption/key
management, durable transport queue, async completion publication guard or callback
transport is implemented. Changing owner bindings currently requires rebuilding the
facade; that is not a demonstrated live revocation mechanism.

Before live use: finish the authenticated Telegram boundary, durable delivery handling,
bounded input/media validation, async revision/consent checks, safe outward errors/logs,
retention maintenance and deletion/backup behavior. Provision a private pilot-owned file
and directory with reviewed filesystem permissions; never use production storage or
commit the database. `pilot-data/` and SQLite filenames are ignored as an extra precaution.
The database is plain SQLite; filesystem and host isolation remain deployment work.

Meta's observed free-credit product-improvement condition remains unresolved. Do not
send private carrier data based on this local storage consent. Review the actual account
conditions and processing disclosure first. The offline Astra review is complete; review
the integrated transport/storage boundaries again before real carriers connect.
Merge, deployment and runtime/secret changes remain separate
owner decisions. Shared Coolify proxy and protected infrastructure holds still apply.

## Verification

Assistant Linux, October 31, 2026; same temporary venv and unchanged lockfile:
- Initial focused memory suite: 19 passed. Two later cases add read-retention and rollback checks.
- Final full pytest: 240 passed in 3.01s (219 prior + 21 memory cases).
- pip check: no broken requirements.
- PYTHONPATH=src python scripts/export_reviewer_openapi.py --check: passed.
- git diff --check and relative Markdown links: passed.

Cases cover no implicit consent, session-only nonpersistence, explicit reviewed saves,
restart/re-consent, loaded drafts, cross-carrier token rejection, unauthorized access before
database access, stale/expired/replayed disclosures, expiry, cleanup, downgrade, withdrawal,
stale versions/revisions, failed deletion, safe malformed-profile errors, read retention and
write rollback. Temporary SQLite files and invented profiles only; no real carrier record,
paid call, transport, hosting or independent security review was involved.
