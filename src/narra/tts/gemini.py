"""Gemini native TTS voice.

Skeleton stub. The intended shape (reconstructed from the original
``generate_notebook.py``): one ``generate_content`` call with
``response_modalities=["AUDIO"]`` and a ``SpeechConfig``. Single speaker uses a
``VoiceConfig(prebuilt_voice_config=...("Fenrir"/"Leda"))``; multi-speaker uses
``MultiSpeakerVoiceConfig`` with a ``SpeakerVoiceConfig`` per speaker. The
response is 24 kHz, 16-bit mono PCM.
"""

from __future__ import annotations

from narra.tts.base import SpeakRequest, SpeakResult, VoiceError, VoiceProvider


class GeminiVoice(VoiceProvider):
    name = "gemini"
    default_model = "gemini-3.8-flash-tts"

    def synthesize(self, request: SpeakRequest) -> SpeakResult:
        # TODO(M1): single-line path; multi-speaker stitching lives in core.
        raise VoiceError(
            "The 'gemini' voice is not implemented yet (Narra 0.0.1 skeleton). "
            "See SPEC.md §10 M1 and ~/Downloads/generate_notebook.py."
        )
