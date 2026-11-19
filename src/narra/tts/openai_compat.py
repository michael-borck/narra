"""OpenAI-compatible voice: the OpenAI standard ``/v1/audio/speech``.

POSTs ``{model, input, voice, response_format, speed}`` and returns the audio
bytes. Works with OpenAI, Speaches, LocalAI, and any compatible server. A local
server usually needs no key, so the key is optional and only a ``base_url`` is
required.
"""

from __future__ import annotations

import os

import requests

from narra.tts.base import SpeakRequest, SpeakResult, VoiceError, VoiceProvider


class OpenAICompatibleVoice(VoiceProvider):
    name = "openai-compatible"
    default_model = "gpt-4o-mini-tts"

    def synthesize(self, request: SpeakRequest) -> SpeakResult:
        base_url = request.base_url or os.getenv("OPENAI_BASE_URL")
        if not base_url:
            raise VoiceError(
                "The 'openai-compatible' voice needs a base_url (config "
                "voices.openai-compatible.base_url or OPENAI_BASE_URL)."
            )
        base_url = base_url.rstrip("/")
        api_key = request.api_key or os.getenv("OPENAI_API_KEY")
        model = request.model or self.default_model

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "input": request.text,
            "voice": request.voice_id,
            "response_format": request.response_format,
            "speed": request.speed,
        }

        try:
            response = requests.post(
                f"{base_url}/audio/speech",
                json=payload,
                headers=headers,
                timeout=request.timeout,
            )
        except requests.RequestException as e:
            raise VoiceError(f"openai-compatible voice error: {e}") from e

        if not response.ok:
            raise VoiceError(
                f"openai-compatible voice returned {response.status_code}: "
                f"{_error_detail(response)}"
            )
        if not response.content:
            raise VoiceError("openai-compatible voice returned no audio")

        return SpeakResult(
            data=response.content, response_format=request.response_format
        )


def _error_detail(response: requests.Response) -> str:
    try:
        body = response.json()
        return str(body.get("error", {}).get("message") or body)
    except ValueError:
        return response.text[:300]
