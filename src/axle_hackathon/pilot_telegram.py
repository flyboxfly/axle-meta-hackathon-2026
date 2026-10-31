"""Injected, offline-tested Telegram boundary. No launcher, secrets or live sends."""
import asyncio
import json
import re
from contextlib import asynccontextmanager
from .pilot_delivery import DeliveryPool

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .pilot_memory import _token_matches
from .remote_app import _is_valid_hostname


def create_app(inbox, *, webhook_secret: str, allowed_host: str, conversation=None, send=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', webhook_secret):
        raise ValueError('Explicit webhook secret required')
    if not _is_valid_hostname(allowed_host):
        raise ValueError('Exact allowed host required')
    if len(set(inbox._bindings.values())) != len(inbox._bindings):
        raise ValueError('One approved private-chat binding per carrier required')
    with inbox._lock:
        if inbox._delivery_pool is None:inbox._delivery_pool=DeliveryPool(None)
        delivery=inbox._delivery_pool
    @asynccontextmanager
    async def lifespan(app):
        try: yield
        finally:
            delivery.close()
            with inbox._lock:
                if inbox._delivery_pool is delivery:inbox._delivery_pool=None
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
            message_id=message.get('message_id')
            if (conversation is not None and isinstance(text,str)
                    and text.split(' ',1)[0] in ('/start','/reply','/confirm','/edit','/save','/refresh')):
                if send is None or conversation.inbox is not inbox:
                    return reply(503,'unavailable')
                with inbox._lock:
                    if inbox.duplicate_update(user,chat,data['update_id'],'flow'):
                        return reply(200,'duplicate')
                    if inbox.stale_message(user,chat,message_id):
                        return reply(200,'stale')
                    claim = inbox.begin_flow(user,chat,data['update_id'],message_id=message_id)
                    if claim is None:
                        return reply(200,'duplicate')
                    try:
                        answer = conversation.handle(user,chat,text)
                    except (ValueError,KeyError,TypeError,PermissionError):
                        try:
                            answer = 'Please check your answer. No new confirmation was granted.\n' + conversation.handle(user,chat,'/refresh')
                        except (ValueError,KeyError,TypeError,PermissionError):
                            answer = 'Your intake needs a fresh start. Use /start while safely parked.'
                    flow=inbox._conversation_states.get(inbox._carrier(user,chat))
                    expected=flow['nonce'] if flow else None
                def guard():
                    with inbox._lock:
                        carrier=inbox._carrier(user,chat)
                        current=inbox._conversation_states.get(carrier)
                        if (current['nonce'] if current else None)!=expected:
                            raise ValueError('Conversation changed')
                        if current is not None:
                            if current['step']=='memory':
                                if current['notice'].expires_at<=inbox._now():raise PermissionError()
                            else:inbox._access(user,chat,current['token'])
                        inbox.start_delivery(user,chat,data['update_id'],claim)
                try:
                    if len(answer)>4000:raise ValueError('Reply too large')
                    await asyncio.to_thread(delivery.send,chat,answer,guard,send)
                    inbox.finish(user,chat,data['update_id'],claim,success=True)
                except Exception:
                    try:inbox.finish(user,chat,data['update_id'],claim,success=False)
                    except Exception:pass
                    return reply(503,'unavailable')
                return reply(200,'processed')
            # Accept only explicit commands; no media fetch or unreviewed text intake.
            action = {'/evaluate': 'evaluate', '/forget': 'forget'}.get(message.get('text'))
            if action is None:
                return reply(400, 'unsupported_command')
            with inbox._lock:
                carrier = inbox._carrier(user, chat)
                command_id = message.get('message_id') if action == 'forget' else None
                if action == 'forget' and (type(command_id) is not int or command_id <= 0):
                    return reply(400,'invalid_update')
                if inbox.duplicate_update(user, chat, data['update_id'], action,command_id=command_id):
                    return reply(200, 'duplicate')
                if inbox.stale_message(user,chat,message_id):
                    return reply(200,'stale')
                if action == 'evaluate':
                    access = inbox._active.get(carrier)
                    if access is None:
                        raise PermissionError()
                    snapshot = inbox.get(user, chat, access.token)
                    accepted = inbox.submit(user, chat, data['update_id'], action,
                                            token=access.token, revision=snapshot.revision,message_id=message_id)
                else:
                    accepted = inbox.submit(user, chat, data['update_id'], action,command_id=command_id,
                                            message_id=message_id)
                    if conversation is not None:
                        conversation.clear(user,chat)
            return reply(200, 'queued' if accepted else 'duplicate')
        except TimeoutError:
            return reply(408, 'timeout')
        except PermissionError:
            return reply(403, 'rejected')
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
            return reply(400, 'invalid_update')
        except Exception:
            # No SDK error, token URL, database details or private input escapes.
            return reply(503, 'unavailable')

    return app


def run_evaluation(inbox, delegator, send, *, user: int, chat: int, update_id: int):
    """One explicit worker attempt; injected sender MUST be bounded and nonretrying.

    No worker scheduler or live Telegram client is installed here. The sender accepts
    (numeric_chat_id, plain_text); it must not honor model-supplied destinations.
    """
    with inbox._lock:
        carrier = inbox._carrier(user, chat)
        access = inbox._active.get(carrier)
        if access is None:
            raise PermissionError('Current consent required')
        token = access.token
        claim, revision = inbox.claim_evaluation(user, chat, update_id, token)
    try:
        result = delegator.evaluate(user, chat, token, revision)
        with inbox._lock:
            # Recompute canonical figures and check state immediately at delivery.
            canonical = inbox.evaluate(user, chat, token, revision)
            if result['evaluation'] != canonical:
                raise ValueError('Result changed')
            def dollars(value):
                return 'unknown' if value is None else '$' + value
            text = (f"{canonical['decision']} — planning estimate\n"
                    f"Total miles: {canonical['total_miles']}\n"
                    f"Planning cost including reserves: {dollars(canonical['planning_cost_including_reserves'])}\n"
                    f"Planning surplus: {dollars(canonical['planning_surplus'])}\n"
                    'No booking or regulatory clearance.')
        def guard():
            with inbox._lock:
                current=inbox.evaluate(user,chat,token,revision)
                if current!=canonical:raise ValueError('Result changed')
                inbox.start_delivery(user,chat,update_id,claim)
        with inbox._lock:
            if inbox._delivery_pool is None:inbox._delivery_pool=DeliveryPool(None)
            pool=inbox._delivery_pool
        pool.send(chat,text,guard,send)
        inbox.finish(user,chat,update_id,claim,success=True)
    except Exception:
        try:
            inbox.finish(user, chat, update_id, claim, success=False)
        except Exception:
            pass  # Remains processing; restart recovery marks it uncertain.
        raise RuntimeError('Worker failed; outcome uncertain; no automatic retry') from None
