import json
import os
import httpx
import pytest
from axle_hackathon.pilot_setup import BotOperator, write_config, FAILURE
from axle_hackathon.pilot_launch import read_private_config
from test_h13_transports import TOKEN
from test_h13_telegram import SECRET


def values():
    return dict(approved_synthetic_owner_test=True,provider_key='invented',bot_token=TOKEN,
                webhook_secret=SECRET,allowed_host='invented.trycloudflare.com',user_id=1,chat_id=1)


def operator(results):
    calls=[]
    def handle(request):
        calls.append((request.url.path.rsplit('/',1)[1],json.loads(request.content)))
        answer=results.pop(0)
        if isinstance(answer,Exception):raise answer
        return httpx.Response(200,stream=httpx.ByteStream(json.dumps({'ok':True,'result':answer}).encode()))
    client=httpx.Client(transport=httpx.MockTransport(handle))
    return BotOperator(client,TOKEN),calls


def identity():return dict(id=int(TOKEN.split(':')[0]),is_bot=True,username='invented')
def info(url=''):return dict(url=url,pending_update_count=0)
def update(uid=1,chat=1):
    return dict(update_id=4,message=dict(text='invented enrollment phrase',
        **{'from':dict(id=uid,is_bot=False),'chat':dict(id=chat,type='private')}))


def test_enrollment_matches_binding_and_acknowledges_once():
    bot,calls=operator([info(),[update()],info(),[]])
    bot.enroll(1,1,'invented enrollment phrase')
    assert calls[-1][1]['offset']==5
    assert [m for m,p in calls]==['getWebhookInfo','getUpdates','getWebhookInfo','getUpdates']


@pytest.mark.parametrize('case',['foreign','boolean','phrase','webhook','nonempty_ack'])
def test_enrollment_rejects_ambiguous_identity_or_backlog(case):
    row=update(uid=2 if case=='foreign' else True if case=='boolean' else 1)
    rows=[info('https://other.invalid') if case=='webhook' else info(),[row],info(),[update()] if case=='nonempty_ack' else []]
    bot,calls=operator(rows)
    with pytest.raises(RuntimeError):bot.enroll(1,1,'wrong' if case=='phrase' else 'invented enrollment phrase')
    assert all(m not in ('setWebhook','deleteWebhook') for m,p in calls)


def test_register_exact_parameters_and_no_replace():
    data=values();url='https://'+data['allowed_host']+'/telegram/webhook'
    bot,calls=operator([identity(),info(),True,{**info(url), 'max_connections':1,'allowed_updates':['message']}])
    bot.webhook(data)
    assert calls[2]==('setWebhook',dict(url=url,secret_token=SECRET,allowed_updates=['message'],max_connections=1,drop_pending_updates=True))
    for existing in (url,'https://other.invalid'):
        bot,calls=operator([identity(),info(existing)])
        with pytest.raises(RuntimeError):bot.webhook(data)
        assert len(calls)==2


def test_remove_scope_and_acknowledgement():
    data=values();url='https://'+data['allowed_host']+'/telegram/webhook'
    bot,calls=operator([identity(),info(url),True,info()]);bot.webhook(data,remove=True)
    assert calls[2]==('deleteWebhook',{'drop_pending_updates':True})
    bot,calls=operator([identity(),info('https://other.invalid')])
    with pytest.raises(RuntimeError):bot.webhook(data,remove=True)
    assert len(calls)==2


@pytest.mark.parametrize('ack',[1,False,{'ok':True}])
def test_registration_requires_exact_true(ack):
    bot,calls=operator([identity(),info(),ack])
    with pytest.raises(RuntimeError):bot.webhook(values())
    assert len(calls)==3


def test_remote_exception_is_sanitized_and_not_retried():
    bot,calls=operator([RuntimeError('private-token private-payload')])
    with pytest.raises(RuntimeError) as error:bot.identity()
    assert 'private' not in str(error.value) and len(calls)==1


