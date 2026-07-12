"""The frozen v1 response envelope + JSON sanitation helpers."""

from __future__ import annotations

import base64
import dataclasses
import math
from typing import Any

import numpy as np

from iscodes import DISCLAIMER, tables
from . import API_VERSION


def sanitize(obj: Any) -> Any:
    """Make iscodes results JSON-safe: numpy -> python, dataclass -> dict,
    tuples -> lists, NaN/inf -> None, drop large arrays."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return sanitize(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, np.ndarray):
        return None if obj.size > 64 else [sanitize(x) for x in obj.tolist()]
    if isinstance(obj, (list, tuple)):
        return [sanitize(x) for x in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        obj = float(obj)
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else round(obj, 6)
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    return str(obj)


def checks_list(checks: list) -> list[dict]:
    return [{"name": str(n), "ok": bool(o)} for n, o in checks]


def artifact(name: str, content: bytes, content_type: str) -> dict:
    return {"name": name, "content_type": content_type, "encoding": "base64",
            "content": base64.b64encode(content).decode("ascii")}


def envelope(ok: bool, checks: list, data: dict,
             artifacts: list[dict] | None = None) -> dict:
    return {
        "api_version": API_VERSION,
        "ok": bool(ok),
        "checks": checks_list(checks),
        "data": sanitize(data),
        "artifacts": artifacts or [],
        "code_editions": tables.CODE_EDITIONS,
        "disclaimer": DISCLAIMER,
    }
