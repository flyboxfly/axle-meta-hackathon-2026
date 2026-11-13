"""Authenticated Telegram Mini App routes for the real-opportunity pilot.

Separate from web.py (loopback-only) and the bot webhook. Every API request
carries raw Telegram initData, verified server-side per
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
(HMAC-SHA-256 with key "WebAppData"). initDataUnsafe, browser-supplied
identity, client prices and client confirmation claims are never trusted.

Trust model:
- initData is an authentication credential. Reuse across one launch's many
  requests is legitimate while fresh and while the SAME consented session
  stays active. Each launch (carrier, auth_date) binds the session
  generation it first used; after /forget, expiry or a new /start the
  old launch is rejected and only a reopened app (fresh launch) binds
  the replacement session. Launch data lives at most two hours with
  60 seconds of future skew: enough for the attended one-hour session
  plus slack, and rotation rejects old launches immediately anyway.
- Replay protection applies to state-changing requests instead: each one
  carries a single-use client request_id. A repeated request_id never
  re-executes; the recorded outcome is returned.
- Evaluation cannot spend twice: one queued action per carrier+revision,
  and stored results return without new queueing.
- Concurrent edits are detected by expected revision; mismatches return
  the current review with a conflict flag instead of applying.
- Inline-button initData carries user but no chat, so the signed user id
  must resolve to exactly one authorized (user, chat) binding.
- Forms, reads, parsing and confirmations spend no model attempts.
  Evaluation queues through the same budgeted inbox path as bot /price.

No framing headers are set: official docs give no allowlist, and Telegram
clients load Mini Apps from varying webview/iframe origins. A guessed
origin policy could prevent the app opening; authorization never depends
on framing.
"""
import hashlib
import hmac
import json
import re
import time
from secrets import token_urlsafe
from urllib.parse import parse_qsl

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from .opening_telegram import (FIELD_LABELS, apply_pairs_to_snapshot,
                               negotiation_guidance, validate_profile_pairs)
from .opening_workflow import (effective_compensation, mileage_candidates, missing_input_labels,
                               pricing_blockers, propose_mileage)
from .remote_app import _is_valid_hostname

INITDATA_MAX_CHARS = 8192
BODY_MAX_BYTES = 65536
# Bounded launch-data lifetime for the attended pilot: the consented bot
# session lasts one hour, and each app open mints fresh initData, so two
# hours covers the admission window with slack while bounding replay of
# authentication material. The launch-to-session binding below is the
# stricter boundary: rotated sessions reject old launches immediately.
AUTH_MAX_AGE_SECONDS = 2 * 3600
AUTH_FUTURE_SKEW_SECONDS = 60
MINIAPP_UPDATE_BASE = 2 ** 62
MINIAPP_UPDATE_LIMIT = 2 ** 63
REQUEST_ID_PATTERN = re.compile(r'[0-9a-f]{32}')
HASH_PATTERN = re.compile(r'[0-9a-fA-F]{64}')

PAGE_CSP = ("default-src 'self'; script-src 'self' https://telegram.org; "
            "style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' blob:; "
            "base-uri 'none'; form-action 'self'")
NO_STORE = {'Cache-Control': 'no-store'}


def verify_init_data(init_data, bot_token, *, now):
    """Verify raw Telegram initData. Returns {'user_id', 'auth_date'}.

    Raises ValueError for malformed data, bad signatures and stale or
    future timestamps. `now` is injected (unix seconds) for testing.
    """
    if not isinstance(init_data, str) or not 1 <= len(init_data) <= INITDATA_MAX_CHARS:
        raise ValueError('Invalid launch data')
    if not isinstance(bot_token, str) or not bot_token:
        raise ValueError('Server identity unavailable')
    try:
        items = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise ValueError('Invalid launch data') from None
    if not items or len({key for key, _ in items}) != len(items):
        raise ValueError('Invalid launch data')
    fields = dict(items)
    received = fields.pop('hash', None)
    if received is None or HASH_PATTERN.fullmatch(received) is None:
        raise ValueError('Invalid launch signature')
    check_string = '\n'.join(f'{key}={fields[key]}' for key in sorted(fields))
    secret = hmac.new(b'WebAppData', bot_token.encode('utf-8'), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received.lower()):
        raise ValueError('Invalid launch signature')
    try:
        auth_date = int(fields.get('auth_date', ''))
    except (TypeError, ValueError):
        raise ValueError('Invalid launch timestamp') from None
    if auth_date > now + AUTH_FUTURE_SKEW_SECONDS:
        raise ValueError('Launch data from the future')
    if auth_date < now - AUTH_MAX_AGE_SECONDS:
        raise ValueError('Stale launch data')
    try:
        user = json.loads(fields.get('user', ''))
    except ValueError:
        raise ValueError('Invalid launch user') from None
    user_id = user.get('id') if isinstance(user, dict) else None
    if type(user_id) is not int or not 0 < user_id < 2 ** 53:
        raise ValueError('Invalid launch user')
    if user.get('is_bot') is True:
        raise ValueError('Invalid launch user')
    return {'user_id': user_id, 'auth_date': auth_date}


