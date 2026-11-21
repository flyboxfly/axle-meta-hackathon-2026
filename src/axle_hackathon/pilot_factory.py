"""Fixed host compositions. No environment reads, launcher or automatic start."""
from .opening_meta import OpeningDelegator
from .opening_telegram import OpeningConversation, create_opening_app
from .opening_workflow import OpeningSessions
from .pilot_host import PilotHost
from .pilot_http import create_http_client
from .pilot_lifecycle import PilotLifecycle
from .pilot_meta import PilotDelegator
from .pilot_runtime import OpeningWorker
from .pilot_transports import (MetaImageClient, MetaResponsesClient, TelegramMedia,
                               TelegramSender, TelegramWebAppButton)


def build_synthetic_host(path, bindings, policy, *, provider_key, bot_token,
                         webhook_secret, allowed_host, global_limit, carrier_limit):
    clients=[]
    try:
        # Separate pools prevent model traffic from consuming sender connections.
        model_http=create_http_client(connect=3,read=10,write=3,pool=1,connections=1)
        clients.append(model_http)
        telegram_http=create_http_client(connect=2,read=3,write=2,pool=1,connections=2)
        clients.append(telegram_http)
        model=MetaResponsesClient(model_http,provider_key,seconds=15)
        sender=TelegramSender(telegram_http,bot_token,
            allowed_chats={chat for user,chat in bindings},seconds=4)
        owner=PilotLifecycle(path,bindings,policy,
            delegator_factory=lambda inbox:PilotDelegator(inbox,model),send=sender,
            webhook_secret=webhook_secret,allowed_host=allowed_host,
            global_limit=global_limit,carrier_limit=carrier_limit,
            provider_timeout=20,interval=1,transport_clients=clients)
        return PilotHost(owner,shutdown_timeout=6)
    except Exception:
        # Includes failed second client creation and failed inbox acquisition, both
        # outside lifecycle's own partial-construction cleanup boundary.
        for client in clients:
            try:
                if not client.is_closed:client.close()
            except Exception:pass
        raise RuntimeError('Synthetic host construction failed; cleanup attempted') from None


def build_opening_host(path, bindings, policy, *, provider_key, bot_token,
                       webhook_secret, allowed_host, global_limit, carrier_limit):
    clients=[]
    try:
        # Separate pools prevent model and media traffic from sharing connections.
        text_http=create_http_client(connect=3,read=10,write=3,pool=1,connections=1)
        clients.append(text_http)
        image_http=create_http_client(connect=3,read=30,write=10,pool=1,connections=1)
        clients.append(image_http)
        telegram_http=create_http_client(connect=2,read=15,write=2,pool=1,connections=2)
        clients.append(telegram_http)
        text=MetaResponsesClient(text_http,provider_key,seconds=15)
        image=MetaImageClient(image_http,provider_key,seconds=40)
        sender=TelegramSender(telegram_http,bot_token,
            allowed_chats={chat for user,chat in bindings},seconds=4)
        button=TelegramWebAppButton(telegram_http,bot_token,
            allowed_chats={chat for user,chat in bindings},allowed_host=allowed_host,seconds=4)
        media=TelegramMedia(telegram_http,bot_token,seconds=15)
        def delegator_factory(inbox):
            sessions = OpeningSessions(bindings)
            inbox._opening = sessions
            return OpeningDelegator(inbox, sessions, image, text, media=media)
        def worker_factory(inbox,provider,send,*,global_limit,carrier_limit):
            return OpeningWorker(inbox,provider,send,global_limit=global_limit,
                                 carrier_limit=carrier_limit)
        def app_factory(inbox,*,webhook_secret,allowed_host,send):
            return create_opening_app(inbox,webhook_secret=webhook_secret,
                allowed_host=allowed_host,conversation=OpeningConversation(inbox),send=send,
                miniapp_bot_token=bot_token,miniapp_button=button)
        owner=PilotLifecycle(path,bindings,policy,
            delegator_factory=delegator_factory,send=sender,
            webhook_secret=webhook_secret,allowed_host=allowed_host,
            global_limit=global_limit,carrier_limit=carrier_limit,
            provider_timeout=90,interval=1,transport_clients=clients,
            worker_factory=worker_factory,app_factory=app_factory)
        return PilotHost(owner,shutdown_timeout=6)
    except Exception:
        for client in clients:
            try:
                if not client.is_closed:client.close()
            except Exception:pass
        raise RuntimeError('Opening host construction failed; cleanup attempted') from None
