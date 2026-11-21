"""Explicit private operator commands. Import never creates files or sends requests."""
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import warnings

from .pilot_http import create_http_client
from .pilot_launch import configure_private_logging, read_private_config, read_real_config
from .pilot_transports import _json_post

FAILURE='Setup stopped; remote changes may be uncertain. Inspect privately before retry.'


def private_prompt(prompt):
    # getpass otherwise falls back to echoing input if terminal control fails.
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        return getpass.getpass(prompt)


class BotOperator:
    def __init__(self,client,token):
        if not isinstance(token,str) or not re.fullmatch(r'[0-9]{1,20}:[A-Za-z0-9_-]{20,200}',token):
            raise ValueError('Invalid credential')
        self.client,self.token=client,token

    def call(self,method,payload):
        if method not in ('getMe','getWebhookInfo','getUpdates','setWebhook','deleteWebhook'):
            raise ValueError('Unsupported operator method')
        data=_json_post(self.client,'https://api.telegram.org/bot'+self.token+'/'+method,
                        payload,{},seconds=5,limit=65536)
        if data.get('ok') is not True or 'result' not in data:raise RuntimeError(FAILURE)
        return data['result']

    def identity(self):
        value=self.call('getMe',{})
        if (not isinstance(value,dict) or value.get('is_bot') is not True
                or type(value.get('id')) is not int or value['id']!=int(self.token.split(':')[0])):
            raise RuntimeError(FAILURE)
        return value

    def info(self):
        value=self.call('getWebhookInfo',{})
        if (not isinstance(value,dict) or not isinstance(value.get('url'),str)
                or type(value.get('pending_update_count')) is not int
                or value['pending_update_count']<0):raise RuntimeError(FAILURE)
        return value

    def enroll(self,user,chat,phrase):
        if self.info()['url']:raise RuntimeError(FAILURE)
        rows=self.call('getUpdates',{'limit':100,'timeout':0,'allowed_updates':['message']})
        if not isinstance(rows,list) or not 1<=len(rows)<100:raise RuntimeError(FAILURE)
        ids=[];matched=0
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'update_id','message'}:raise RuntimeError(FAILURE)
            update=row['update_id'];message=row['message']
            if type(update) is not int or not 0<=update<2**63:raise RuntimeError(FAILURE)
            if (not isinstance(message,dict) or not isinstance(message.get('from'),dict)
                    or not isinstance(message.get('chat'),dict)
                    or type(message['from'].get('id')) is not int or message['from']['id']!=user
                    or message['from'].get('is_bot') is not False
                    or type(message['chat'].get('id')) is not int or message['chat']['id']!=chat
                    or message['chat'].get('type')!='private'):raise RuntimeError(FAILURE)
            matched+=message.get('text')==phrase
            ids.append(update)
        if matched!=1 or len(set(ids))!=len(ids):raise RuntimeError(FAILURE)
        # Explicit acknowledgement, never poll concurrently with a webhook.
        if self.info()['url']:raise RuntimeError(FAILURE)
        remaining=self.call('getUpdates',{'offset':max(ids)+1,'limit':100,'timeout':0,
                                         'allowed_updates':['message']})
        if remaining!=[]:raise RuntimeError(FAILURE)

    def webhook(self,data,*,remove=False):
        self.identity()
        url='https://'+data['allowed_host']+'/telegram/webhook'
        before=self.info()
        if before['url'] not in ('',url):raise RuntimeError(FAILURE)
        if remove:
            if self.call('deleteWebhook',{'drop_pending_updates':True}) is not True:
                raise RuntimeError(FAILURE)
            after=self.info()
            if after['url']!='' or after['pending_update_count']!=0:raise RuntimeError(FAILURE)
        else:
            if before['url']:raise RuntimeError(FAILURE)
            if self.call('setWebhook',{'url':url,'secret_token':data['webhook_secret'],
                    'allowed_updates':['message'],'max_connections':1,
                    'drop_pending_updates':True}) is not True:raise RuntimeError(FAILURE)
            after=self.info()
            if (after['url']!=url or type(after.get('max_connections')) is not int
                    or after['max_connections']!=1 or after.get('allowed_updates')!=['message']):
                raise RuntimeError(FAILURE)
        return after


