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
from .opening_workflow import OpeningPricing, render_review
from .pilot_delivery import DeliveryPool
from .pilot_memory import _token_matches
from .remote_app import _is_valid_hostname

QUESTIONS = ('Useful next details: cargo commodity and weight confirmation, handling or '
    'equipment needs, loading/unloading appointments, and schedule feasibility. Unknown '
    'schedule allows preliminary pricing but blocks full acceptance.')


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
                # Plain corrections carry no nonce; commands without one are stale.
                if parts[0].startswith('/'):
                    raise ValueError('Stale conversation step')
                return self._correct(user, chat, carrier, flow, text)
            if flow['step'] != 'memory':
                try:
                    self.inbox._access(user, chat, flow['token'])
                except PermissionError:
                    self._flows.pop(carrier, None)
                    raise
            command = parts[0]
            value = parts[2] if len(parts) == 3 else ''
            if command == '/confirm' and flow['step'] == 'review' and not value:
                self.opening.confirm(user, chat, flow['revision'])
                flow['nonce'] = token_urlsafe(12)
                flow['step'] = 'confirmed'
                return self._prompt(carrier, f'Confirmed opening revision {flow["revision"]}. '
                    'Use /price for a preliminary opening price, or correct a field. '
                    'Corrections require fresh confirmation. /forget withdraws consent.')
            if command == '/edit' and flow['step'] in ('review', 'confirmed') and value:
                field, _, field_value = value.partition(' ')
                if not field_value:
                    raise ValueError('Send edits as /edit NONCE field value')
                return self._correct(user, chat, carrier, flow, field + ' ' + field_value)
            if command != '/reply':
                raise ValueError('Unexpected conversation command')
            if flow['step'] == 'memory':
                choices = {'session': 'session_only', 'remember': 'remember_profile'}
                if value not in choices:
                    raise ValueError('Choose session or remember')
                access = self.inbox.consent(user, chat, flow['notice'].token, choices[value])
                flow['token'] = access.token
                self._flows[carrier] = flow
                return self._advance(carrier, 'photo',
                    'Consent recorded. Send one PNG or JPEG screenshot of the opportunity. '
                    'Processing before consent is never performed; /forget withdraws consent.')
            raise ValueError('Unexpected conversation step')

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
        if flow['step'] == 'photo':
            try:
                snapshot = self.opening.get(user, chat)
            except KeyError:
                return self._prompt(carrier, flow['last_prompt'])
            flow['revision'] = snapshot.revision
            flow['step'] = 'review'
            return self._prompt(carrier, render_review(snapshot) + '\n' + QUESTIONS)
        snapshot = self.opening.get(user, chat)
        if snapshot.revision != flow.get('revision'):
            flow['revision'] = snapshot.revision
            flow['step'] = 'review'
        if flow['step'] == 'confirmed' and not snapshot.confirmed:
            flow['step'] = 'review'
        if flow['step'] == 'review':
            return self._prompt(carrier, render_review(snapshot) + '\n' + QUESTIONS)
        return self._prompt(carrier, f'Confirmed opening revision {snapshot.revision}. '
            'Use /price for a preliminary opening price, or correct a field.')

    def _correct(self, user, chat, carrier, flow, text):
        if flow['step'] not in ('review', 'confirmed'):
            raise ValueError('Send one screenshot first; corrections apply to its draft')
        try:
            self.inbox._access(user, chat, flow['token'])
        except PermissionError:
            self._flows.pop(carrier, None)
            raise
        field, _, value = text.partition(' ')
        if not value:
            raise ValueError('Send corrections as "field value", e.g. "target 2.10"')
        snapshot = self.opening.get(user, chat)
        facts = snapshot.draft.facts.model_dump()
        pricing = snapshot.pricing.model_dump()
        note = snapshot.counter_note
        field = field.lower()
        if field == 'counter':
            note = value.strip()[:200] or None
            if value.strip().lower() == 'none':
                note = None
        elif field in ('payout', 'loaded', 'loaded_miles', 'deadhead', 'deadhead_miles',
                       'weight', 'weight_lbs'):
            name = {'loaded': 'loaded_miles', 'deadhead': 'deadhead_miles',
                    'weight': 'weight_lbs'}.get(field, field)
            parsed = _unknown(value)
            if parsed is None:
                facts[name] = None
            else:
                bounds = {'payout': (0, 1000000, True), 'loaded_miles': (0, 100000, False),
                          'deadhead_miles': (0, 100000, True), 'weight_lbs': (0, 200000, True)}[name]
                facts[name] = _decimal(parsed, name=name, low=Decimal(bounds[0]),
                                       high=Decimal(bounds[1]), allow_zero=bounds[2])
                if name == 'weight_lbs' and facts[name] == 0:
                    facts[name] = None
        elif field in ('target', 'cpm', 'minimum', 'reposition', 'reposition_miles'):
            name = {'target': 'target_all_mile_rpm', 'cpm': 'operating_cpm',
                    'minimum': 'minimum_job_charge',
                    'reposition': 'reposition_miles'}.get(field, field)
            parsed = _unknown(value)
            if name == 'minimum_job_charge':
                if parsed is None:
                    raise ValueError('Minimum charge must be supplied, including explicit zero')
                if parsed.lower() == 'none':
                    pricing[name] = Decimal(0)
                else:
                    pricing[name] = _decimal(parsed, name=name, low=Decimal(0),
                                             high=Decimal(1000000), allow_zero=True)
            elif name == 'operating_cpm':
                if parsed is None:
                    pricing[name] = None
                    pricing['expense_claim'] = None
                elif parsed.lower() == 'itemized':
                    raise ValueError('Itemized costs need explicit normalization first; '
                                     'pricing stays unavailable')
                else:
                    pricing[name] = _decimal(parsed, name=name, low=Decimal(0),
                                             high=Decimal(1000), allow_zero=True)
                    pricing['expense_claim'] = 'all_operating_expenses'
            elif parsed is None:
                pricing[name] = None
                if name == 'operating_cpm':
                    pricing['expense_claim'] = None
            else:
                bounds = {'target_all_mile_rpm': (0, 1000, False),
                          'reposition_miles': (0, 100000, True)}[name]
                pricing[name] = _decimal(parsed, name=name, low=Decimal(bounds[0]),
                                         high=Decimal(bounds[1]), allow_zero=bounds[2])
        else:
            raise ValueError('Unknown field; correct payout, loaded, deadhead, weight, target, '
                             'cpm, minimum, reposition or counter')
        draft = ScreenshotDraft(status='UNCONFIRMED', facts=IntakeFacts.model_validate(facts),
            evidence={**snapshot.draft.evidence,
                      **({name: 'carrier correction'} if field in (
                          'payout', 'loaded', 'loaded_miles', 'deadhead',
                          'deadhead_miles', 'weight', 'weight_lbs') else {})},
            issues=snapshot.draft.issues)
        updated = self.opening.put(user, chat, draft,
            OpeningPricing.model_validate(pricing), expected_revision=snapshot.revision,
            counter_note=note)
        flow['revision'] = updated.revision
        flow['step'] = 'review'
        flow['nonce'] = token_urlsafe(12)
        return self._prompt(carrier, render_review(updated) + '\n' + QUESTIONS)

    def _advance(self, carrier, step, prompt):
        self._flows[carrier].update(step=step, nonce=token_urlsafe(12))
        return self._prompt(carrier, prompt)

    def _prompt(self, carrier, prompt):
        self._flows[carrier]['last_prompt'] = prompt
        return prompt + '\nStep: ' + self._flows[carrier]['nonce'] + '\nReply format: /reply STEP answer'