def resolve_owner(inbox, user_id):
    """Resolve a signed user id to exactly one authorized binding.

    Returns (user, chat, carrier). Ambiguity or unknown users are rejected:
    inline-button initData carries no chat, so the binding must be unique.
    """
    matches = [key for key in inbox._bindings if key[0] == user_id]
    if len(matches) != 1:
        raise PermissionError('Unapproved launch identity')
    user, chat = matches[0]
    return user, chat, inbox._bindings[(user, chat)]


def ensure_miniapp_tables(inbox):
    with inbox._lock, inbox._db:
        inbox._db.execute('''CREATE TABLE IF NOT EXISTS miniapp_requests (
            request_id TEXT PRIMARY KEY, carrier TEXT NOT NULL, kind TEXT NOT NULL,
            revision INTEGER, update_id INTEGER, status TEXT NOT NULL,
            created REAL NOT NULL)''')
        inbox._db.execute('''CREATE TABLE IF NOT EXISTS miniapp_launches (
            carrier TEXT NOT NULL, auth_date INTEGER NOT NULL,
            generation TEXT NOT NULL, created REAL NOT NULL,
            PRIMARY KEY (carrier, auth_date))''')
        inbox._db.execute('''CREATE TABLE IF NOT EXISTS miniapp_seq (
            name TEXT PRIMARY KEY, next_id INTEGER NOT NULL)''')
        inbox._db.execute('INSERT OR IGNORE INTO miniapp_seq VALUES (?,?)',
                          ('update_id', MINIAPP_UPDATE_BASE))
        if not hasattr(inbox, '_miniapp_staging'):
            inbox._miniapp_staging = {}


def bind_launch_session(inbox, carrier, auth_date, generation):
    """Bind one Mini App launch to the consented session it first used.

    Legitimate multi-request use reuses one launch (same auth_date) and
    passes. After /forget, expiry or a new /start the active generation
    rotates, so the old launch is rejected; reopening the app (a fresh
    launch with a new auth_date) binds the replacement session.
    """
    now = time.time()
    with inbox._lock, inbox._db:
        inbox._db.execute('DELETE FROM miniapp_launches WHERE created < ?',
                          (now - AUTH_MAX_AGE_SECONDS - 300,))
        if inbox._db.execute('SELECT count(*) FROM miniapp_launches').fetchone()[0] >= 10000:
            raise RuntimeError('Mini App capacity reached')
        inbox._db.execute('INSERT OR IGNORE INTO miniapp_launches VALUES (?,?,?,?)',
                          (carrier, auth_date, generation, now))
        row = inbox._db.execute('SELECT generation FROM miniapp_launches '
                                'WHERE carrier=? AND auth_date=?',
                                (carrier, auth_date)).fetchone()
        if row is None or row[0] != generation:
            raise PermissionError('Session changed; reopen the Mini App')


def allocate_miniapp_update_id(inbox):
    """Synthetic update ids from a disjoint high range; never collide with Telegram ids."""
    with inbox._lock, inbox._db:
        row = inbox._db.execute("SELECT next_id FROM miniapp_seq WHERE name='update_id'").fetchone()
        if row is None:
            raise ValueError('Mini App storage unavailable')
        update_id = row[0]
        if not MINIAPP_UPDATE_BASE <= update_id < MINIAPP_UPDATE_LIMIT:
            raise RuntimeError('Mini App update space exhausted')
        inbox._db.execute("UPDATE miniapp_seq SET next_id=? WHERE name='update_id'",
                          (update_id + 1,))
        return update_id


