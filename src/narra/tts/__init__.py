"""Voice registry: name -> thin TTS client."""

from __future__ import annotations

from narra.tts.base import (
    SpeakRequest,
    SpeakResult,
    VoiceError,
    VoiceProvider,
)
from narra.tts.edge import EdgeVoice
from narra.tts.gemini import GeminiVoice
from narra.tts.kokoro import KokoroVoice
from narra.tts.openai_compat import OpenAICompatibleVoice
from narra.tts.piper import PiperVoice

__all__ = [
    "SpeakRequest",
    "SpeakResult",
    "VoiceError",
    "VoiceProvider",
    "VOICES",
    "get_voice",
    "EdgeVoice",
    "OpenAICompatibleVoice",
    "GeminiVoice",
    "PiperVoice",
    "KokoroVoice",
]

#: Alias -> class. "openai" maps to the compatible client but requires a key.
VOICES: dict[str, type[VoiceProvider]] = {
    "edge": EdgeVoice,
    "openai": OpenAICompatibleVoice,
    "openai-compatible": OpenAICompatibleVoice,
    "gemini": GeminiVoice,
    "piper": PiperVoice,
    "kokoro": KokoroVoice,
}


def get_voice(name: str) -> VoiceProvider:
    """Instantiate a voice provider by name."""
    try:
        voice_cls = VOICES[name.lower()]
    except KeyError:
        known = ", ".join(sorted(set(VOICES)))
        raise VoiceError(f"Unknown voice '{name}'. Choose from: {known}") from None
    return voice_cls()
