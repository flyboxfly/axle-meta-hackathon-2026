# H13 setup helper security review

November 1, 2026 (America/New_York). Reviewed baseline 3b867fe. Offline evidence only.

Two defects corrected:

- isatty does not guarantee that getpass can disable terminal echo. Python can issue
  GetPassWarning and fall back to visible input. Every private prompt now treats that
  warning as an exception before fallback reads input. main reports its fixed error.
- A new config could be named pilot.sqlite3 or pilot.sqlite3.owner, occupying a path
  reserved for runtime database/ownership state. Destination validation now rejects
  the entire pilot.sqlite3 filename prefix before any write or enrollment call in
  the CLI. Existing config/state preservation checks remain in place.

Four regression cases cover the echo fallback and database/lock/journal filename
collisions. Full suite: 383 passed in 5.30s. Dependency and reviewer OpenAPI checks
passed; whitespace checks passed. No credentials, listener, model or Telegram call.

Reviewed the fixed endpoint allowlist, identity/binding checks, exact acknowledgement
handling, private exclusive file creation and CLI sanitization. Registration refuses
an existing webhook; removal refuses a different URL. No automatic retry or raw
response output is introduced. These controls assume one trusted local operator and
exclusive use of the dedicated bot: separate getWebhookInfo and mutation calls are
not atomic against another operator. Scoped removal of an empty webhook deliberately
drops queued updates. A lost acknowledgement remains uncertain and requires check,
not repeated mutation. Tests do not establish live provider or Mac behavior.

The helper is ready for target-environment preparation after this focused review.
No further model-switch loop is needed for this slice. Before any live setup, verify
Mac/Python/tunnel inventory, private storage/backup exclusions, dedicated bot and owner
binding, provider account authorization and spending ceiling. Use the deployment plan
and an immutable combined package pin. This review grants no merge, deployment,
secret-provisioning or live-operation permission. The existing retained-owner policy,
external-history limitations and no automatic crash recovery still apply.
