"""Voice abstraction: a line of text goes in, audio bytes come out.

Voices are thin clients over one TTS backend each. They raise VoiceError on any
failure — Narra fails loudly rather than dropping a line silently.
"""

from __future__ import annotations

import io
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class VoiceError(Exception):
    """Raised when a voice provider cannot synthesize audio."""


def wrap_pcm_wav(
    pcm: bytes,
    sample_rate: int = 24000,
    sample_width: int = 2,
    channels: int = 1,
) -> bytes:
    """Wrap raw little-endian PCM in a WAV container.

    Gemini TTS returns headerless 24 kHz, 16-bit mono PCM; wrapping it here
    lets the core treat every provider's output the same way.
    """
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


@dataclass
class SpeakRequest:
    """Everything a voice provider needs for one line."""

    text: str
    voice_id: str = "en-US-AndrewNeural"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout: float = 120.0
    #: Fraction, e.g. 1.0 normal; providers that support it map to their speed.
    speed: float = 1.0
    response_format: str = "mp3"


@dataclass
class SpeakResult:
    """One line's audio plus whatever the backend reported."""

    data: bytes
    response_format: str = "mp3"


class VoiceProvider(ABC):
    """One backend: turn a SpeakRequest into audio bytes."""

    name: str = "base"

    @abstractmethod
    def synthesize(self, request: SpeakRequest) -> SpeakResult:
        """Synthesize one line. Raises VoiceError on failure."""
        raise NotImplementedError

    def list_voices(self, request: SpeakRequest) -> list[str]:
        """Voice names this backend offers (prompt text in ``request`` is unused)."""
        raise VoiceError(f"Provider '{self.name}' cannot list voices.")

    def warn_unsupported(self, request: SpeakRequest) -> None:
        """Tell the user about request fields this backend ignores (skeleton)."""
        return None

    def unsupported(self, request: SpeakRequest) -> list[tuple[str, Any]]:
        """(label, value) pairs of request fields this backend ignores."""
        return []
