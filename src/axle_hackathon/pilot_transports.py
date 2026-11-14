"""Injected HTTP adapters. No client creation, credential loading or live launcher."""
import json
import re
from time import monotonic
from types import SimpleNamespace
from .opening_intake import (
    MAX_IMAGE_REQUEST_BYTES, MAX_RESPONSE_CHARS, TELEGRAM_HOSTS, validate_file_path,
)
from .pilot_execution import ExtractionResponseError, _seconds
from .vision import MAX_IMAGE_BYTES


def _json_post(client,url,payload,headers,*,seconds,limit,image_extraction=False):
    deadline=monotonic()+seconds
    try:
        with client.stream('POST',url,json=payload,headers={**headers,'Accept-Encoding':'identity'},
                           follow_redirects=False) as response:
            if image_extraction and response.status_code in (500, 502, 503):
                raise ExtractionResponseError('provider_unavailable', 'Image provider unavailable')
            if response.status_code != 200 or response.headers.get('content-encoding','identity') != 'identity':
                raise ValueError()
            body=bytearray()
            for chunk in response.iter_raw():
                if monotonic()>=deadline or len(body)+len(chunk)>limit:raise ValueError()
                body.extend(chunk)
            if monotonic()>=deadline:raise ValueError()
            def unique(pairs):
                result={}
                for key,value in pairs:
                    if key in result:raise ValueError()
                    result[key]=value
                return result
            value=json.loads(body,object_pairs_hook=unique)
            if not isinstance(value,dict):raise ValueError()
            return value
    except ExtractionResponseError:
        raise
    except Exception:
        raise RuntimeError('Remote outcome uncertain; no automatic retry') from None


def _check_delivery(result,chat):
    message=result.get('result')
    if (result.get('ok') is not True or not isinstance(message,dict)
            or type(message.get('message_id')) is not int or message['message_id']<=0
            or not isinstance(message.get('chat'),dict)
            or type(message['chat'].get('id')) is not int
            or message['chat']['id']!=chat
            or message['chat'].get('type')!='private'):
        raise RuntimeError('Delivery uncertain; no automatic retry')


class TelegramSender:
    def __init__(self,client,token,*,allowed_chats,seconds):
        if not isinstance(token,str) or not re.fullmatch(r'[0-9]{1,20}:[A-Za-z0-9_-]{20,200}',token):
            raise ValueError('Explicit bot token required')
        if not allowed_chats or any(type(c) is not int or c<=0 for c in allowed_chats):
            raise ValueError('Approved private chats required')
        self._client,self._url=client,'https://api.telegram.org/bot'+token+'/sendMessage'
        self._chats=frozenset(allowed_chats);self._seconds=_seconds(seconds)

    def __call__(self,chat,text):
        if type(chat) is not int or chat not in self._chats:raise PermissionError('Unapproved chat')
        if not isinstance(text,str) or not 1<=len(text)<=4000:raise ValueError('Bounded text required')
        result=_json_post(self._client,self._url,{'chat_id':chat,'text':text},{},
                          seconds=self._seconds,limit=32768)
        _check_delivery(result,chat)
        return True


class TelegramWebAppButton:
    """One inline web_app button per message; URL fixed to the allowed host.

    The button opens https://<allowed_host>/miniapp/ only. No other markup,
    URLs or chat types are expressible here.
    """
    def __init__(self,client,token,*,allowed_chats,allowed_host,seconds):
        if not isinstance(token,str) or not re.fullmatch(r'[0-9]{1,20}:[A-Za-z0-9_-]{20,200}',token):
            raise ValueError('Explicit bot token required')
        if not allowed_chats or any(type(c) is not int or c<=0 for c in allowed_chats):
            raise ValueError('Approved private chats required')
        from .remote_app import _is_valid_hostname
        if not _is_valid_hostname(allowed_host):
            raise ValueError('Exact allowed host required')
        self._client,self._url=client,'https://api.telegram.org/bot'+token+'/sendMessage'
        self._chats=frozenset(allowed_chats);self._seconds=_seconds(seconds)
        self._web_app_url='https://'+allowed_host+'/miniapp/'

    @property
    def web_app_url(self):
        return self._web_app_url

    def __call__(self,chat,text,*,label):
        if type(chat) is not int or chat not in self._chats:raise PermissionError('Unapproved chat')
        if not isinstance(text,str) or not 1<=len(text)<=4000:raise ValueError('Bounded text required')
        if not isinstance(label,str) or not 1<=len(label)<=64:raise ValueError('Bounded label required')
        result=_json_post(self._client,self._url,{'chat_id':chat,'text':text,'reply_markup':
            {'inline_keyboard':[[{'text':label,'web_app':{'url':self._web_app_url}}]]}},{},
            seconds=self._seconds,limit=32768)
        _check_delivery(result,chat)
        return True


class MetaResponsesClient:
    """Minimal Responses interface for PilotDelegator; direct HTTP, no SDK retry layer."""
    def __init__(self,client,key,*,seconds):
        if not isinstance(key,str) or not key or not key.isascii() or any(c.isspace() for c in key):
            raise ValueError('Explicit provider key required')
        self._client,self._key,self._seconds=client,key,_seconds(seconds)
        self.responses=self

    def create(self,**payload):
        if len(json.dumps(payload).encode())>32768:raise ValueError('Provider request too large')
        data=_json_post(self._client,'https://api.meta.ai/v1/responses',payload,
            {'Authorization':'Bearer '+self._key},seconds=self._seconds,limit=65536)
        try:
            return SimpleNamespace(status=data['status'],
                output=[SimpleNamespace(**item) for item in data['output']],
                id=data.get('id'),usage=data.get('usage'))
        except Exception:raise RuntimeError('Invalid provider response') from None


