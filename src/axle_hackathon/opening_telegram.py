"""Injected, offline-tested opening boundary. No launcher, secrets or live sends."""
import asyncio
import json
import re
from decimal import Decimal
from secrets import token_urlsafe
from threading import BoundedSemaphore
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .opening_intake import IntakeFacts, ScreenshotDraft, parse_media_update
from .opening_workflow import (OpeningPricing, OpeningProfile, OpeningTrip,
                               display_expense_claim, render_review)
from .pilot_delivery import DeliveryPool
from .pilot_execution import failure_category_for
from .pilot_memory import _token_matches
from .remote_app import _is_valid_hostname

QUESTIONS = ('Useful next details: cargo commodity and weight confirmation, handling or '
    'equipment needs, loading/unloading appointments, and schedule feasibility. Unknown '
    'schedule allows preliminary pricing but blocks full acceptance.')
PROFILE_PROMPT = ('Send your carrier profile in one message (one item per line, or separated '
    'by semicolons). Labels: cpm ($/mile, all operating expenses), target ($/mile revenue), '
    'minimum (job charge, or none), equipment, context. Example:\n'
    'cpm 1.25\ntarget 2.50\nminimum 100\nequipment 26ft box truck\ncontext solo, no hazmat')
TRIP_PROMPT = ('Send trip details in one message, or "skip". Labels: deadhead (miles to pickup), '
    'reposition (extra miles), duration, availability (feasible, blocked, or unknown), handling. Example:\n'
    'deadhead 40\nreposition 20\nduration 6 hours\navailability feasible\nhandling liftgate required')
PHOTO_PROMPT = ('Send one PNG or JPEG screenshot of the opportunity. '
    'Processing before consent is never performed; /forget withdraws consent.')


def _decimal(value, *, name, low, high, allow_zero):
    try:
        number = Decimal(value)
    except (ArithmeticError, ValueError, TypeError):
        raise ValueError(f'Invalid {name}') from None
    if not number.is_finite():
        raise ValueError(f'Invalid {name}')
    if (number < low or number > high or (not allow_zero and number == low)):
        raise ValueError(f'Invalid {name}')
    return number


def _unknown(value):
    return None if value.lower() in ('unknown', 'skip') else value


_UNITS = ('per mile', '/mi', 'rpm', 'cpm', 'miles', 'mile', 'mi', 'usd', '$',
          'hours', 'hour', 'hrs', 'hr', 'lbs', 'lb')


def _number(value, *, name):
    """One decimal token with an optional familiar unit. Ambiguity rejected."""
    cleaned = value.replace('$', '').replace(',', '').strip()
    lowered = cleaned.lower()
    for unit in _UNITS:
        if lowered.endswith(unit):
            cleaned = cleaned[: -len(unit)].strip()
            break
    if not cleaned or any(ch.isspace() for ch in cleaned):
        raise ValueError(f'Invalid {name}')
    return cleaned


# Canonical field -> accepted labels. Correction messages accept every field;
# the profile step accepts the pricing/equipment subset only.
FIELD_LABELS = {
    'payout': ('payout', 'pay', 'compensation', 'offer'),
    'loaded_miles': ('loaded', 'loaded miles', 'loaded mi', 'ld'),
    'deadhead_miles': ('deadhead', 'deadhead miles', 'deadhead mi', 'dh', 'dead head'),
    'weight_lbs': ('weight', 'weight lbs', 'wt'),
    'target_all_mile_rpm': ('target', 'target rpm', 'revenue target', 'all-mile rpm', 'all mile rpm'),
    'operating_cpm': ('cpm', 'operating cpm', 'operating cost', 'all-in cpm', 'all in cpm'),
    'minimum_job_charge': ('minimum', 'minimum charge', 'min charge', 'min'),
    'reposition_miles': ('reposition', 'reposition miles', 'reposition mi', 'repo'),
    'duration_note': ('duration', 'expected duration', 'job duration', 'time'),
    'availability': ('availability', 'schedule', 'schedule feasibility', 'feasible'),
    'handling_note': ('handling', 'handling notes', 'service', 'service needs'),
    'equipment': ('equipment', 'truck', 'vehicle'),
    'operating_context': ('context', 'operating context', 'about'),
    'counter': ('counter', 'counteroffer', 'counter offer'),
}
PROFILE_FIELDS = ('operating_cpm', 'target_all_mile_rpm', 'minimum_job_charge',
                  'equipment', 'operating_context')


def _label_map(fields):
    mapping = {}
    for name in fields:
        for label in FIELD_LABELS[name]:
            mapping[label] = name
    return mapping


def parse_fields(text, fields):
    """Deterministic consolidated parsing. Unknown/duplicate labels rejected."""
    entries = [chunk.strip() for chunk in re.split(r'[\n;]+', text) if chunk.strip()]
    if not entries:
        raise ValueError('Send at least one "label value" pair')
    if len(entries) > 16:
        raise ValueError('Too many entries in one message')
    mapping = _label_map(fields)
    found = {}
    for entry in entries[:16]:
        piece, lowered = entry[:600], entry[:600].lower()
        best = None
        for label in mapping:
            if (lowered == label or lowered.startswith(label + ' ')
                    or lowered.startswith(label + ':') or lowered.startswith(label + '=')):
                if best is None or len(label) > len(best):
                    best = label
        if best is None:
            head = piece.split(' ', 1)[0][:40]
            raise ValueError(f"Unknown label '{head}'; use: " + ', '.join(sorted(mapping)))
        value = piece[len(best):].lstrip(' :=').strip()
        if not value:
            raise ValueError(f"'{best}' needs a value")
        if mapping[best] in found:
            raise ValueError(f"Duplicate '{best}'; send each field once")
        found[mapping[best]] = value
    return found


