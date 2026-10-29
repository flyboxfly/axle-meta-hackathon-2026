"""Container HEALTHCHECK probe for axle_hackathon.remote_app (H9 review candidate).

Standard library only. Connects over container loopback TCP to 127.0.0.1:8000
(transport only; this is NOT an allowlist bypass) and sends
``GET /api/health`` with an explicit ``Host`` header taken at runtime from the
first entry of ``AXLE_API_ALLOWED_HOSTS``. The application still enforces its
host allowlist against that header; there is no localhost bypass and no
wildcard. Any missing, empty, or wildcard configuration fails closed
(nonzero exit). Bounded socket timeout; no retries here (Docker handles
retries via HEALTHCHECK --retries).
"""

from __future__ import annotations

import http.client
import json
import os
import sys

_HEALTH_PATH = "/api/health"
_CONNECT_HOST = "127.0.0.1"
_CONNECT_PORT = 8000
_TIMEOUT_SECONDS = 5.0
_MAX_BODY_BYTES = 65536


def _select_host() -> str:
    """Return the explicit Host value for the probe.

    Reads the runtime ``AXLE_API_ALLOWED_HOSTS`` (the same variable the app
    enforces) and uses its first entry. Never defaults to localhost and never
    sends a wildcard.
    """
    raw = os.environ.get("AXLE_API_ALLOWED_HOSTS", "")
    if not raw or not raw.strip():
        raise ValueError("AXLE_API_ALLOWED_HOSTS is not configured")
    if "*" in raw:
        raise ValueError("wildcard hosts are not allowed")
    first = raw.split(",")[0].strip().lower()
    if not first:
        raise ValueError("health Host entry is empty")
    if any(ch.isspace() for ch in first):
        raise ValueError("invalid health Host")
    return first


def main() -> int:
    try:
        host = _select_host()
        conn = http.client.HTTPConnection(
            _CONNECT_HOST, _CONNECT_PORT, timeout=_TIMEOUT_SECONDS
        )
        try:
            conn.request(
                "GET", _HEALTH_PATH, headers={"Host": host, "Connection": "close"}
            )
            resp = conn.getresponse()
            body = resp.read(_MAX_BODY_BYTES + 1)
        finally:
            conn.close()
        if resp.status != 200:
            return 1
        if len(body) > _MAX_BODY_BYTES:
            return 1
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return 1
        if not isinstance(data, dict):
            return 1
        if data.get("status") != "ok" or data.get("synthetic_only") is not True:
            return 1
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