def touch_conversation(inbox, carrier):
    """Keep the bot surface consistent after a Mini App mutation.

    Rotates the bot nonce so in-flight bot commands fail closed, resyncs the
    tracked revision, and demotes a confirmed bot step when the snapshot is
    no longer confirmed. Never confirms or spends anything.
    """
    with inbox._lock:
        flow = inbox._conversation_states.get(carrier)
        if flow is None or flow.get('step') == 'memory':
            return
        flow['nonce'] = token_urlsafe(12)
        opening = getattr(inbox, '_opening', None)
        if opening is None:
            return
        key = next((k for k, v in inbox._bindings.items() if v == carrier), None)
        if key is None:
            return
        try:
            opening.get_profile(*key)
        except KeyError:
            pass
        else:
            if flow.get('step') in ('profile', 'profile_review'):
                flow['step'] = 'photo'
                flow.pop('profile_values', None)
        try:
            current = opening.get(*key)
        except KeyError:
            return
        flow['revision'] = current.revision
        if flow.get('step') == 'confirmed' and not current.confirmed:
            flow['step'] = 'review'


def _number_field(value, source):
    if value is None:
        return {'value': None, 'state': 'unknown', 'source': source}
    text = str(value)
    return {'value': text, 'state': 'explicit_zero' if text in ('0', '0.00') else 'known',
            'source': source}


def _text_field(value, source):
    if value is None:
        return {'value': None, 'state': 'unknown', 'source': source}
    return {'value': value, 'state': 'known', 'source': source}


def profile_payload(profile):
    if profile is None:
        return None
    return {
        'operating_cpm': _number_field(profile.operating_cpm, 'profile'),
        'expense_claim': _text_field(profile.expense_claim, 'profile'),
        'target_all_mile_rpm': _number_field(profile.target_all_mile_rpm, 'profile'),
        'minimum_job_charge': _number_field(profile.minimum_job_charge, 'profile'),
        'equipment': _text_field(profile.equipment, 'profile'),
        'operating_context': _text_field(profile.operating_context, 'profile')}


def review_payload(snapshot, profile):
    """Structured review: values with sources, unknowns distinct from zero."""
    facts = snapshot.draft.facts
    pricing = snapshot.pricing
    trip = snapshot.trip
    sources = snapshot.sources
    review = {
        'revision': snapshot.revision,
        'confirmed': snapshot.confirmed,
        'facts': {
            'payout': _number_field(facts.payout, sources.get('payout', 'screenshot')),
            'loaded_miles': _number_field(facts.loaded_miles,
                                          sources.get('loaded_miles', 'screenshot')),
            'deadhead_miles': _number_field(facts.deadhead_miles,
                                            sources.get('deadhead_miles', 'screenshot')),
            'weight_lbs': _number_field(facts.weight_lbs,
                                        sources.get('weight_lbs', 'screenshot'))},
        'pricing': {
            'target_all_mile_rpm': _number_field(pricing.target_all_mile_rpm,
                                                sources.get('target_all_mile_rpm', 'carrier')),
            'operating_cpm': _number_field(pricing.operating_cpm,
                                           sources.get('operating_cpm', 'carrier')),
            'expense_claim': _text_field(pricing.expense_claim, 'carrier'),
            'minimum_job_charge': _number_field(pricing.minimum_job_charge,
                                               sources.get('minimum_job_charge', 'carrier')),
            'reposition_miles': _number_field(pricing.reposition_miles,
                                             sources.get('reposition_miles', 'carrier'))},
        'trip': {
            'duration_note': _text_field(trip.duration_note,
                                         sources.get('duration_note', 'carrier')),
            'availability': _text_field(trip.availability
                                        if trip.availability != 'unknown' else None,
                                        sources.get('availability', 'carrier')),
            'handling_note': _text_field(trip.handling_note,
                                         sources.get('handling_note', 'carrier'))},
        'profile': profile_payload(profile),
        'counter_note': _text_field(snapshot.counter_note, 'carrier'),
        'issues': list(snapshot.draft.issues),
        'mileage_proposals': propose_mileage(snapshot),
        'mileage_candidates': mileage_candidates(snapshot)}
    if snapshot.counter_offer is not None:
        review['counter_offer'] = _number_field(
            snapshot.counter_offer, sources.get('counter_offer', 'carrier'))
    else:
        review['counter_offer'] = {'value': None, 'state': 'unknown', 'source': 'unknown'}
    compensation, source = effective_compensation(snapshot)
    review['evaluated_compensation'] = _number_field(compensation, source)
    return review