_RETIRE_KEYWORDS = {
    'payout': ('payout',), 'loaded_miles': ('loaded',), 'deadhead_miles': ('deadhead',),
    'weight_lbs': ('weight',), 'target_all_mile_rpm': ('target',),
    'operating_cpm': ('cpm', 'cost'), 'minimum_job_charge': ('minimum',),
    'reposition_miles': ('reposition',), 'duration_note': ('duration',),
    'availability': ('availability', 'feasible', 'schedule'),
    'handling_note': ('handling', 'service'), 'counter': ('counter',),
}


class OpeningConversation:
    """Deterministic opening intake; no model extraction or synthetic reuse."""
    def __init__(self, inbox):
        self.inbox = inbox
        self._flows = inbox._conversation_states

    @property
    def opening(self):
        opening = getattr(self.inbox, '_opening', None)
        if opening is None:
            raise ValueError('Opening workflow unavailable')
        return opening

    def clear(self, user, chat):
        with self.inbox._lock:
            self._flows.pop(self.inbox._carrier(user, chat), None)

    def handle(self, user, chat, text):
        """Trusted transport calls under inbox lock; callbacks contain an opaque step nonce."""
        with self.inbox._lock:
            carrier = self.inbox._carrier(user, chat)
            if text == '/start':
                self.inbox._clear(carrier)
                notice = self.inbox.disclosure(user, chat)
                self._flows[carrier] = dict(step='memory', nonce=token_urlsafe(12), notice=notice,
                                           values={}, token=None)
                return self._prompt(carrier, notice.text + '\nReal opening-price test. '
                    'Reply session or remember. Reply only while safely parked.')
            flow = self._flows.get(carrier)
            if flow is None:
                raise ValueError('Start a fresh intake with /start')
            if text == '/refresh':
                return self._refresh(carrier, flow)
            parts = text.split(' ', 2)
            if len(parts) < 2 or parts[1] != flow['nonce']:
                # Plain messages carry no nonce; commands without one are stale.
                if parts[0].startswith('/'):
                    raise ValueError('Stale conversation step')
                return self._plain(user, chat, carrier, flow, text)
            if flow['step'] != 'memory':
                try:
                    self.inbox._access(user, chat, flow['token'])
                except PermissionError:
                    self._flows.pop(carrier, None)
                    raise
            command = parts[0]
            value = parts[2] if len(parts) == 3 else ''
            if command == '/confirm' and not value:
                if flow['step'] == 'profile_review':
                    return self._confirm_profile(user, chat, carrier, flow)
                if flow['step'] == 'review':
                    self.opening.confirm(user, chat, flow['revision'])
                    flow['nonce'] = token_urlsafe(12)
                    flow['step'] = 'confirmed'
                    return self._prompt(carrier, f'Confirmed opening revision {flow["revision"]}. '
                        'Use /price for a preliminary opening price or offer evaluation, '
                        'or correct a field. Corrections require fresh confirmation. '
                        '/forget withdraws consent.')
                raise ValueError('Nothing to confirm at this step')
            if command == '/edit' and value and flow['step'] in ('trip', 'review', 'confirmed'):
                return self._apply_message(user, chat, carrier, flow, value)
            if command != '/reply':
                raise ValueError('Unexpected conversation command')
            if flow['step'] == 'memory':
                choices = {'session': 'session_only', 'remember': 'remember_profile'}
                if value not in choices:
                    raise ValueError('Choose session or remember')
                access = self.inbox.consent(user, chat, flow['notice'].token, choices[value])
                flow['token'] = access.token
                self._flows[carrier] = flow
                return self._advance(carrier, 'profile', 'Consent recorded. ' + PROFILE_PROMPT)
            raise ValueError('Unexpected conversation step')

    def _plain(self, user, chat, carrier, flow, text):
        step = flow['step']
        if step in ('profile', 'profile_review'):
            return self._profile_message(user, chat, carrier, flow, text)
        if step == 'photo':
            raise ValueError('Send one PNG or JPEG screenshot of the opportunity first')
        if step == 'trip':
            if text.strip().lower() == 'skip':
                try:
                    self.inbox._access(user, chat, flow['token'])
                except PermissionError:
                    self._flows.pop(carrier, None)
                    raise
                snapshot = self.opening.get(user, chat)
                flow['revision'] = snapshot.revision
                flow['step'] = 'review'
                flow['trip_done'] = True
                flow['nonce'] = token_urlsafe(12)
                return self._prompt(carrier, render_review(snapshot, self._profile(user, chat))
                                    + '\n' + QUESTIONS)
            return self._apply_message(user, chat, carrier, flow, text)
        if step in ('review', 'confirmed'):
            return self._correct(user, chat, carrier, flow, text)
        raise ValueError('Reply to the current step or use /refresh')

    def _profile(self, user, chat):
        try:
            return self.opening.get_profile(user, chat)
        except (KeyError, ValueError):
            return None

    def _profile_message(self, user, chat, carrier, flow, text):
        try:
            self.inbox._access(user, chat, flow['token'])
        except PermissionError:
            self._flows.pop(carrier, None)
            raise
        profile = validate_profile_pairs(parse_fields(text, PROFILE_FIELDS))
        flow['profile_values'] = profile
        flow['step'] = 'profile_review'
        flow['nonce'] = token_urlsafe(12)
        return self._prompt(carrier, self._render_profile(profile))

    def _confirm_profile(self, user, chat, carrier, flow):
        profile = flow.get('profile_values')
        if profile is None:
            raise ValueError('Send the profile message first')
        self.opening.set_profile(user, chat, profile)
        return self._advance(carrier, 'photo',
            'Profile confirmed and reused for this session. ' + PHOTO_PROMPT)

    def _refresh(self, carrier, flow):
        if flow['step'] == 'memory':
            if flow['notice'].expires_at <= self.inbox._now():
                self._flows.pop(carrier, None)
                raise ValueError('Disclosure expired')
            return self._prompt(carrier, flow['last_prompt'])
        user, chat = next(k for k, value in self.inbox._bindings.items() if value == carrier)
        try:
            self.inbox._access(user, chat, flow['token'])
        except PermissionError:
            self._flows.pop(carrier, None)
            raise
        notice = flow.pop('screenshot_notice', False)
        def done(prompt):
            if notice:
                prompt += ('\nLast screenshot was not processed; no draft was created and '
                           'nothing was sent. Send a new PNG or JPEG screenshot, or /forget.')
            return self._prompt(carrier, prompt, save=not notice)
        if flow['step'] in ('profile', 'profile_review'):
            if flow['step'] == 'profile_review' and flow.get('profile_values') is not None:
                return done(self._render_profile(flow['profile_values']))
            return done(PROFILE_PROMPT)
        if flow['step'] == 'photo':
            try:
                snapshot = self.opening.get(user, chat)
            except KeyError:
                return done(PHOTO_PROMPT)
            flow['revision'] = snapshot.revision
            if flow.get('trip_done'):
                flow['step'] = 'review'
                return done(render_review(snapshot, self._profile(user, chat)) + '\n' + QUESTIONS)
            flow['step'] = 'trip'
            return done(render_review(snapshot, self._profile(user, chat)) + '\n' + TRIP_PROMPT)
        if flow['step'] == 'trip':
            try:
                snapshot = self.opening.get(user, chat)
            except KeyError:
                flow['step'] = 'photo'
                return done(PHOTO_PROMPT)
            return done(render_review(snapshot, self._profile(user, chat)) + '\n' + TRIP_PROMPT)
        snapshot = self.opening.get(user, chat)
        if snapshot.revision != flow.get('revision'):
            flow['revision'] = snapshot.revision
            flow['step'] = 'review'
        if flow['step'] == 'confirmed' and not snapshot.confirmed:
            flow['step'] = 'review'
        if flow['step'] == 'review':
            return done(render_review(snapshot, self._profile(user, chat)) + '\n' + QUESTIONS)
        return done(f'Confirmed opening revision {snapshot.revision}. '
            'Use /price for a preliminary opening price or offer evaluation, or correct a field.')

    def _render_profile(self, profile):
        def shown(value):
            return str(value) if value is not None else 'unknown'
        return ('SESSION PROFILE — review before screenshot upload:\n'
            f'operating CPM: {shown(profile.operating_cpm)}\n'
            f'expense claim: {display_expense_claim(profile.expense_claim)}\n'
            f'target all-mile RPM: {shown(profile.target_all_mile_rpm)}\n'
            f'minimum job charge: {shown(profile.minimum_job_charge)}\n'
            f'equipment: {shown(profile.equipment)}\n'
            f'operating context: {shown(profile.operating_context)}\n'
            'Use /confirm to confirm this profile, or re-send the profile message.')

    def _correct(self, user, chat, carrier, flow, text):
        if flow['step'] not in ('review', 'confirmed'):
            raise ValueError('Send one screenshot first; corrections apply to its draft')
        return self._apply_message(user, chat, carrier, flow, text)

    def _apply_message(self, user, chat, carrier, flow, text):
        try:
            self.inbox._access(user, chat, flow['token'])
        except PermissionError:
            self._flows.pop(carrier, None)
            raise
        pairs = parse_fields(text, tuple(FIELD_LABELS))
        snapshot = self.opening.get(user, chat)
        updated = self._apply_pairs(user, chat, snapshot, pairs)
        flow['revision'] = updated.revision
        flow['step'] = 'review'
        flow['trip_done'] = True
        flow['nonce'] = token_urlsafe(12)
        return self._prompt(carrier, render_review(updated, self._profile(user, chat))
                            + '\n' + QUESTIONS)

    def _apply_pairs(self, user, chat, snapshot, pairs):
        return apply_pairs_to_snapshot(self.opening, user, chat, snapshot, pairs)

    def _advance(self, carrier, step, prompt):
        self._flows[carrier].update(step=step, nonce=token_urlsafe(12))
        return self._prompt(carrier, prompt)

    def _prompt(self, carrier, prompt, *, save=True):
        if save:
            self._flows[carrier]['last_prompt'] = prompt
        return prompt + step_trailer(self._flows[carrier]['step'], self._flows[carrier]['nonce'])