def validate_values(data):
    if (not re.fullmatch(r'[a-z0-9-]+\.trycloudflare\.com',data['allowed_host'])
            or len(data['allowed_host'])>253
            or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}',data['webhook_secret'])
            or not data['provider_key'] or not data['provider_key'].isascii()
            or any(c.isspace() for c in data['provider_key'])):raise ValueError('Invalid configuration')
    if any(type(data[k]) is not int or not 0<data[k]<2**53 for k in ('user_id','chat_id')):
        raise ValueError('Invalid binding')


def config_destination(path):
    path=Path(path)
    if path.name.startswith('pilot.sqlite3'):raise ValueError('Reserved storage path')
    parent=path.parent.stat()
    if (not path.is_absolute() or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid!=os.getuid() or stat.S_IMODE(parent.st_mode)!=0o700):
        raise ValueError('Private directory required')
    if any(path.parent.glob('pilot.sqlite3*')):raise ValueError('Fresh state required')
    if path.exists() or path.is_symlink():raise ValueError('New config required')
    return path


def write_config(path,data):
    validate_values(data)
    path=config_destination(path)
    raw=json.dumps(data).encode()
    if len(raw)>8192:raise ValueError('Configuration too large')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    # Failure leaves any partial file for private inspection; never overwrite/retry.
    with os.fdopen(fd,'wb') as file:
        file.write(raw);file.flush();os.fsync(file.fileno())


def main():
    configure_private_logging();os.umask(0o077)
    try:
        if not sys.stdin.isatty() or not sys.stderr.isatty():raise ValueError()
        if len(sys.argv)!=2 or sys.argv[1] not in ('prepare','prepare-opening','check','register','remove'):
            raise ValueError()
        action=sys.argv[1]
        path=os.environ.get('AXLE_PILOT_CONFIG_FILE','')
        if action in ('prepare','prepare-opening'):
            # All private values use non-echoing terminal input; no secret arguments.
            phrase_expected='PREPARE NEW OWNER TEST' if action=='prepare' else 'PREPARE NEW OPENING TEST'
            if private_prompt('After owner approval, type '+phrase_expected+': ')!=phrase_expected:
                raise ValueError()
            token=private_prompt('Dedicated bot token: ')
            expected=private_prompt('Expected dedicated bot username (without @): ')
            approval=dict(approved_synthetic_owner_test=True) if action=='prepare' else dict(approved_real_opening_test=True)
            data=dict(approval,bot_token=token,
                provider_key=private_prompt('Provider key: '),
                webhook_secret=secrets.token_urlsafe(32),
                allowed_host=private_prompt('Generated tunnel hostname: '),
                user_id=int(private_prompt('Approved owner user ID: ')),
                chat_id=int(private_prompt('Approved private chat ID: ')))
            phrase=private_prompt('Unique enrollment phrase already sent in owner chat: ')
            if not 16<=len(phrase)<=128 or not expected:raise ValueError()
            validate_values(data)
            config_destination(path)
        else:
            try:data,_=read_private_config(path)
            except RuntimeError:data,_=read_real_config(path)
            validate_values(data);token=data['bot_token']
            if action!='check' and private_prompt('After owner approval, type '+action.upper()+': ')!=action.upper():
                raise ValueError()
        with create_http_client(connect=2,read=3,write=2,pool=1,connections=1) as client:
            bot=BotOperator(client,token)
            identity=bot.identity()
            if action in ('prepare','prepare-opening'):
                if identity.get('username')!=expected:raise ValueError()
                bot.enroll(data['user_id'],data['chat_id'],phrase)
                write_config(path,data)
            elif action=='check':
                info=bot.info()
                expected_url='https://'+data['allowed_host']+'/telegram/webhook'
                if info['url'] not in ('',expected_url):raise ValueError()
                print('Webhook configured: '+str(bool(info['url']))+
                      '; pending updates: '+str(info['pending_update_count'])+
                      '; error recorded: '+str('last_error_date' in info))
            else:bot.webhook(data,remove=action=='remove')
        print('Operator step completed. No application process was started.')
        return 0
    except (Exception,KeyboardInterrupt):
        print(FAILURE,file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
