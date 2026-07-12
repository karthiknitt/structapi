"""Rate limiting (separate module: needs its own env before import)."""

import importlib
import os

from fastapi.testclient import TestClient


def test_rate_limit_429(monkeypatch):
    monkeypatch.setenv("STRUCTAPI_KEYS", "rl-key")
    monkeypatch.setenv("STRUCTAPI_RATE_LIMIT", "3")
    import structapi.security as sec
    importlib.reload(sec)
    from structapi import main
    importlib.reload(main)
    client = TestClient(main.app)
    h = {"x-api-key": "rl-key"}
    codes = [client.post("/v1/calc/mix", json={"fck": 25}, headers=h).status_code
             for _ in range(6)]
    assert codes[0] == 200
    assert 429 in codes
