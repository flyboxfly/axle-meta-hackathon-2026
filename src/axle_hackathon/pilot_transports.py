"""Injected HTTP adapters. No client creation, credential loading or live launcher."""
import json
import re
from time import monotonic
from types import SimpleNamespace
from .pilot_execution import _seconds


def _json_post(client,url,payload,headers,*,seconds,limit):
    deadline=monotonic()+seconds
    try:
        with client.stream('POST',url,json=payload,headers={**headers,'Accept-Encoding':'identity'},
                           follow_redirects=False) as response:
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
    except Exception:
        raise RuntimeError('Remote outcome uncertain; no automatic retry') from None


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
        message=result.get('result')
        if (result.get('ok') is not True or not isinstance(message,dict)
                or type(message.get('message_id')) is not int or message['message_id']<=0
                or not isinstance(message.get('chat'),dict)
                or type(message['chat'].get('id')) is not int
                or message['chat']['id']!=chat
                or message['chat'].get('type')!='private'):
            raise RuntimeError('Delivery uncertain; no automatic retry')
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
            return SimpleNamespace(status=data['status'],output=[SimpleNamespace(**item) for item in data['output']])
        except Exception:raise RuntimeError('Invalid provider response') from None
