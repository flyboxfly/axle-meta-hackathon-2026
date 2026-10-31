"""HTTP phase-timeout configuration; no endpoints, credentials or requests at import."""
import httpx
from .pilot_execution import _seconds


def create_http_client(*, connect, read, write, pool, connections):
    if type(connections) is not int or not 1 <= connections <= 2:
        raise ValueError('One or two connections required')
    timeout = httpx.Timeout(connect=_seconds(connect),read=_seconds(read),
                            write=_seconds(write),pool=_seconds(pool))
    limits = httpx.Limits(max_connections=connections,max_keepalive_connections=connections)
    transport = httpx.HTTPTransport(retries=0,limits=limits,trust_env=False)
    try:
        return httpx.Client(transport=transport,timeout=timeout,
                            follow_redirects=False,trust_env=False)
    except Exception:
        transport.close()
        raise
