"""Gemini native TTS voice (per line).

Reconstructed from the original ``generate_notebook.py``: one
``generate_content`` call with ``response_modalities=["AUDIO"]`` and a
``SpeechConfig`` carrying a prebuilt voice. Gemini returns 24 kHz, 16-bit mono
PCM; this provider wraps it in a WAV container so the core can stitch it with
every other provider.
"""

from __future__ import annotations

import os

from narra.tts.base import (
    SpeakRequest,
    SpeakResult,
    VoiceError,
    VoiceProvider,
    wrap_pcm_wav,
)


class GeminiVoice(VoiceProvider):
    name = "gemini"
    default_model = "gemini-3.8-flash-tts"
    sample_rate = 24000

    def synthesize(self, request: SpeakRequest) -> SpeakResult:
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise VoiceError(
                "The 'gemini' voice needs google-genai. Install it with:\n"
                "  pip install \"narra[gemini]\""
            ) from e

        api_key = (
            request.api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        if not api_key:
            raise VoiceError(
                "The 'gemini' voice needs an API key (config voices.gemini.api_key, "
                "GEMINI_API_KEY, or GOOGLE_API_KEY)."
            )
        model = request.model or self.default_model

        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=request.voice_id
                )
            )
        )

        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(api_version="v1beta"),
            )
            response = client.models.generate_content(
                model=model,
                contents=request.text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=speech_config,
                ),
            )
            pcm = _extract_pcm(response)
        except VoiceError:
            raise
        except Exception as e:
            raise VoiceError(f"gemini voice error: {e}") from e

        if not pcm:
            raise VoiceError("gemini voice returned no audio")

        return SpeakResult(
            data=wrap_pcm_wav(pcm, sample_rate=self.sample_rate),
            response_format="wav",
        )


def _extract_pcm(response: object) -> bytes:
    """Pull the first inline audio part out of a Gemini response, or fail."""
    candidates = getattr(response, "candidates", None)
    if not candidates:
        raise VoiceError("gemini voice returned no candidates")
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None)
    if not parts:
        raise VoiceError("gemini voice returned no audio parts")
    inline = getattr(parts[0], "inline_data", None)
    data = getattr(inline, "data", None)
    if not data:
        raise VoiceError("gemini voice returned no audio data")
    return data
