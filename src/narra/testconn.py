"""Lightweight connectivity checks for a configured writer or voice.

Used by the desktop Settings sheet's "Test connection" button (and available
to any caller via ``POST /api/test``). These are deliberately small: a one-word
chat completion for a writer, a short synthesis for a voice.
"""

from __future__ import annotations

import os
from typing import Any

from narra.config import voice_settings, writer_settings
from narra.tts import get_voice
from narra.tts.base import SpeakRequest

#: A sensible default voice per provider, used when testing without a speaker.
_DEFAULT_TEST_VOICE = {
    "edge": "en-US-AndrewNeural",
    "openai": "alloy",
    "openai-compatible": "alloy",
    "gemini": "Fenrir",
    "piper": "en_US-amy-low",
    "kokoro": "af_sarah",
}


def _gemini_key(settings: dict[str, Any]) -> str:
    return (
        settings.get("api_key")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or ""
    )


def test_writer(settings: dict[str, Any], writer: str) -> tuple[bool, str]:
    """Check that a writer can produce a completion. Returns (ok, detail)."""
    import requests

    resolved = writer_settings(settings, writer)
    model = resolved.get("model") or ""
    timeout = min(float(resolved.get("timeout") or 30), 20)

    try:
        if writer == "gemini":
            try:
                from google import genai
                from google.genai import types
            except ImportError:
                return False, "google-genai is not installed (pip install 'narra[gemini]')"
            key = _gemini_key(resolved)
            if not key:
                return False, "No Gemini API key configured."
            client = genai.Client(
                api_key=key, http_options=types.HttpOptions(api_version="v1beta")
            )
            response = client.models.generate_content(
                model=model or "gemini-flash-latest",
                contents="Reply with the single word OK.",
            )
            text = (response.text or "").strip()
            return True, (text[:80] or "OK")

        if writer == "ollama":
            base = (resolved.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
            response = requests.post(
                f"{base}/api/chat",
                json={
                    "model": model or "qwen3.5:4b",
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "stream": False,
                },
                timeout=timeout,
            )
            if not response.ok:
                return False, f"Ollama HTTP {response.status_code}: {response.text[:120]}"
            return True, f"Ollama OK ({model or 'default model'})"

        # openai-compatible
        base = resolved.get("base_url") or os.getenv("OPENAI_BASE_URL")
        if not base:
            return False, "No base_url configured for openai-compatible."
        headers = {"Content-Type": "application/json"}
        if resolved.get("api_key"):
            headers["Authorization"] = f"Bearer {resolved['api_key']}"
        response = requests.post(
            f"{base.rstrip('/')}/chat/completions",
            json={
                "model": model or "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 5,
            },
            headers=headers,
            timeout=timeout,
        )
        if not response.ok:
            return False, f"HTTP {response.status_code}: {response.text[:120]}"
        return True, f"HTTP 200 ({model or 'default model'})"
    except Exception as e:  # noqa: BLE001 - surface any provider error
        return False, str(e)[:240]


def test_voice(settings: dict[str, Any], voice: str) -> tuple[bool, str]:
    """Check that a voice can synthesize a short clip. Returns (ok, detail)."""
    resolved = voice_settings(settings, voice)
    voice_id = _DEFAULT_TEST_VOICE.get(voice, "en_US-amy-low")
    try:
        result = get_voice(voice).synthesize(
            SpeakRequest(
                text="This is a voice test.",
                voice_id=voice_id,
                model=resolved.get("model"),
                base_url=resolved.get("base_url"),
                api_key=resolved.get("api_key"),
                timeout=min(float(resolved.get("timeout") or 30), 30),
            )
        )
        return True, f"{len(result.data)} bytes ({voice_id})"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:240]
