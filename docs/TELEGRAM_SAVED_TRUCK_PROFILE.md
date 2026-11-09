# Saved truck profile and chat-only host

Development date: November 8, 2026. Offline evidence only.

## Behavior

The chat profile now accepts USDOT, optional MC, unit number or nickname,
capabilities, owned/financed/rented arrangement and optional home base alongside
the existing planning cost and revenue target fields. Identity values are
carrier assertions, not independent verification. Tenant authorization still
comes from the trusted numeric user/private-chat binding. Supplying the same
USDOT in two separately authorized chats never merges their records.

After choosing `remember`, enter the profile and review it. Reply `edit profile`
and supply changed fields, or `save profile` to explicitly save the reviewed
version. `/save_profile STEP` is tied to the current review nonce. The existing
`/confirm STEP` confirms for the session without saving. Choosing `session`
never permits a durable profile save.

On restart, `/start` and renewed `remember` consent reload the saved profile as
an editable draft. No opportunity or load approval is restored. Review costs
and equipment again before confirming or saving. `/profile` displays the
current truck without changing the workflow.

This increment stores one truck per authorized carrier. To update it after
starting a load, begin again with `/start`, choose `remember`, edit and save.
Starting again clears the active load session. Home base does not establish
home as the next destination. Trip goals and location are not profile fields.

## Storage and recovery

A separate `opening_profiles` table uses the existing SQLite owner and lock.
It stores reviewed profile facts, a version, save/expiry timestamps, disclosure
version and consent time. Existing retention policy applies, with a maximum
profile lifetime of 30 days. Tests use shorter retention periods.

Reads and saves require current consent. Saves compare both the reviewed
in-memory profile version and durable saved version. A failed save leaves the
chat at profile review and does not confirm a session profile. Replaying an
update does not repeat the save or outbound reply.

Session-only consent and `/forget` delete the saved truck record through the
existing durable privacy path. Failed deletion retains its pending intent and
prevents reuse. Expiry is enforced on read and scheduled maintenance. Deletion
does not erase external histories or backups. No screenshot, trip, model reply
or geolocation is persisted by this profile module.

## Host and remaining work

The opening host defaults to `enable_miniapp=False`: Mini App routes and web_app
buttons are absent. Explicit legacy callers can opt in; existing source is
retained. Profile setup itself makes no model calls.

Multi-truck selection, automatic unit matching, inline Save/Edit buttons,
guided cost normalization, location sharing/routing, next-destination
confirmation, pass records and durable opportunity revisions remain future work.
No merge, deployment or live provider/Telegram observation is claimed.

`scripts/owner_readiness.py` provides a read-only local check. It reports only
booleans, makes no network calls and changes no configuration. Presence checks
do not establish credential validity, provider funding or live compatibility.

## Verification

`python -m pytest -q`: 668 passed, including 20 new saved-profile tests.
`git diff --check`: passed. New coverage includes explicit save, fresh consent
and restart, carrier isolation, stale review/version rejection, partial edits,
expiry, save failure, deletion failure, pending privacy recovery, repeated
webhook delivery, optional nickname, profile viewing and chat-only host routes.
All provider and Telegram transport evidence in these tests is mocked.

## Trip mileage and location

Development date: November 9, 2026. Offline evidence only.

The chat accepts city or site labels for truck position, pickup, delivery and
next destination. Reply `home` to choose home and `reposition 35` to supply the
miles from delivery to home. Enter individual mileage legs as needed. The review
shows the three legs together, their sources and which values are unknown.
A screenshot estimate stays advisory until the carrier supplies a planning value.

A one-time Telegram location message can set the truck position after a screenshot
draft exists. Axle rounds the coordinates to two decimal places and keeps the
approximate pin in the active trip. It does not echo or send coordinates to the
pricing provider or write them to SQLite. Use a city or site label for typed
locations. Telegram retains its own message history. Location capture makes no
routing, geocoding or mileage request.

An endpoint edit clears the mileage for its adjoining legs unless the carrier
enters replacement mileage in the same message. Each correction opens a new
revision. A new screenshot starts a fresh trip and reuses the confirmed truck
profile. Offline webhook and worker tests use two fictional loads, verify replay
deduplication and reproduce the 245-mile Load 2 calculation before changing home
to the yard and checking the fresh mileage and confirmation requirements.
