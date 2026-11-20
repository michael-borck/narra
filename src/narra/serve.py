"""Narra web UI: a single page (source -> script -> preview/edit -> episode).

The flow is two-step so the user can edit the script before spending any TTS:

1. ``POST /api/script`` — write a script from a source.
2. ``POST /api/audio``  — voice an (edited) script into an episode.

The session gallery lives in memory only; nothing touches disk until Save.
Requires the [serve] extra.
"""

from __future__ import annotations

import base64
import copy
import os
import tempfile
import threading
import uuid
from collections import OrderedDict
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from narra import __version__, core
from narra.formats import format_options, format_prompt, get_format
from narra.script import outline_to_dialogue, read_source
from narra.speakers import resolve_speakers
from narra.writers.base import DialogueLine, WriterError

#: In-memory session gallery cap (privacy: it dies with the process).
MAX_EPISODES = 50

#: Which env vars make a provider usable (reported to the UI).
_PROVIDER_ENV = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openai-compatible": ("OPENAI_API_KEY", "OPENAI_BASE_URL"),
}


class ScriptBody(BaseModel):
    source_text: str
    format: str = "deep-dive"
    writer: str | None = None
    speakers: list[dict[str, Any]] | None = None


class AudioBody(BaseModel):
    lines: list[dict[str, str]]
    format: str = "deep-dive"
    writer: str | None = None
    speakers: list[dict[str, Any]] | None = None
    source_text: str = ""


class CompareBody(BaseModel):
    lines: list[dict[str, str]]
    format: str = "deep-dive"
    writer: str | None = None
    speakers: list[dict[str, Any]] | None = None
    voices: list[str] = []


class TestBody(BaseModel):
    writer: str | None = None
    voice: str | None = None
    gemini_key: str | None = None
    openai_url: str | None = None
    openai_key: str | None = None
    openai_writer_model: str | None = None
    openai_voice_model: str | None = None
    ollama_url: str | None = None
    ollama_model: str | None = None


def _page_html() -> str:
    return (
        resources.files("narra")
        .joinpath("serve_page.html")
        .read_text(encoding="utf-8")
    )


def _error_detail(exc: Exception) -> str:
    return str(exc)


def _settings_with_overrides(base: dict[str, Any], body: TestBody) -> dict[str, Any]:
    """Merge the Settings-sheet fields over the loaded config (for a test)."""
    s = copy.deepcopy(base)
    if body.writer:
        s["writer"] = body.writer
    if body.voice:
        s["voice"] = body.voice

    writers = s.setdefault("writers", {})
    if body.gemini_key:
        writers.setdefault("gemini", {})["api_key"] = body.gemini_key
    if body.openai_url or body.openai_key or body.openai_writer_model:
        block = writers.setdefault("openai-compatible", {})
        if body.openai_url:
            block["base_url"] = body.openai_url
        if body.openai_key:
            block["api_key"] = body.openai_key
        if body.openai_writer_model:
            block["model"] = body.openai_writer_model
    if body.ollama_url or body.ollama_model:
        block = writers.setdefault("ollama", {})
        if body.ollama_url:
            block["base_url"] = body.ollama_url
        if body.ollama_model:
            block["model"] = body.ollama_model

    voices = s.setdefault("voices", {})
    if body.gemini_key:
        voices.setdefault("gemini", {})["api_key"] = body.gemini_key
    if body.openai_url or body.openai_key or body.openai_voice_model:
        block = voices.setdefault("openai-compatible", {})
        if body.openai_url:
            block["base_url"] = body.openai_url
        if body.openai_key:
            block["api_key"] = body.openai_key
        if body.openai_voice_model:
            block["model"] = body.openai_voice_model
    return s


