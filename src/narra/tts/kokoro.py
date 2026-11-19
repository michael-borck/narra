"""Kokoro voice: local CPU via ``kokoro-onnx``, or a Speaches server.

Skeleton stub. The intended shape: synthesize with ``kokoro-onnx`` locally
(~120 MB model, downloaded once), or POST to a Speaches ``/v1/audio/speech``
endpoint. Kokoro-82M is small enough to run comfortably on CPU.
"""

from __future__ import annotations

from narra.tts.base import SpeakRequest, SpeakResult, VoiceError, VoiceProvider


class KokoroVoice(VoiceProvider):
    name = "kokoro"
    default_model = None

    def synthesize(self, request: SpeakRequest) -> SpeakResult:
        # TODO(M3): kokoro-onnx create/voice -> wav bytes, or Speaches POST.
        raise VoiceError(
            "The 'kokoro' voice is not implemented yet (Narra 0.0.1 skeleton). "
            "See SPEC.md §10 M3."
        )
