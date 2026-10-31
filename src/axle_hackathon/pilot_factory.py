"""Fixed synthetic-only composition. No environment reads, launcher or automatic start."""
from .pilot_host import PilotHost
from .pilot_http import create_http_client
from .pilot_lifecycle import PilotLifecycle
from .pilot_meta import PilotDelegator
from .pilot_transports import MetaResponsesClient, TelegramSender


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
