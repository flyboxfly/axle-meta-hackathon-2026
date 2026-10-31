"""Injected, offline-tested Telegram boundary. No launcher, secrets or live sends."""
import asyncio
import json
import re

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
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

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
                    and text.split(' ',1)[0] in ('/start','/reply','/confirm','/edit','/save')):
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
                        if len(answer) > 4000 or send(chat,answer) is not True:
                            raise RuntimeError('Delivery not confirmed')
                        inbox.finish(user,chat,data['update_id'],claim,success=True)
                    except (ValueError,KeyError,TypeError,PermissionError):
                        inbox.finish(user,chat,data['update_id'],claim,success=False)
                        # No private input/validation details in response; step remains reviewable.
                        return reply(400,'invalid_conversation_step')
                    except Exception:
                        inbox.finish(user,chat,data['update_id'],claim,success=False)
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
            if send(chat, text) is not True:
                raise RuntimeError('Delivery not confirmed')
            inbox.finish(user, chat, update_id, claim, success=True)
    except Exception:
        try:
            inbox.finish(user, chat, update_id, claim, success=False)
        except Exception:
            pass  # Remains processing; restart recovery marks it uncertain.
        raise RuntimeError('Worker failed; outcome uncertain; no automatic retry') from None