def _response_text(data):
    """Strict visible text from REST output items; top-level helper is SDK-only.

    Message parts are authoritative when present: refusal fails, and the
    top-level fallback applies only when no message item exists, so it can
    never override refusal, status, or malformed-shape handling. Response
    status is always checked separately by the caller.
    """
    parts, total, saw_message = [], 0, False
    output = data.get('output', [])
    if not isinstance(output, list) or len(output) > 32:
        raise ValueError()
    for item in output:
        if not isinstance(item, dict):
            raise ValueError()
        if item.get('type') != 'message':
            continue
        if item.get('role') != 'assistant':
            raise ValueError()
        saw_message = True
        content = item.get('content')
        if not isinstance(content, list) or len(content) > 32:
            raise ValueError()
        for part in content:
            if not isinstance(part, dict):
                raise ValueError()
            if part.get('type') == 'refusal':
                raise ExtractionResponseError('extraction_filtered',
                                              'Screenshot extraction refused')
            if part.get('type') != 'output_text':
                continue
            text = part.get('text')
            if not isinstance(text, str):
                raise ValueError()
            total += len(text)
            if total > MAX_RESPONSE_CHARS:
                raise ValueError()
            parts.append(text)
    if parts or saw_message:
        return ''.join(parts)
    top = data.get('output_text')
    if top is None:
        return ''
    if not isinstance(top, str) or len(top) > MAX_RESPONSE_CHARS:
        raise ValueError()
    return top


class MetaImageClient:
    """Image-capable Responses interface; separate reviewed request bound."""
    def __init__(self,client,key,*,seconds):
        if not isinstance(key,str) or not key or not key.isascii() or any(c.isspace() for c in key):
            raise ValueError('Explicit provider key required')
        self._client,self._key,self._seconds=client,key,_seconds(seconds)
        self.responses=self

    def create(self,**payload):
        if len(json.dumps(payload).encode())>MAX_IMAGE_REQUEST_BYTES:
            raise ValueError('Provider request too large')
        data=_json_post(self._client,'https://api.meta.ai/v1/responses',payload,
            {'Authorization':'Bearer '+self._key},seconds=self._seconds,limit=65536,
            image_extraction=True)
        try:
            text = _response_text(data)
            details = data.get('incomplete_details')
            reason = details.get('reason') if isinstance(details, dict) else None
            namespace=SimpleNamespace(status=data['status'],output_text=text,
                incomplete_reason=reason if reason in ('max_output_tokens','content_filter') else None,
                id=data.get('id'),usage=data.get('usage'))
            namespace.output=[SimpleNamespace(**item) for item in data.get('output',[])]
            return namespace
        except (KeyError, TypeError, ValueError):
            raise ExtractionResponseError('extraction_response_shape',
                                          'Invalid provider response') from None


class TelegramMedia:
    """Bounded getFile/download for approved screenshots. Fixed host, no redirects."""
    def __init__(self,client,token,*,seconds):
        if not isinstance(token,str) or not re.fullmatch(r'[0-9]{1,20}:[A-Za-z0-9_-]{20,200}',token):
            raise ValueError('Explicit bot token required')
        self._client,self._token,self._seconds=client,token,_seconds(seconds)

    def fetch(self,file_id,mime):
        """Return validated file bytes; rejects oversized/reported-unknown media."""
        if not isinstance(file_id,str) or not 1<=len(file_id)<=256:
            raise ValueError('Invalid file reference')
        if mime not in ('image/png','image/jpeg'):
            raise ValueError('Use a PNG or JPEG screenshot')
        data=_json_post(self._client,'https://api.telegram.org/bot'+self._token+'/getFile',
            {'file_id':file_id},{},seconds=self._seconds,limit=32768)
        result=data.get('result')
        if (data.get('ok') is not True or not isinstance(result,dict)
                or result.get('file_id')!=file_id):
            raise RuntimeError('Media metadata uncertain; no automatic retry')
        reported=result.get('file_size')
        if reported is not None and (
                type(reported) is not int or not 1<=reported<=MAX_IMAGE_BYTES):
            raise ValueError('Reported file size exceeds limit')
        path=validate_file_path(result.get('file_path',''))
        url='https://api.telegram.org/file/bot'+self._token+'/'+path
        deadline=monotonic()+self._seconds
        body=bytearray()
        try:
            with self._client.stream('GET',url,follow_redirects=False) as response:
                if response.status_code!=200 or response.request.url.host not in TELEGRAM_HOSTS:
                    raise ValueError()
                for chunk in response.iter_raw():
                    if monotonic()>=deadline or len(body)+len(chunk)>MAX_IMAGE_BYTES:
                        raise ValueError()
                    body.extend(chunk)
                if monotonic()>=deadline:raise ValueError()
        except Exception:
            raise RuntimeError('Media download uncertain; no automatic retry') from None
        return bytes(body),mime
