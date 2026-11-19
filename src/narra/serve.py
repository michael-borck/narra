"""Narra web UI: a single page (source -> format -> speakers -> episode).

Skeleton in 0.0.1: the app serves a placeholder page and a health endpoint. The
full flow (source box, format chips, speaker strip, preview/edit, session
gallery) lands in M2. Requires the [serve] extra.
"""

from __future__ import annotations

from importlib import resources
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from narra import __version__


def _page_html() -> str:
    """Read the bundled single-page UI (no CDNs)."""
    return (
        resources.files("narra")
        .joinpath("serve_page.html")
        .read_text(encoding="utf-8")
    )


def create_app(config: dict[str, Any] | None = None) -> FastAPI:
    """Build the FastAPI app for the web UI."""
    settings = config or {}
    app = FastAPI(title="Narra", version=__version__)

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_page_html())

    @app.get("/api/health")
    def health() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "app": "narra",
                "version": __version__,
                "writer": settings.get("writer"),
                "voice": settings.get("voice"),
                "format": settings.get("format"),
            }
        )

    return app