def evaluation_status(inbox, carrier, revision):
    """Durable status of a carrier+revision evaluation, if one was queued."""
    with inbox._lock:
        row = inbox._db.execute(
            "SELECT update_id, status FROM pilot_updates WHERE carrier=? AND action='opening' "
            'AND revision=? ORDER BY update_id DESC LIMIT 1', (carrier, revision)).fetchone()
        category = None
        if row is not None:
            kept = inbox._db.execute(
                'SELECT category FROM pilot_failure_categories WHERE update_id=?',
                (row[0],)).fetchone()
            category = kept[0] if kept else None
    if row is None:
        return {'state': 'not_requested'}
    update_id, status = row[0], row[1]
    if status in ('queued', 'processing', 'sending'):
        return {'state': 'pending', 'update_id': update_id}
    if status == 'completed':
        return {'state': 'completed', 'update_id': update_id}
    # Sanitized enum only; never exception text or provider detail.
    from .pilot_execution import FAILURE_CATEGORIES
    return {'state': 'uncertain', 'update_id': update_id,
            'failure_category': category if category in FAILURE_CATEGORIES else 'unknown'}


def build_state(inbox, user, chat):
    """Full Mini App state. Reads only; spends nothing."""
    with inbox._lock:
        carrier = inbox._bindings[(user, chat)]
        staging = getattr(inbox, '_miniapp_staging', {}).get(carrier)
    opening = getattr(inbox, '_opening', None)
    if opening is None:
        raise ValueError('Opening workflow unavailable')
    try:
        profile = opening.get_profile(user, chat)
    except KeyError:
        profile = None
    if profile is None:
        state = {'stage': 'profile',
                 'staged_profile': profile_payload(staging['profile']) if staging else None,
                 'stage_token': staging['token'] if staging else None}
        return state
    try:
        snapshot = opening.get(user, chat)
    except KeyError:
        return {'stage': 'photo', 'profile': profile_payload(profile)}
    state = {'profile': profile_payload(profile), 'review': review_payload(snapshot, profile)}
    if not snapshot.confirmed:
        state['stage'] = 'review'
        return state
    stored = opening.last_result(user, chat)
    if stored is not None and stored[1].get('revision') == snapshot.revision:
        kind, result = stored
        state.update(stage='decided', evaluation_kind=kind, result=result,
                     guidance=negotiation_guidance(kind, result))
        return state
    status = evaluation_status(inbox, carrier, snapshot.revision)
    if status['state'] == 'pending':
        state.update(stage='evaluating', evaluation=status)
    elif status['state'] == 'uncertain':
        state.update(stage='confirmed', evaluation=status)
    else:
        state.update(stage='confirmed')
    return state


def check_request_id(request_id):
    if not isinstance(request_id, str) or REQUEST_ID_PATTERN.fullmatch(request_id) is None:
        raise ValueError('Single-use request id required')
    return request_id


def prior_request(inbox, request_id):
    with inbox._lock:
        return inbox._db.execute(
            'SELECT carrier, kind, revision, update_id, status FROM miniapp_requests '
            'WHERE request_id=?', (request_id,)).fetchone()


def claim_request(inbox, request_id, carrier, kind, revision):
    """Single-attempt claim. True executes; False means duplicate or in-flight.

    A failed attempt keeps its row: the client retries with a NEW request_id.
    This closes the concurrent-duplicate race via the primary key.
    """
    with inbox._lock:
        if inbox._db.execute('SELECT count(*) FROM miniapp_requests').fetchone()[0] >= 10000:
            raise RuntimeError('Mini App capacity reached')
        try:
            with inbox._db:
                inbox._db.execute('INSERT INTO miniapp_requests VALUES (?,?,?,?,?,?,?)',
                                  (request_id, carrier, kind, revision, None, 'received',
                                   time.time()))
        except Exception:
            return False
        return True