def validate_profile_pairs(pairs):
    """Shared profile validation for bot text and Mini App JSON. Deterministic."""
    for name in pairs:
        if name not in PROFILE_FIELDS:
            raise ValueError(f'Unexpected profile field {name!r}'[:80])
    values = dict(operating_cpm=None, expense_claim=None, target_all_mile_rpm=None,
                  minimum_job_charge=None, equipment=None, operating_context=None)
    for name, raw in pairs.items():
        if not isinstance(raw, str) or not raw.strip() or len(raw) > 600:
            raise ValueError(f'Invalid {name}')
        parsed = _unknown(raw)
        if name == 'minimum_job_charge':
            if parsed is None:
                raise ValueError('Minimum charge must be supplied, including explicit zero')
            values[name] = Decimal(0) if parsed.lower() == 'none' else _decimal(
                _number(parsed, name=name), name=name, low=Decimal(0),
                high=Decimal(1000000), allow_zero=True)
        elif name == 'operating_cpm':
            if parsed is None:
                continue
            if parsed.lower() == 'itemized':
                raise ValueError('Itemized costs need explicit normalization first; '
                                 'pricing stays unavailable')
            values[name] = _decimal(_number(parsed, name=name), name=name,
                                    low=Decimal(0), high=Decimal(1000), allow_zero=True)
            values['expense_claim'] = 'all_operating_expenses'
        elif name == 'target_all_mile_rpm':
            if parsed is not None:
                values[name] = _decimal(_number(parsed, name=name), name=name,
                                        low=Decimal(0), high=Decimal(1000), allow_zero=False)
        else:
            if parsed is not None:
                cleaned = parsed.strip()[:500 if name == 'operating_context' else 200]
                if not cleaned:
                    raise ValueError(f'Invalid {name}')
                values[name] = cleaned
    if values['minimum_job_charge'] is None:
        raise ValueError('Minimum charge must be supplied, including explicit zero')
    return OpeningProfile.model_validate(values)