def create_opening_app(inbox, *, webhook_secret: str, allowed_host: str, conversation=None, send=None):
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
                        if inbox.duplicate_update(user, chat, data['update_id'], 'screenshot'):
                            return reply(200, 'duplicate')
                        if inbox.stale_message(user, chat, message_id):
                            return reply(200, 'stale')
                        accepted = inbox.submit(user, chat, data['update_id'], 'screenshot',
                            token=token, message_id=message_id, media=dict(
                                file_id=media.file_id, file_unique_id=media.file_unique_id,
                                mime=media.mime, reported_size=message.get('photo', [{}])[-1].get('file_size')
                                if message.get('photo') else message.get('document', {}).get('file_size')))
                    return reply(200, 'queued' if accepted else 'duplicate')
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
    try:
        outcome = delegator.screenshot(user, chat, token, media['file_id'], media['mime'],
                                       expected_revision=expected)
        snapshot = outcome['snapshot']
        with inbox._lock:
            current = opening.get(user, chat)
            if current.revision != expected + 1 or current != snapshot:
                raise ValueError('Result changed')
            text = ('UNCONFIRMED screenshot draft — verify every value.\n'
                    + render_review(snapshot) + '\n' + QUESTIONS)
            if len(text) > 4000:
                raise ValueError('Reply too large')
            flow = inbox._conversation_states.get(carrier)
            nonce = token_urlsafe(12)
            inbox._conversation_states[carrier] = dict(
                step='review', nonce=nonce, revision=snapshot.revision, token=token,
                values={}, last_prompt=text)
            text += '\nStep: ' + nonce + '\nReply format: /reply STEP answer'
        def guard():
            with inbox._lock:
                inbox._access(user, chat, token)
                if opening.get(user, chat).revision != snapshot.revision:
                    raise ValueError('Result changed')
                inbox.start_delivery(user, chat, update_id, claim)
        with inbox._lock:
            if inbox._delivery_pool is None:inbox._delivery_pool=DeliveryPool(None)
            pool=inbox._delivery_pool
        pool.send(chat, text, guard, send)
        inbox.finish(user, chat, update_id, claim, success=True)
    except Exception:
        try:
            inbox.finish(user, chat, update_id, claim, success=False)
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
    try:
        outcome = delegator.opening(user, chat, token, revision)
        with inbox._lock:
            canonical = opening.price(user, chat, revision)
            if outcome['result'] != canonical:
                raise ValueError('Result changed')
            text = _finish_opening_text(revision, canonical)
            if len(text) > 4000:
                raise ValueError('Reply too large')
        def guard():
            with inbox._lock:
                inbox._access(user, chat, token)
                if opening.price(user, chat, revision) != canonical:
                    raise ValueError('Result changed')
                inbox.start_delivery(user, chat, update_id, claim)
        with inbox._lock:
            if inbox._delivery_pool is None:inbox._delivery_pool=DeliveryPool(None)
            pool=inbox._delivery_pool
        pool.send(chat, text, guard, send)
        inbox.finish(user, chat, update_id, claim, success=True)
    except Exception:
        try:
            inbox.finish(user, chat, update_id, claim, success=False)
        except Exception:
            pass
        raise RuntimeError('Worker failed; outcome uncertain; no automatic retry') from None