def complete_request(inbox, request_id, update_id=None):
    with inbox._lock, inbox._db:
        inbox._db.execute("UPDATE miniapp_requests SET update_id=?, status='completed' "
                          'WHERE request_id=?', (update_id, request_id))


def mount_miniapp(app, inbox, *, bot_token, allowed_host):
    """Mount authenticated Mini App routes on the pilot app. No model calls here."""
    if not isinstance(bot_token, str) or not bot_token:
        raise ValueError('Explicit bot token required for Mini App verification')
    if not _is_valid_hostname(allowed_host):
        raise ValueError('Exact allowed host required')
    ensure_miniapp_tables(inbox)
    from pathlib import Path
    page = Path(__file__).with_name('miniapp.html').read_text()
    app_js = Path(__file__).with_name('miniapp_app.js').read_text()
    # Official circular brand mark, vendored byte-identical from the
    # pre-existing product website (axle-icon-512.png, 512x512 RGBA).
    # Served only through the narrow route below; never redrawn.
    logo_png = Path(__file__).with_name('miniapp_logo.png').read_bytes()

    def denied(code, message):
        return JSONResponse({'ok': False, 'error': message}, status_code=code,
                            headers=dict(NO_STORE))

    async def read_json(request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > BODY_MAX_BYTES:
                raise ValueError('Request too large')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Duplicate request field')
                result[key] = value
            return result
        data = json.loads(body, object_pairs_hook=unique)
        if not isinstance(data, dict):
            raise ValueError('Invalid request')
        return data

    def authenticate(data):
        claimed = verify_init_data(data.get('initData'), bot_token, now=int(time.time()))
        user, chat, carrier = resolve_owner(inbox, claimed['user_id'])
        with inbox._lock:
            access = inbox._active.get(carrier)
            token = access.token if access is not None else None
        if token is None:
            raise PermissionError('Run /start in the bot first')
        inbox._access(user, chat, token)
        generation = hashlib.sha256(token.encode('ascii')).hexdigest()
        bind_launch_session(inbox, carrier, claimed['auth_date'], generation)
        return user, chat, carrier, token

    def conflict(user, chat, message):
        return JSONResponse({'ok': False, 'error': message, 'conflict': True,
                             'state': build_state(inbox, user, chat)}, status_code=409,
                            headers=dict(NO_STORE))

    @app.get('/miniapp')
    @app.get('/miniapp/')
    async def miniapp_page(request: Request):
        if request.headers.get('host') != allowed_host:
            return HTMLResponse('Not found', status_code=404, headers=dict(NO_STORE))
        return HTMLResponse(page, headers={**NO_STORE,
            'Content-Security-Policy': PAGE_CSP})

    @app.get('/miniapp/app.js')
    async def miniapp_script(request: Request):
        # Same-origin application script; the page carries no inline code,
        # keeping script-src free of unsafe-inline.
        if request.headers.get('host') != allowed_host:
            return HTMLResponse('Not found', status_code=404, headers=dict(NO_STORE))
        return HTMLResponse(app_js, media_type='application/javascript',
                            headers={**NO_STORE,
                                     'Content-Security-Policy': PAGE_CSP,
                                     'X-Content-Type-Options': 'nosniff'})

    @app.get('/miniapp/logo.png')
    async def miniapp_logo(request: Request):
        # Single vendored brand asset; same Host gating as page/script.
        # Page CSP already allows img-src 'self', so no policy change.
        if request.headers.get('host') != allowed_host:
            return HTMLResponse('Not found', status_code=404, headers=dict(NO_STORE))
        from fastapi.responses import Response
        return Response(logo_png, media_type='image/png',
                        headers={**NO_STORE, 'X-Content-Type-Options': 'nosniff'})

    @app.post('/miniapp/api/state')
    async def miniapp_state(request: Request):
        if request.headers.get('host') != allowed_host:
            return denied(403, 'rejected')
        try:
            data = await read_json(request)
            user, chat, _, _ = authenticate(data)
            return JSONResponse({'ok': True, 'state': build_state(inbox, user, chat)},
                                headers=dict(NO_STORE))
        except PermissionError as exc:
            return denied(403, str(exc)[:120])
        except (ValueError, KeyError, TypeError) as exc:
            return denied(400, str(exc)[:160] or 'invalid_request')
        except Exception:
            return denied(503, 'unavailable')

    @app.post('/miniapp/api/profile')
    async def miniapp_profile(request: Request):
        if request.headers.get('host') != allowed_host:
            return denied(403, 'rejected')
        try:
            data = await read_json(request)
            user, chat, carrier, _ = authenticate(data)
            request_id = check_request_id(data.get('request_id'))
            fields = data.get('fields')
            if not isinstance(fields, dict) or not fields or len(fields) > 8:
                raise ValueError('Profile fields required')
            if not claim_request(inbox, request_id, carrier, 'profile', None):
                row = prior_request(inbox, request_id)
                if row is not None and row[4] == 'completed':
                    return JSONResponse({'ok': True, 'duplicate': True,
                                         'state': build_state(inbox, user, chat)},
                                        headers=dict(NO_STORE))
                return denied(409, 'Request already received')
            opening = getattr(inbox, '_opening', None)
            if opening is None:
                complete_request(inbox, request_id)
                raise ValueError('Opening workflow unavailable')
            try:
                staged = validate_profile_pairs(fields)
            except ValueError:
                complete_request(inbox, request_id)
                raise
            with inbox._lock:
                inbox._miniapp_staging[carrier] = {
                    'profile': staged, 'token': token_urlsafe(16),
                    'version': opening.profile_version(user, chat)}
            complete_request(inbox, request_id)
            touch_conversation(inbox, carrier)
            return JSONResponse({'ok': True, 'state': build_state(inbox, user, chat)},
                                headers=dict(NO_STORE))
        except PermissionError as exc:
            return denied(403, str(exc)[:120])
        except (ValueError, KeyError, TypeError) as exc:
            return denied(400, str(exc)[:160] or 'invalid_request')
        except Exception:
            return denied(503, 'unavailable')

    @app.post('/miniapp/api/profile/confirm')
    async def miniapp_profile_confirm(request: Request):
        if request.headers.get('host') != allowed_host:
            return denied(403, 'rejected')
        try:
            data = await read_json(request)
            user, chat, carrier, _ = authenticate(data)
            request_id = check_request_id(data.get('request_id'))
            if not claim_request(inbox, request_id, carrier, 'profile_confirm', None):
                row = prior_request(inbox, request_id)
                if row is not None and row[4] == 'completed':
                    return JSONResponse({'ok': True, 'duplicate': True,
                                         'state': build_state(inbox, user, chat)},
                                        headers=dict(NO_STORE))
                return denied(409, 'Request already received')
            opening = getattr(inbox, '_opening', None)
            if opening is None:
                complete_request(inbox, request_id)
                raise ValueError('Opening workflow unavailable')
            presented = data.get('stage_token')
            if not isinstance(presented, str) or not presented:
                complete_request(inbox, request_id)
                raise ValueError('Profile review token required')
            with inbox._lock:
                staged = inbox._miniapp_staging.get(carrier)
            if staged is None or not hmac.compare_digest(staged['token'], presented):
                complete_request(inbox, request_id)
                return conflict(user, chat, 'This profile review is stale; submit the form again')
            try:
                opening.set_profile_expected(user, chat, staged['profile'],
                                             expected_version=staged['version'])
            except ValueError:
                with inbox._lock:
                    inbox._miniapp_staging.pop(carrier, None)
                complete_request(inbox, request_id)
                return conflict(user, chat, 'The profile changed elsewhere; review the current state')
            with inbox._lock:
                inbox._miniapp_staging.pop(carrier, None)
            complete_request(inbox, request_id)
            touch_conversation(inbox, carrier)
            return JSONResponse({'ok': True, 'state': build_state(inbox, user, chat)},
                                headers=dict(NO_STORE))
        except PermissionError as exc:
            return denied(403, str(exc)[:120])
        except (ValueError, KeyError, TypeError) as exc:
            return denied(400, str(exc)[:160] or 'invalid_request')
        except Exception:
            return denied(503, 'unavailable')

    @app.post('/miniapp/api/correct')
    async def miniapp_correct(request: Request):
        if request.headers.get('host') != allowed_host:
            return denied(403, 'rejected')
        try:
            data = await read_json(request)
            user, chat, carrier, _ = authenticate(data)
            request_id = check_request_id(data.get('request_id'))
            expected = data.get('expected_revision')
            fields = data.get('fields')
            if type(expected) is not int or not isinstance(fields, dict) or not fields:
                raise ValueError('Revision and fields required')
            if len(fields) > 16 or any(key not in FIELD_LABELS for key in fields):
                raise ValueError('Unexpected correction field')
            if not claim_request(inbox, request_id, carrier, 'correct', expected):
                row = prior_request(inbox, request_id)
                if row is not None and row[4] == 'completed':
                    return JSONResponse({'ok': True, 'duplicate': True,
                                         'state': build_state(inbox, user, chat)},
                                        headers=dict(NO_STORE))
                return denied(409, 'Request already received')
            opening = getattr(inbox, '_opening', None)
            if opening is None:
                complete_request(inbox, request_id)
                raise ValueError('Opening workflow unavailable')
            try:
                snapshot = opening.get(user, chat)
            except KeyError:
                complete_request(inbox, request_id)
                raise ValueError('Upload a screenshot in the bot first') from None
            if snapshot.revision != expected:
                complete_request(inbox, request_id)
                return conflict(user, chat, 'This review is stale; the latest revision is shown')
            try:
                apply_pairs_to_snapshot(opening, user, chat, snapshot, fields)
            except ValueError as exc:
                complete_request(inbox, request_id)
                if 'Stale' in str(exc):
                    return conflict(user, chat, 'This review is stale; the latest revision is shown')
                raise
            complete_request(inbox, request_id)
            touch_conversation(inbox, carrier)
            return JSONResponse({'ok': True, 'state': build_state(inbox, user, chat)},
                                headers=dict(NO_STORE))
        except PermissionError as exc:
            return denied(403, str(exc)[:120])
        except (ValueError, KeyError, TypeError) as exc:
            return denied(400, str(exc)[:160] or 'invalid_request')
        except Exception:
            return denied(503, 'unavailable')

    @app.post('/miniapp/api/confirm')
    async def miniapp_confirm(request: Request):
        if request.headers.get('host') != allowed_host:
            return denied(403, 'rejected')
        try:
            data = await read_json(request)
            user, chat, carrier, _ = authenticate(data)
            request_id = check_request_id(data.get('request_id'))
            revision = data.get('revision')
            if type(revision) is not int:
                raise ValueError('Revision required')
            if not claim_request(inbox, request_id, carrier, 'confirm', revision):
                row = prior_request(inbox, request_id)
                if row is not None and row[4] == 'completed':
                    return JSONResponse({'ok': True, 'duplicate': True,
                                         'state': build_state(inbox, user, chat)},
                                        headers=dict(NO_STORE))
                return denied(409, 'Request already received')
            opening = getattr(inbox, '_opening', None)
            if opening is None:
                complete_request(inbox, request_id)
                raise ValueError('Opening workflow unavailable')
            try:
                opening.confirm(user, chat, revision)
            except (KeyError, ValueError):
                complete_request(inbox, request_id)
                try:
                    return conflict(user, chat, 'This review is stale; no confirmation was granted')
                except (KeyError, ValueError):
                    raise ValueError('Nothing to confirm') from None
            complete_request(inbox, request_id)
            touch_conversation(inbox, carrier)
            return JSONResponse({'ok': True, 'state': build_state(inbox, user, chat)},
                                headers=dict(NO_STORE))
        except PermissionError as exc:
            return denied(403, str(exc)[:120])
        except (ValueError, KeyError, TypeError) as exc:
            return denied(400, str(exc)[:160] or 'invalid_request')
        except Exception:
            return denied(503, 'unavailable')

    @app.post('/miniapp/api/evaluate')
    async def miniapp_evaluate(request: Request):
        if request.headers.get('host') != allowed_host:
            return denied(403, 'rejected')
        try:
            data = await read_json(request)
            user, chat, carrier, token = authenticate(data)
            request_id = check_request_id(data.get('request_id'))
            revision = data.get('revision')
            if type(revision) is not int:
                raise ValueError('Revision required')
            if not claim_request(inbox, request_id, carrier, 'evaluate', revision):
                row = prior_request(inbox, request_id)
                if row is None or row[4] != 'completed':
                    return denied(409, 'Request already received')
                return JSONResponse({'ok': True, 'duplicate': True,
                                     'evaluation': evaluation_status(
                                         inbox, carrier, revision),
                                     'state': build_state(inbox, user, chat)},
                                    headers=dict(NO_STORE))
            opening = getattr(inbox, '_opening', None)
            if opening is None:
                complete_request(inbox, request_id)
                raise ValueError('Opening workflow unavailable')
            # Check-and-queue runs under one lock hold so concurrent requests
            # for the same revision cannot queue two evaluations.
            with inbox._lock:
                try:
                    snapshot = opening.get(user, chat)
                except KeyError:
                    complete_request(inbox, request_id)
                    raise ValueError('Nothing to evaluate') from None
                if snapshot.revision != revision or not snapshot.confirmed:
                    complete_request(inbox, request_id)
                    return conflict(user, chat, 'Confirm the current revision first')
                blockers = pricing_blockers(snapshot)
                if blockers:
                    complete_request(inbox, request_id)
                    return JSONResponse(
                        {'ok': False,
                         'error': 'Add these before pricing: '
                                  + ', '.join(missing_input_labels(blockers)),
                         'missing': blockers,
                         'state': build_state(inbox, user, chat)},
                        status_code=409, headers=dict(NO_STORE))
                stored = opening.last_result(user, chat)
                if stored is not None and stored[1].get('revision') == revision:
                    complete_request(inbox, request_id)
                    return JSONResponse({'ok': True, 'evaluation': {'state': 'completed'},
                                         'state': build_state(inbox, user, chat)},
                                        headers=dict(NO_STORE))
                pending = evaluation_status(inbox, carrier, revision)
                if pending['state'] == 'pending':
                    complete_request(inbox, request_id, pending.get('update_id'))
                    return JSONResponse({'ok': True, 'evaluation': pending,
                                         'state': build_state(inbox, user, chat)},
                                        headers=dict(NO_STORE))
                if (pending['state'] == 'uncertain'
                        and data.get('retry_uncertain') is not True):
                    # Accidental repeats after uncertainty never spend again.
                    # The carrier edits (fresh revision) or retries explicitly.
                    complete_request(inbox, request_id, pending.get('update_id'))
                    return JSONResponse({'ok': True, 'evaluation': pending,
                                         'state': build_state(inbox, user, chat)},
                                        headers=dict(NO_STORE))
                update_id = allocate_miniapp_update_id(inbox)
                accepted = inbox.submit(user, chat, update_id, 'opening', token=token,
                                        revision=revision,
                                        allow_uncertain_retry=data.get(
                                            'retry_uncertain') is True)
                complete_request(inbox, request_id, update_id)
                status = {'state': 'pending', 'update_id': update_id}
                if not accepted:
                    status = evaluation_status(inbox, carrier, revision)
                return JSONResponse({'ok': True, 'evaluation': status,
                                     'state': build_state(inbox, user, chat)},
                                    headers=dict(NO_STORE))
        except PermissionError as exc:
            return denied(403, str(exc)[:120])
        except (ValueError, KeyError, TypeError) as exc:
            return denied(400, str(exc)[:160] or 'invalid_request')
        except Exception:
            return denied(503, 'unavailable')

    @app.post('/miniapp/api/forget')
    async def miniapp_forget(request: Request):
        if request.headers.get('host') != allowed_host:
            return denied(403, 'rejected')
        try:
            data = await read_json(request)
            user, chat, carrier, _ = authenticate(data)
            request_id = check_request_id(data.get('request_id'))
            if not claim_request(inbox, request_id, carrier, 'forget', None):
                return denied(409, 'Request already received')
            update_id = allocate_miniapp_update_id(inbox)
            inbox.submit(user, chat, update_id, 'forget')
            with inbox._lock, inbox._db:
                inbox._conversation_states.pop(carrier, None)
                inbox._miniapp_staging.pop(carrier, None)
                inbox._db.execute('DELETE FROM miniapp_launches WHERE carrier=?', (carrier,))
            complete_request(inbox, request_id, update_id)
            return JSONResponse({'ok': True, 'forgotten': True}, headers=dict(NO_STORE))
        except PermissionError as exc:
            return denied(403, str(exc)[:120])
        except (ValueError, KeyError, TypeError) as exc:
            return denied(400, str(exc)[:160] or 'invalid_request')
        except Exception:
            return denied(503, 'unavailable')

    return app