def apply_pairs_to_snapshot(opening, user, chat, snapshot, pairs):
    """Shared correction/trip/counteroffer application. Creates one new revision."""
    for name, raw in pairs.items():
        if name not in FIELD_LABELS:
            raise ValueError(f'Unexpected field {name!r}'[:80])
        if not isinstance(raw, str) or not raw.strip() or len(raw) > 600:
            raise ValueError(f'Invalid {name}')
    facts = snapshot.draft.facts.model_dump()
    pricing = snapshot.pricing.model_dump()
    trip = snapshot.trip.model_dump()
    offer, note = snapshot.counter_offer, snapshot.counter_note
    issues = list(snapshot.draft.issues)
    sources = dict(snapshot.sources)
    marked, weight_placeholder = set(), False
    for name in ('equipment', 'operating_context'):
        if name not in pairs:
            continue
        try:
            current = opening.get_profile(user, chat)
        except KeyError:
            current = OpeningProfile()
        data = current.model_dump()
        parsed = _unknown(pairs[name])
        data[name] = None if parsed is None else parsed.strip()[:500 if name == 'operating_context' else 200] or None
        if parsed is not None and data[name] is None:
            raise ValueError(f'Invalid {name}')
        opening.set_profile(user, chat, OpeningProfile.model_validate(data))
    for name, raw in pairs.items():
        if name in ('equipment', 'operating_context'):
            continue
        parsed = _unknown(raw)
        if name == 'counter':
            stripped = raw.strip()
            if stripped.lower() in ('none', 'unknown'):
                offer, note = None, None
            elif re.match(r'^[\d$.,\s-]', stripped):
                offer = _decimal(_number(stripped, name=name), name=name,
                                 low=Decimal(0), high=Decimal(1000000), allow_zero=True)
            else:
                note = stripped[:200] or None
                if note is None:
                    raise ValueError('Invalid counter')
        elif name in ('duration_note', 'handling_note'):
            limit = 200 if name == 'duration_note' else 500
            trip[name] = None if parsed is None else parsed.strip()[:limit] or None
            if parsed is not None and trip[name] is None:
                raise ValueError(f'Invalid {name}')
        elif name == 'availability':
            if parsed is None:
                trip[name] = 'unknown'
            elif parsed.lower() not in ('feasible', 'blocked', 'unknown'):
                raise ValueError('Availability must be feasible, blocked, or unknown')
            else:
                trip[name] = parsed.lower()
        elif name in facts:
            marked.add(name)
            if parsed is None:
                facts[name] = None
            else:
                bounds = {'payout': (0, 1000000, True), 'loaded_miles': (0, 100000, False),
                          'deadhead_miles': (0, 100000, True),
                          'weight_lbs': (0, 200000, True)}[name]
                facts[name] = _decimal(_number(parsed, name=name), name=name,
                                       low=Decimal(bounds[0]), high=Decimal(bounds[1]),
                                       allow_zero=bounds[2])
                if name == 'weight_lbs' and facts[name] == 0:
                    facts[name] = None
                    weight_placeholder = True
        elif name == 'minimum_job_charge':
            if parsed is None:
                raise ValueError('Minimum charge must be supplied, including explicit zero')
            pricing[name] = Decimal(0) if parsed.lower() == 'none' else _decimal(
                _number(parsed, name=name), name=name, low=Decimal(0),
                high=Decimal(1000000), allow_zero=True)
        elif name == 'operating_cpm':
            if parsed is None:
                pricing[name] = None
                pricing['expense_claim'] = None
            elif parsed.lower() == 'itemized':
                raise ValueError('Itemized costs need explicit normalization first; '
                                 'pricing stays unavailable')
            else:
                pricing[name] = _decimal(_number(parsed, name=name), name=name,
                                        low=Decimal(0), high=Decimal(1000), allow_zero=True)
                pricing['expense_claim'] = 'all_operating_expenses'
        elif parsed is None:
            pricing[name] = None
        else:
            bounds = {'target_all_mile_rpm': (0, 1000, False),
                      'reposition_miles': (0, 100000, True)}[name]
            pricing[name] = _decimal(_number(parsed, name=name), name=name,
                                     low=Decimal(bounds[0]), high=Decimal(bounds[1]),
                                     allow_zero=bounds[2])
        sources[name if name != 'counter' else 'counter_offer'] = 'carrier'
    if offer is None:
        sources.pop('counter_offer', None)
    keywords = {word for name in pairs for word in _RETIRE_KEYWORDS.get(name, ())}
    issues = [issue for issue in issues
              if not any(word in issue.lower() for word in keywords)]
    if weight_placeholder and len(issues) < 6 and not any(
            'weight' in issue.lower() for issue in issues):
        issues.append('Displayed zero weight is a placeholder requiring clarification.')
    draft = ScreenshotDraft(status='UNCONFIRMED', facts=IntakeFacts.model_validate(facts),
        evidence={**snapshot.draft.evidence,
                  **{name: 'carrier correction' for name in marked}},
        issues=issues)
    return opening.put(user, chat, draft, OpeningPricing.model_validate(pricing),
        expected_revision=snapshot.revision, trip=OpeningTrip.model_validate(trip),
        counter_offer=offer, counter_note=note, sources=sources)


