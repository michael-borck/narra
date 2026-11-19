"""Edge-TTS voice: free neural voices, no key.

Wraps ``edge_tts.Communicate(text, voice)`` and returns MP3 bytes, retrying a
few times on ``NoAudioReceived`` (a common transient edge-tts failure).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from narra.tts.base import SpeakRequest, SpeakResult, VoiceError, VoiceProvider


class EdgeVoice(VoiceProvider):
    name = "edge"
    default_model = None

    def synthesize(self, request: SpeakRequest) -> SpeakResult:
        try:
            import edge_tts
        except ImportError as e:
            raise VoiceError(
                "The 'edge' voice needs edge-tts. Install it with:\n"
                "  pip install \"narra[edge]\""
            ) from e

        last_error: Exception | None = None
        for attempt in range(3):
            fd, tmp = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            try:
                asyncio.run(self._save(edge_tts, request.text, request.voice_id, tmp))
                data = Path(tmp).read_bytes()
                if data:
                    return SpeakResult(data=data, response_format="mp3")
                last_error = VoiceError("edge-tts produced no audio")
            except Exception as e:  # noqa: BLE001 - edge raises several types
                last_error = e
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            if attempt < 2:
                import time

                time.sleep(1.5)

        raise VoiceError(f"edge-tts failed after 3 attempts: {last_error}")

    @staticmethod
    async def _save(edge_tts, text: str, voice: str, path: str) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(path)