def create_app(config: dict[str, Any] | None = None, token: str | None = None) -> FastAPI:
    """Build the FastAPI app for the web UI.

    ``token`` gates the API when set (an empty token leaves it open, for
    localhost). The gallery is held in memory and capped at MAX_EPISODES.
    """
    settings = config or {}
    app = FastAPI(title="Narra", version=__version__)
    # The desktop Settings sheet (served from the Tauri origin) calls the
    # sidecar for /api/test, so allow that origin through CORS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    episodes: OrderedDict[str, core.Episode] = OrderedDict()
    saved_ids: set[str] = set()
    lock = threading.Lock()

    def guard(
        request: Request,
        x_narra_token: str | None = Header(default=None),
    ) -> None:
        if not token:
            return
        supplied = (
            x_narra_token
            or request.query_params.get("token")
            or request.cookies.get("narra_token")
        )
        if supplied != token:
            raise HTTPException(status_code=401, detail="Invalid or missing token.")

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

    @app.get("/api/config", dependencies=[Depends(guard)])
    def get_config() -> JSONResponse:
        speakers = resolve_speakers(settings.get("speakers"))
        writers = ["gemini", "openai-compatible", "ollama"]
        voices = ["edge", "openai", "openai-compatible", "gemini", "piper", "kokoro"]
        available = {
            name: any(os.getenv(var) for var in envs)
            for name, envs in _PROVIDER_ENV.items()
        }
        return JSONResponse(
            {
                "version": __version__,
                "requires_token": bool(token),
                "writer": settings.get("writer") or "gemini",
                "voice": settings.get("voice") or "edge",
                "format": settings.get("format") or "deep-dive",
                "formats": format_options(),
                "writers": writers,
                "voices": voices,
                "providers_available": available,
                "speakers": [
                    {
                        "name": s.name,
                        "persona": s.persona,
                        "provider": s.provider,
                        "voice_id": s.voice_id,
                        "model": s.model,
                    }
                    for s in speakers
                ],
            }
        )

    @app.post("/api/extract", dependencies=[Depends(guard)])
    async def extract(file: UploadFile = File(...)) -> JSONResponse:
        data = await file.read()
        with tempfile.NamedTemporaryFile(
            suffix=Path(file.filename or "upload.txt").suffix, delete=False
        ) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            text = read_source(tmp_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=_error_detail(e)) from e
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        return JSONResponse({"text": text, "name": file.filename})

    @app.post("/api/script", dependencies=[Depends(guard)])
    def make_script(body: ScriptBody) -> JSONResponse:
        fmt = get_format(body.format)
        writer_name = body.writer or str(settings.get("writer") or "gemini")
        speakers = resolve_speakers(body.speakers or settings.get("speakers"))
        try:
            lines = outline_to_dialogue(
                body.source_text,
                format_prompt(fmt.key),
                writer_name,
                settings,
                speakers=speakers,
            )
        except WriterError as e:
            raise HTTPException(status_code=400, detail=_error_detail(e)) from e
        return JSONResponse(
            {
                "format": fmt.key,
                "writer": writer_name,
                "lines": [{"speaker": ln.speaker, "text": ln.text} for ln in lines],
            }
        )

    @app.post("/api/audio", dependencies=[Depends(guard)])
    def make_audio(body: AudioBody) -> JSONResponse:
        lines = [DialogueLine(speaker=ln.get("speaker", ""), text=ln.get("text", "")) for ln in body.lines]
        lines = [ln for ln in lines if ln.text.strip()]
        if not lines:
            raise HTTPException(status_code=400, detail="No dialogue lines to speak.")
        speakers = resolve_speakers(body.speakers or settings.get("speakers"))
        fmt = get_format(body.format)
        writer_name = body.writer or str(settings.get("writer") or "gemini")
        try:
            audio = core.voice_lines(lines, speakers, settings)
        except core.GenerationError as e:
            raise HTTPException(status_code=400, detail=_error_detail(e)) from e
        except Exception as e:  # noqa: BLE001 - surface provider errors to the UI
            raise HTTPException(status_code=400, detail=_error_detail(e)) from e

        episode = core.Episode(
            lines=lines,
            audio=audio,
            source=body.source_text,
            source_path="(web)",
            format=fmt.key,
            writer=writer_name,
            voices=[s.voice_ref() for s in speakers],
        )
        episode_id = uuid.uuid4().hex[:12]
        with lock:
            episodes[episode_id] = episode
            while len(episodes) > MAX_EPISODES:
                episodes.popitem(last=False)
        return JSONResponse(
            {
                "id": episode_id,
                "mime": "audio/mpeg",
                "transcript": "\n\n".join(ln.text for ln in lines),
                "audio": base64.b64encode(audio).decode("ascii"),
            }
        )

    @app.post("/api/compare", dependencies=[Depends(guard)])
    def compare(body: CompareBody) -> JSONResponse:
        lines = [DialogueLine(speaker=ln.get("speaker", ""), text=ln.get("text", "")) for ln in body.lines]
        lines = [ln for ln in lines if ln.text.strip()]
        if not lines:
            raise HTTPException(status_code=400, detail="No dialogue lines to speak.")
        speakers = resolve_speakers(body.speakers or settings.get("speakers"))
        fmt = get_format(body.format)
        writer_name = body.writer or str(settings.get("writer") or "gemini")
        voices = [v for v in (body.voices or []) if v]
        if not voices:
            voices = [str(settings.get("voice") or "edge")]

        results: list[dict[str, Any]] = []
        for provider in voices:
            try:
                audio = core.voice_lines(lines, speakers, settings, voice_override=provider)
            except Exception as e:  # noqa: BLE001 - one provider must not stop the rest
                results.append({"voice": provider, "ok": False, "detail": _error_detail(e)})
                continue
            episode = core.Episode(
                lines=lines,
                audio=audio,
                source="",
                source_path="(compare)",
                format=fmt.key,
                writer=writer_name,
                voices=[s.voice_ref() for s in speakers],
            )
            episode_id = uuid.uuid4().hex[:12]
            with lock:
                episodes[episode_id] = episode
                while len(episodes) > MAX_EPISODES:
                    episodes.popitem(last=False)
            results.append(
                {
                    "voice": provider,
                    "ok": True,
                    "id": episode_id,
                    "transcript": "\n\n".join(ln.text for ln in lines),
                }
            )
        return JSONResponse({"results": results})

    @app.post("/api/test", dependencies=[Depends(guard)])
    def test_connection(body: TestBody) -> JSONResponse:
        """Check that the configured writer and voice can be reached."""
        from narra import testconn

        effective = _settings_with_overrides(settings, body)
        writer_name = str(effective.get("writer") or "gemini")
        voice_name = str(effective.get("voice") or "edge")
        w_ok, w_detail = testconn.test_writer(effective, writer_name)
        v_ok, v_detail = testconn.test_voice(effective, voice_name)
        return JSONResponse(
            {
                "writer": {"name": writer_name, "ok": w_ok, "detail": w_detail},
                "voice": {"name": voice_name, "ok": v_ok, "detail": v_detail},
            }
        )

    @app.get("/api/episodes", dependencies=[Depends(guard)])
    def list_episodes() -> JSONResponse:
        with lock:
            items = [
                {
                    "id": eid,
                    "format": ep.format,
                    "writer": ep.writer,
                    "lines": len(ep.lines),
                    "created": ep.created,
                    "saved": eid in saved_ids,
                }
                for eid, ep in episodes.items()
            ]
        return JSONResponse({"episodes": items})

    @app.get("/api/episodes/{episode_id}/audio", dependencies=[Depends(guard)])
    def episode_audio(episode_id: str) -> Response:
        with lock:
            episode = episodes.get(episode_id)
        if episode is None:
            raise HTTPException(status_code=404, detail="Episode not found.")
        return Response(content=episode.audio, media_type="audio/mpeg")

    @app.delete("/api/episodes/{episode_id}", dependencies=[Depends(guard)])
    def delete_episode(episode_id: str) -> JSONResponse:
        with lock:
            existed = episodes.pop(episode_id, None) is not None
        if not existed:
            raise HTTPException(status_code=404, detail="Episode not found.")
        return JSONResponse({"ok": True})

    @app.post("/api/episodes/{episode_id}/save", dependencies=[Depends(guard)])
    def save_episode(episode_id: str) -> JSONResponse:
        serve_cfg = settings.get("serve") or {}
        out_dir = str(serve_cfg.get("out_dir") or "~/Podcasts/Narra")
        with lock:
            episode = episodes.get(episode_id)
        if episode is None:
            raise HTTPException(status_code=404, detail="Episode not found.")
        try:
            audio_path, _ = core.save_episode(episode, out_dir=out_dir)
        except core.GenerationError as e:
            raise HTTPException(status_code=400, detail=_error_detail(e)) from e
        with lock:
            saved_ids.add(episode_id)
        return JSONResponse({"ok": True, "path": str(audio_path)})

    return app