def step_trailer(step, nonce):
    """Stage-specific instructions; no misleading generic reply footer."""
    if step == 'memory':
        return f'\nStep: {nonce}\nReply format: /reply STEP session|remember'
    if step in ('profile', 'profile_review'):
        return (f'\nStep: {nonce}\nSend one profile message '
                '(cpm, target, minimum, equipment, context)')
    if step == 'photo':
        return '\nSend one PNG or JPEG screenshot of the opportunity.'
    if step == 'trip':
        return ('\nSend trip details in one message, or "skip". '
                'Labels: deadhead, reposition, duration, availability, handling.')
    if step == 'review':
        return (f'\nStep: {nonce}\nReply format: /confirm STEP | '
                '/edit STEP field value | correction as "field value"')
    if step == 'confirmed':
        return (f'\nStep: {nonce}\nReply format: /price | '
                '/edit STEP field value | correction as "field value"')
    return ''


def create_opening_app(inbox, *, webhook_secret: str, allowed_host: str, conversation=None, send=None,
                       miniapp_bot_token: str | None = None, miniapp_button=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', webhook_secret):
        raise ValueError('Explicit webhook secret required')
    if not _is_valid_hostname(allowed_host):
        raise ValueError('Exact allowed host required')
    if len(set(inbox._bindings.values())) != len(inbox._bindings):
        raise ValueError('One approved private-chat binding per carrier required')
    with inbox._lock:
        if not hasattr(inbox, '_flow_slots'):inbox._flow_slots = BoundedSemaphore(2)
        flow_slots = inbox._flow_slots
        if inbox._delivery_pool is None:inbox._delivery_pool=DeliveryPool(None)
        delivery=inbox._delivery_pool
    @asynccontextmanager
    async def lifespan(app):
        try: yield
        finally:
            delivery.close()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None,lifespan=lifespan)

    @app.post('/telegram/webhook')
    async def webhook(request: Request):
        def reply(code, message):
            return JSONResponse({'status': message}, status_code=code,
                                headers={'Cache-Control': 'no-store'})
        if request.headers.get('host') != allowed_host:
            return reply(403, 'rejected')
        secrets = request.headers.getlist('x-telegram-bot-api-secret-token')
        if len(secrets) != 1 or not _token_matches(webhook_secret, secrets[0]):
            return reply(403, 'rejected')
        try:
            body = bytearray()
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 8192:
                        return reply(413, 'too_large')
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError()
                    result[key] = value
                return result
            data = json.loads(body, object_pairs_hook=unique)
            if set(data) != {'update_id', 'message'}:
                return reply(400, 'unsupported_update')
            message = data['message']
            user, chat = message['from']['id'], message['chat']['id']
            if message['chat']['type'] != 'private' or message['from'].get('is_bot') is not False:
                return reply(403, 'rejected')
            text = message.get('text')
            message_id = message.get('message_id')
            has_media = message.get('photo') is not None or message.get('document') is not None
            if has_media:
                if conversation is None or conversation.inbox is not inbox:
                    return reply(503, 'unavailable')
                if not flow_slots.acquire(blocking=False):
                    return reply(503, 'unavailable')
                try:
                    with inbox._lock:
                        carrier = inbox._carrier(user, chat)
                        flow = inbox._conversation_states.get(carrier)
                        token = None
                        if flow is not None and flow['step'] != 'memory':
                            token = flow['token']
                        else:
                            access = inbox._active.get(carrier)
                            token = access.token if access is not None else None
                        if token is None:
                            raise PermissionError()
                        inbox._access(user, chat, token)
                        media = parse_media_update(data, inbox._bindings, consented=True)
                        try:
                            conversation.opening.get_profile(user, chat)
                        except KeyError:
                            if send is None:
                                return reply(503, 'unavailable')
                            if inbox.duplicate_update(user, chat, data['update_id'], 'flow'):
                                return reply(200, 'duplicate')
                            if inbox.stale_message(user, chat, message_id):
                                return reply(200, 'stale')
                            guidance_claim = inbox.begin_flow(
                                user, chat, data['update_id'], message_id=message_id)
                            if guidance_claim is None:
                                return reply(200, 'duplicate')
                            guidance = ('Send your carrier profile first — one message with: '
                                        'cpm, target, minimum, equipment, context. Screenshots '
                                        'are processed only after the confirmed profile.')
                        else:
                            guidance, guidance_claim = None, None
                        if guidance is None:
                            if inbox.duplicate_update(user, chat, data['update_id'], 'screenshot'):
                                return reply(200, 'duplicate')
                            if inbox.stale_message(user, chat, message_id):
                                return reply(200, 'stale')
                            accepted = inbox.submit(user, chat, data['update_id'], 'screenshot',
                                token=token, message_id=message_id, media=dict(
                                    file_id=media.file_id, file_unique_id=media.file_unique_id,
                                    mime=media.mime, reported_size=media.reported_size))
                            if accepted and flow is not None:
                                flow.pop('screenshot_notice', None)
                            return reply(200, 'queued' if accepted else 'duplicate')
                    if guidance is not None:
                        def guidance_guard():
                            with inbox._lock:
                                inbox._access(user, chat, token)
                                inbox.start_delivery(user, chat, data['update_id'], guidance_claim)
                        try:
                            await asyncio.to_thread(delivery.send, chat, guidance,
                                                    guidance_guard, send)
                            inbox.finish(user, chat, data['update_id'], guidance_claim,
                                         success=True)
                        except (Exception, asyncio.CancelledError) as exc:
                            try:
                                inbox.finish(user, chat, data['update_id'], guidance_claim,
                                             success=False)
                            except Exception:
                                pass
                            if isinstance(exc, asyncio.CancelledError):
                                raise
                            return reply(503, 'unavailable')
                        return reply(200, 'processed')
                finally:
                    flow_slots.release()
            if text is None:
                return reply(400, 'unsupported_command')
            if text == '/forget':
                with inbox._lock:
                    carrier = inbox._carrier(user, chat)
                    if type(message_id) is not int or message_id <= 0:
                        return reply(400, 'invalid_update')
                    if inbox.duplicate_update(user, chat, data['update_id'], 'forget',
                                              command_id=message_id):
                        return reply(200, 'duplicate')
                    if inbox.stale_message(user, chat, message_id):
                        return reply(200, 'stale')
                    accepted = inbox.submit(user, chat, data['update_id'], 'forget',
                                            command_id=message_id, message_id=message_id)
                    if conversation is not None:
                        conversation.clear(user, chat)
                if accepted and send is not None:
                    def privacy_guard():
                        with inbox._lock:
                            row = inbox._db.execute('SELECT update_id FROM pilot_privacy '
                                'WHERE carrier=? AND user_id=? AND chat_id=?',
                                (carrier, user, chat)).fetchone()
                            if row != (data['update_id'],) or carrier in inbox._active:
                                raise ValueError('Privacy acknowledgement superseded')
                    try:
                        await asyncio.to_thread(delivery.send, chat,
                            'Consent withdrawn. Active session cleared; saved-profile deletion requested. '
                            'Telegram and provider histories are separate.', privacy_guard, send)
                    except Exception:
                        pass
                return reply(200, 'queued' if accepted else 'duplicate')
            if text == '/app':
                if (conversation is None or conversation.inbox is not inbox
                        or miniapp_button is None):
                    return reply(503, 'unavailable')
                if not flow_slots.acquire(blocking=False):
                    return reply(503, 'unavailable')
                try:
                    with inbox._lock:
                        carrier = inbox._carrier(user, chat)
                        flow = inbox._conversation_states.get(carrier)
                        token = None
                        if flow is not None and flow['step'] != 'memory':
                            token = flow['token']
                        else:
                            access = inbox._active.get(carrier)
                            token = access.token if access is not None else None
                        if token is None:
                            raise PermissionError()
                        inbox._access(user, chat, token)
                        if inbox.duplicate_update(user, chat, data['update_id'], 'flow'):
                            return reply(200, 'duplicate')
                        if inbox.stale_message(user, chat, message_id):
                            return reply(200, 'stale')
                        claim = inbox.begin_flow(
                            user, chat, data['update_id'], message_id=message_id)
                        if claim is None:
                            return reply(200, 'duplicate')
                    def app_guard():
                        with inbox._lock:
                            inbox._access(user, chat, token)
                            inbox.start_delivery(user, chat, data['update_id'], claim)
                    try:
                        await asyncio.to_thread(delivery.send, chat,
                            'Open the Axle review app for guided entry and confirmation. '
                            'The text conversation keeps working.',
                            app_guard,
                            lambda c, t: miniapp_button(c, t, label='Open Axle review'))
                        inbox.finish(user, chat, data['update_id'], claim, success=True)
                    except (Exception, asyncio.CancelledError) as exc:
                        try:
                            inbox.finish(user, chat, data['update_id'], claim, success=False)
                        except Exception:
                            pass
                        if isinstance(exc, asyncio.CancelledError):
                            raise
                        return reply(503, 'unavailable')
                    return reply(200, 'processed')
                finally:
                    flow_slots.release()
            if text == '/price':
                if conversation is None or conversation.inbox is not inbox:
                    return reply(503, 'unavailable')
                with inbox._lock:
                    try:
                        carrier = inbox._carrier(user, chat)
                        flow = inbox._conversation_states.get(carrier)
                        if flow is None or flow['step'] != 'confirmed':
                            raise ValueError('Confirm the current revision first')
                        token = flow['token']
                        inbox._access(user, chat, token)
                        snapshot = conversation.opening.get(user, chat)
                        if snapshot.revision != flow['revision'] or not snapshot.confirmed:
                            raise ValueError('Confirm the current revision first')
                        if inbox.duplicate_update(user, chat, data['update_id'], 'opening'):
                            return reply(200, 'duplicate')
                        if inbox.stale_message(user, chat, message_id):
                            return reply(200, 'stale')
                        accepted = inbox.submit(user, chat, data['update_id'], 'opening',
                            token=token, revision=snapshot.revision, message_id=message_id)
                    except (ValueError, KeyError):
                        return reply(400, 'invalid_update')
                return reply(200, 'queued' if accepted else 'duplicate')
            if conversation is not None and (isinstance(text, str) and (
                    text.split(' ', 1)[0] in ('/start', '/reply', '/confirm', '/edit', '/refresh')
                    or not text.startswith('/'))):
                if send is None or conversation.inbox is not inbox:
                    return reply(503, 'unavailable')
                if not flow_slots.acquire(blocking=False):
                    return reply(503, 'unavailable')
                try:
                    with inbox._lock:
                        if inbox.duplicate_update(user, chat, data['update_id'], 'flow'):
                            return reply(200, 'duplicate')
                        if inbox.stale_message(user, chat, message_id):
                            return reply(200, 'stale')
                        claim = inbox.begin_flow(user, chat, data['update_id'], message_id=message_id)
                        if claim is None:
                            return reply(200, 'duplicate')
                        try:
                            answer = conversation.handle(user, chat, text)
                        except (ValueError, KeyError, TypeError, PermissionError):
                            try:
                                answer = 'Please check your answer. No new confirmation was granted.\n' + conversation.handle(user, chat, '/refresh')
                            except (ValueError, KeyError, TypeError, PermissionError):
                                answer = 'Your intake needs a fresh start. Use /start while safely parked.'
                        flow = inbox._conversation_states.get(inbox._carrier(user, chat))
                        expected = flow['nonce'] if flow else None
                    def guard():
                        with inbox._lock:
                            carrier = inbox._carrier(user, chat)
                            current = inbox._conversation_states.get(carrier)
                            if (current['nonce'] if current else None) != expected:
                                raise ValueError('Conversation changed')
                            if current is not None and current['step'] != 'memory':
                                inbox._access(user, chat, current['token'])
                            inbox.start_delivery(user, chat, data['update_id'], claim)
                    try:
                        if len(answer) > 4000:raise ValueError('Reply too large')
                        await asyncio.to_thread(delivery.send, chat, answer, guard, send)
                        inbox.finish(user, chat, data['update_id'], claim, success=True)
                    except (Exception, asyncio.CancelledError) as exc:
                        try:inbox.finish(user, chat, data['update_id'], claim, success=False)
                        except Exception:pass
                        if isinstance(exc, asyncio.CancelledError):
                            raise
                        return reply(503, 'unavailable')
                    return reply(200, 'processed')
                finally:
                    flow_slots.release()
            return reply(400, 'unsupported_command')
        except TimeoutError:
            return reply(408, 'timeout')
        except PermissionError:
            return reply(403, 'rejected')
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
            return reply(400, 'invalid_update')
        except Exception:
            return reply(503, 'unavailable')

    if miniapp_bot_token is not None:
        from .opening_miniapp import mount_miniapp
        mount_miniapp(app, inbox, bot_token=miniapp_bot_token, allowed_host=allowed_host)

    return app


