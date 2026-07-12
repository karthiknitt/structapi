"""Render iscodes figures/PDFs to in-memory bytes for the envelope."""

from __future__ import annotations

import os
import tempfile

from .envelope import artifact


def png_artifact(name: str, render_fn) -> dict | None:
    """render_fn(path) writes a PNG to path; returns envelope artifact."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, name)
        try:
            render_fn(path)
            with open(path, "rb") as f:
                return artifact(name, f.read(), "image/png")
        except Exception:
            return None


def pdf_artifact(name: str, render_fn) -> dict | None:
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, name)
        try:
            render_fn(path)
            with open(path, "rb") as f:
                return artifact(name, f.read(), "application/pdf")
        except Exception:
            return None