def test_exclusive_private_config_roundtrip_and_preserved_state(tmp_path):
    tmp_path.chmod(0o700);path=tmp_path/'private.json'
    write_config(path,values())
    data,db=read_private_config(path)
    assert data==values() and os.stat(path).st_mode&0o777==0o600
    before=path.read_bytes()
    with pytest.raises(ValueError):write_config(path,values())
    assert path.read_bytes()==before
    path.unlink();db.write_bytes(b'existing state')
    with pytest.raises(ValueError):write_config(path,values())
    assert db.read_bytes()==b'existing state' and not path.exists()


def test_config_rejects_symlink_and_insecure_directory(tmp_path):
    tmp_path.chmod(0o700);target=tmp_path/'target';target.write_text('preserve')
    path=tmp_path/'private.json';path.symlink_to(target)
    with pytest.raises(ValueError):write_config(path,values())
    assert target.read_text()=='preserve'
    path.unlink();tmp_path.chmod(0o755)
    with pytest.raises(ValueError):write_config(path,values())


def test_prepare_cli_hidden_inputs_and_no_secret_output(tmp_path,monkeypatch,capsys):
    import axle_hackathon.pilot_setup as setup
    tmp_path.chmod(0o700);path=tmp_path/'private.json'
    answers=iter(['PREPARE NEW OWNER TEST',TOKEN,'invented','invented-provider-key',
                  'invented.trycloudflare.com','1','1','invented enrollment phrase'])
    monkeypatch.setattr(setup.getpass,'getpass',lambda prompt:next(answers))
    monkeypatch.setattr(setup.sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(setup.sys.stderr,'isatty',lambda:True)
    monkeypatch.setattr(setup.sys,'argv',['pilot_setup','prepare'])
    monkeypatch.setenv('AXLE_PILOT_CONFIG_FILE',str(path))
    monkeypatch.setattr(setup,'configure_private_logging',lambda:None)
    monkeypatch.setattr(setup.os,'umask',lambda mode:None)
    bot,calls=operator([identity(),info(),[update()],info(),[]])
    monkeypatch.setattr(setup,'create_http_client',lambda **kwargs:bot.client)
    assert setup.main()==0
    output=capsys.readouterr()
    assert TOKEN not in output.out+output.err and 'invented-provider-key' not in output.out+output.err
    assert read_private_config(path)[0]['user_id']==1
    assert not any(method in ('setWebhook','deleteWebhook') for method,payload in calls)


def test_cli_refuses_nonterminal_without_network(monkeypatch,capsys):
    import axle_hackathon.pilot_setup as setup
    monkeypatch.setattr(setup.sys.stdin,'isatty',lambda:False)
    monkeypatch.setattr(setup,'configure_private_logging',lambda:None)
    monkeypatch.setattr(setup.os,'umask',lambda mode:None)
    monkeypatch.setattr(setup,'create_http_client',lambda **kwargs:pytest.fail('Network forbidden'))
    assert setup.main()==1
    assert capsys.readouterr().err.strip()==FAILURE


@pytest.mark.parametrize('name',['pilot.sqlite3','pilot.sqlite3.owner','pilot.sqlite3-journal'])
def test_config_cannot_occupy_runtime_storage_paths(tmp_path,name):
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError,match='Reserved storage path'):
        write_config(tmp_path/name,values())
    assert list(tmp_path.iterdir())==[]


def test_secret_prompt_aborts_before_getpass_echo_fallback(monkeypatch):
    import warnings
    import axle_hackathon.pilot_setup as setup
    echoed=[]
    def fallback(prompt):
        warnings.warn('Cannot control echo',setup.getpass.GetPassWarning)
        echoed.append(True)
        return 'secret'
    monkeypatch.setattr(setup.getpass,'getpass',fallback)
    with pytest.raises(setup.getpass.GetPassWarning):setup.private_prompt('Secret: ')
    assert not echoed