def _finish_opening_text(snapshot_revision, result):
    def dollars(value):
        return 'unknown' if value is None else '$' + value
    lines = [f'Preliminary opening price — revision {snapshot_revision}',
        f"Total miles: {result['total_miles'] or 'unknown'}",
        f"Estimated operating cost: {dollars(result['estimated_operating_cost'])}",
        f"Target revenue: {dollars(result['target_revenue'])}"]
    if result['opening_bid'] is not None:
        lines.append(f"Opening bid: ${result['opening_bid']}")
        lines.append(f"Estimated operating surplus: ${result['estimated_operating_surplus']}")
    else:
        lines.append('Missing: ' + (', '.join(result['missing']) or 'review required'))
        if result['pricing_issue']:
            lines.append(result['pricing_issue'])
    lines.append(result['notice'])
    lines.append(QUESTIONS)
    return '\n'.join(lines)


def _finish_evaluation_text(snapshot_revision, result):
    def dollars(value):
        return 'unknown' if value is None else '$' + value
    titles = {'ACCEPT': 'The supplied checks pass.',
              'NEGOTIATE': 'The current terms need work.',
              'DECLINE': 'This schedule does not work.',
              'NEED_MORE_INFORMATION': 'Add facts before deciding.'}
    lines = [f'Offer evaluation — revision {snapshot_revision}: {result["decision"]}',
        titles[result['decision']],
        f"Compensation: {dollars(result['compensation'])} [{result['compensation_source']}]",
        f"Total miles: {result['total_miles'] or 'unknown'}",
        f"Estimated operating cost: {dollars(result['estimated_operating_cost'])}",
        f"Target revenue: {dollars(result['target_revenue'])}"]
    if result['revenue_gap_to_target'] is not None:
        lines.append(f"Revenue gap to target: ${result['revenue_gap_to_target']}")
    if result['estimated_operating_surplus'] is not None:
        lines.append(f"Estimated operating surplus: ${result['estimated_operating_surplus']}")
    if result['missing_information']:
        lines.append('Missing: ' + ', '.join(result['missing_information']))
    lines.append('Limits: stops, hours-of-service, routing and market conditions are not modeled; '
                 'equipment match and schedule are carrier-supplied, not verified.')
    lines.append('A decision here is never a booking; confirm logistics before acting.')
    lines.append(result['notice'])
    return '\n'.join(lines)


