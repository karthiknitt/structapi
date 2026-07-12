"""API-key auth + per-key token-bucket rate limiting (Phase C hardening).

STRUCTAPI_KEYS: comma-separated keys. Unset -> open DEV MODE (logged loudly).
STRUCTAPI_RATE_LIMIT: requests/minute per key (default 60; 0 disables).
"""

from __future__ import annotations

import logging
import os
import threading
import time

from fastapi import Header, HTTPException, Request

log = logging.getLogger("structapi")

_buckets: dict[str, list] = {}
_lock = threading.Lock()


def _keys() -> set[str]:
    raw = os.environ.get("STRUCTAPI_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def _rate_limit() -> int:
    try:
        return int(os.environ.get("STRUCTAPI_RATE_LIMIT", "60"))
    except ValueError:
        return 60


def _allow(key: str) -> bool:
    """Token bucket: rate/minute, burst = rate. time.monotonic-based."""
    rate = _rate_limit()
    if rate <= 0:
        return True
    now = time.monotonic()
    with _lock:
        tokens, last = _buckets.get(key, (float(rate), now))
        tokens = min(float(rate), tokens + (now - last) * rate / 60.0)
        if tokens < 1.0:
            _buckets[key] = (tokens, now)
            return False
        _buckets[key] = (tokens - 1.0, now)
        return True


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
) -> str:
    keys = _keys()
    if not keys:
        log.warning("STRUCTAPI_KEYS unset — running OPEN (dev mode)")
        caller = "dev"
    else:
        if not x_api_key or x_api_key not in keys:
            raise HTTPException(status_code=401, detail="invalid or missing x-api-key")
        caller = x_api_key[:8]
    if not _allow(caller):
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    request.state.caller = caller
    request.state.correlation_id = x_correlation_id or ""
    return caller
