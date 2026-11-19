"""Edge-TTS voice: free neural voices, no key.

Skeleton stub. The intended shape: wrap ``edge_tts.Communicate(text, voice)``,
save to a temp file, read the bytes, and retry on ``NoAudioReceived`` a few
times. One process per episode with an asyncio loop is fine (edge-tts is async).
"""

from __future__ import annotations

from narra.tts.base import SpeakRequest, SpeakResult, VoiceError, VoiceProvider


class EdgeVoice(VoiceProvider):
    name = "edge"
    default_model = None

    def synthesize(self, request: SpeakRequest) -> SpeakResult:
        # TODO(M1): asyncio.run(_save(text, voice_id, tmp)); read bytes; retry.
        raise VoiceError(
            "The 'edge' voice is not implemented yet (Narra 0.0.1 skeleton). "
            "See SPEC.md §10 M1."
        )