def negotiation_guidance(kind, result):
    """Deterministic guidance. Broker wording stays separate from internal costs."""
    lines = ['Negotiation guidance (internal):']
    if kind == 'opening_bid':
        if result['opening_bid'] is not None:
            lines.append(f"Basis: {result['total_miles']} mi at confirmed operating cost "
                         f"${result['estimated_operating_cost']}; target revenue "
                         f"${result['target_revenue']}; opening ${result['opening_bid']}.")
        else:
            lines.append('Basis unavailable: '
                         + (', '.join(result['missing']) or 'review required') + '.')
        lines.append('Unknown schedule allows preliminary pricing but blocks full acceptance.')
        lines.append('Repricing triggers: detention, lumper, reefer or temperature control, '
                     'tarping, team service, extra stops, revised miles.')
        if result['opening_bid'] is not None:
            lines.append('Broker wording (DRAFT — NOT SENT; no internal costs):')
            lines.append(f'"Thanks — I can open at ${result["opening_bid"]} on these details. '
                         'Please confirm commodity, weight, loading appointment and any '
                         'handling or accessorial needs; added service may require repricing."')
        return '\n'.join(lines)
    decision = result['decision']
    if decision == 'ACCEPT':
        lines.append('The compensation meets the confirmed target, exceeds operating cost, '
                     'and clears the minimum with feasible availability.')
        lines.append('Before acting, still confirm loading appointment, commodity, weight, '
                     'handling needs and payment terms. ACCEPT is not a booking.')
    elif decision == 'NEGOTIATE':
        lines.append(f"Gap to target revenue: ${result['revenue_gap_to_target']}.")
        # A named ask must clear target, minimum and operating cost together.
        # NEGOTIATE implies complete inputs, so all three figures are known.
        ask = max(Decimal(result['target_revenue']), Decimal(result['minimum_job_charge']))
        if ask > Decimal(result['estimated_operating_cost']):
            ask_text = f'{ask:.2f}'
            lines.append(f'Ask at or above ${ask_text}; do not concede below operating '
                         'cost or the confirmed minimum.')
            lines.append('Broker wording (DRAFT — NOT SENT; no internal costs, no confirmed floor):')
            lines.append(f'"Thanks — at the current offer this one does not work for me. '
                         f'I can do it at ${ask_text}. Can you confirm commodity, '
                         'weight, loading appointment and any accessorial needs?"')
        else:
            lines.append('No numeric ask follows from the confirmed inputs: clearing the '
                         'target and minimum together does not exceed operating cost. '
                         'Request carrier review; revised miles, service needs or pricing '
                         'may change the picture before any broker reply.')
            lines.append('Broker wording (DRAFT — NOT SENT; no internal costs, no confirmed floor):')
            lines.append('"Thanks — I need to review the details before naming a price. '
                         'Can you confirm commodity, weight, loading appointment and any '
                         'accessorial needs?"')
    elif decision == 'DECLINE':
        lines.append('Availability is confirmed blocked. No price changes that decision; '
                     'only a schedule change with a fresh revision can.')
    else:
        lines.append('Missing: ' + (', '.join(result['missing_information']) or 'review required')
                     + '. Ask the broker for the missing facts; do not guess them.')
    return '\n'.join(lines)


