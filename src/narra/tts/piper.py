"""Piper voice: local CPU, tiny ONNX voices.

Skeleton stub. The intended shape: locate (or download on first run) the piper
binary and a sha256-pinned voice, then spawn ``piper -m voice.onnx
--output-raw`` and wrap the 16-bit mono PCM in a WAV header. Piper is fast
(~0.05x realtime on arm64) and needs no GPU.
"""

from __future__ import annotations

from narra.tts.base import SpeakRequest, SpeakResult, VoiceError, VoiceProvider


class PiperVoice(VoiceProvider):
    name = "piper"
    default_model = None

    def synthesize(self, request: SpeakRequest) -> SpeakResult:
        # TODO(M3): resolve voice, spawn piper, wrap PCM as WAV, return bytes.
        raise VoiceError(
            "The 'piper' voice is not implemented yet (Narra 0.0.1 skeleton). "
            "See SPEC.md §10 M3."
        )
