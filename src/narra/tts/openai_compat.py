"""OpenAI-compatible voice: the OpenAI standard ``/v1/audio/speech``.

Skeleton stub. The intended shape: POST ``{base_url}/audio/speech`` with
``{model, input, voice, response_format, speed}`` and return the audio bytes.
Works with OpenAI, Speaches, LocalAI, and any compatible server.
"""

from __future__ import annotations

from narra.tts.base import SpeakRequest, SpeakResult, VoiceError, VoiceProvider


class OpenAICompatibleVoice(VoiceProvider):
    name = "openai-compatible"
    default_model = "gpt-4o-mini-tts"

    def synthesize(self, request: SpeakRequest) -> SpeakResult:
        # TODO(M1): requests.post(f"{base_url}/audio/speech",
        #   headers={Authorization: Bearer}, json={model, input, voice,
        #   response_format, speed}); return response.content.
        raise VoiceError(
            "The 'openai-compatible' voice is not implemented yet "
            "(Narra 0.0.1 skeleton). See SPEC.md §10 M1."
        )