def run_screenshot(inbox, delegator, send, *, user: int, chat: int, update_id: int):
    """One extraction attempt; injected sender MUST be bounded and nonretrying."""
    with inbox._lock:
        carrier = inbox._carrier(user, chat)
        access = inbox._active.get(carrier)
        if access is None:
            raise PermissionError('Current consent required')
        token = access.token
        claim, media = inbox.claim_screenshot(user, chat, update_id, token)
        opening = inbox._opening
        try:
            expected = opening.get(user, chat).revision
        except KeyError:
            expected = 0
    stage = 'attempt'
    try:
        outcome = delegator.screenshot(user, chat, token, media['file_id'], media['mime'],
                                       expected_revision=expected)
        snapshot = outcome['snapshot']
        with inbox._lock:
            current = opening.get(user, chat)
            if current.revision != expected + 1 or current != snapshot:
                raise ValueError('Result changed')
            try:
                profile = opening.get_profile(user, chat)
            except KeyError:
                profile = None
            previous = inbox._conversation_states.get(carrier)
            trip_done = bool(previous and previous.get('trip_done'))
            if trip_done:
                step = 'review'
                text = ('UNCONFIRMED screenshot draft — verify every value.\n'
                        + render_review(snapshot, profile) + '\n' + QUESTIONS)
            else:
                step = 'trip'
                text = ('UNCONFIRMED screenshot draft — verify every value.\n'
                        + render_review(snapshot, profile) + '\n' + TRIP_PROMPT)
            if len(text) > 4000:
                raise ValueError('Reply too large')
            nonce = token_urlsafe(12)
            inbox._conversation_states[carrier] = dict(
                step=step, nonce=nonce, revision=snapshot.revision, token=token,
                values={}, trip_done=trip_done, last_prompt=text)
            text += step_trailer(step, nonce)
        def guard():
            with inbox._lock:
                inbox._access(user, chat, token)
                if opening.get(user, chat).revision != snapshot.revision:
                    raise ValueError('Result changed')
                inbox.start_delivery(user, chat, update_id, claim)
        with inbox._lock:
            if inbox._delivery_pool is None:inbox._delivery_pool=DeliveryPool(None)
            pool=inbox._delivery_pool
        stage = 'delivery'
        pool.send(chat, text, guard, send)
        inbox.finish(user, chat, update_id, claim, success=True)
    except Exception as exc:
        try:
            inbox.finish(user, chat, update_id, claim, success=False,
                         category=failure_category_for(exc, stage=stage))
        except Exception:
            pass
        try:
            # Best-effort recovery hint for /refresh; durable state is recorded above.
            # Fixed text only: no provider detail, pixels or secrets.
            flow = inbox._conversation_states.get(carrier)
            if flow is not None:
                flow['screenshot_notice'] = True
        except Exception:
            pass
        raise RuntimeError('Worker failed; outcome uncertain; no automatic retry') from None


def run_opening(inbox, delegator, send, *, user: int, chat: int, update_id: int):
    """One pricing attempt; injected sender MUST be bounded and nonretrying."""
    with inbox._lock:
        carrier = inbox._carrier(user, chat)
        access = inbox._active.get(carrier)
        if access is None:
            raise PermissionError('Current consent required')
        token = access.token
        claim, revision = inbox.claim_opening(user, chat, update_id, token)
        opening = inbox._opening
    stage = 'attempt'
    try:
        outcome = delegator.opening(user, chat, token, revision)
        with inbox._lock:
            kind, canonical = opening.decide(user, chat, revision)
            if (outcome['kind'], outcome['result']) != (kind, canonical):
                raise ValueError('Result changed')
            if kind == 'offer_evaluation':
                text = _finish_evaluation_text(revision, canonical)
            else:
                text = _finish_opening_text(revision, canonical)
            text += '\n' + negotiation_guidance(kind, canonical)
            if len(text) > 4000:
                raise ValueError('Reply too large')
        def guard():
            with inbox._lock:
                inbox._access(user, chat, token)
                if opening.decide(user, chat, revision) != (kind, canonical):
                    raise ValueError('Result changed')
                inbox.start_delivery(user, chat, update_id, claim)
        with inbox._lock:
            if inbox._delivery_pool is None:inbox._delivery_pool=DeliveryPool(None)
            pool=inbox._delivery_pool
        stage = 'delivery'
        pool.send(chat, text, guard, send)
        inbox.finish(user, chat, update_id, claim, success=True)
    except Exception as exc:
        try:
            inbox.finish(user, chat, update_id, claim, success=False,
                         category=failure_category_for(exc, stage=stage))
        except Exception:
            pass
        raise RuntimeError('Worker failed; outcome uncertain; no automatic retry') from None
