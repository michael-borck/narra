"""Kokoro voice: local CPU via ``kokoro-onnx`` (or a Speaches server).

Kokoro-82M is a small open model that runs on CPU. This provider uses the
``kokoro-onnx`` package and downloads the ONNX weights on first use into
``~/.narra/kokoro/`` (or ``NARRA_HOME``). It returns 16-bit mono WAV.

Install with ``pip install "narra[local]"`` (pulls kokoro-onnx + numpy).
"""

from __future__ import annotations

import importlib
import os
import re
from pathlib import Path
from typing import Any

from narra.tts._download import download
from narra.tts.base import (
    SpeakRequest,
    SpeakResult,
    VoiceError,
    VoiceProvider,
    wrap_pcm_wav,
)

_MODEL_BASE = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
)
_MODEL_FILE = "kokoro-v1.0.onnx"
_VOICES_FILE = "voices-v1.0.bin"


def _base_dir() -> Path:
    override = os.getenv("NARRA_KOKORO_DIR")
    if override:
        return Path(override)
    home = os.getenv("NARRA_HOME") or str(Path.home() / ".narra")
    return Path(home) / "kokoro"


def _ensure_models(base: Path) -> tuple[Path, Path]:
    base.mkdir(parents=True, exist_ok=True)
    onnx = base / _MODEL_FILE
    voices = base / _VOICES_FILE
    if not onnx.exists() or onnx.stat().st_size < 1_000_000:
        download(f"{_MODEL_BASE}/{_MODEL_FILE}", onnx)
    if not voices.exists() or voices.stat().st_size < 1_000:
        download(f"{_MODEL_BASE}/{_VOICES_FILE}", voices)
    return onnx, voices


class KokoroVoice(VoiceProvider):
    name = "kokoro"
    default_model = None
    default_voice = "af_sarah"

    def __init__(self) -> None:
        self._base = _base_dir()
        self._kokoro: Any = None

    @staticmethod
    def _lang(voice: str) -> str:
        if voice[:1] in ("b",):
            return "en-gb"
        return "en-us"

    def _resolve_voice(self, voice_id: str) -> str:
        # Kokoro names look like af_sarah / am_adam / bf_emma / bm_george.
        if voice_id and re.match(r"^[ab][mf]_", voice_id):
            return voice_id
        return self.default_voice

    def _load(self) -> Any:
        if self._kokoro is not None:
            return self._kokoro
        try:
            kokoro_onnx = importlib.import_module("kokoro_onnx")
        except ImportError as e:
            raise VoiceError(
                "The 'kokoro' voice needs kokoro-onnx + numpy. Install with:\n"
                "  pip install \"narra[local]\""
            ) from e
        onnx, voices = _ensure_models(self._base)
        self._kokoro = kokoro_onnx.Kokoro(str(onnx), str(voices))
        return self._kokoro

    def synthesize(self, request: SpeakRequest) -> SpeakResult:
        kokoro = self._load()
        np = importlib.import_module("numpy")
        voice = self._resolve_voice(request.voice_id)
        try:
            samples, sample_rate = kokoro.create(
                request.text,
                voice=voice,
                speed=request.speed or 1.0,
                lang=self._lang(voice),
            )
        except Exception as e:
            raise VoiceError(f"kokoro synthesis failed: {e}") from e
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        return SpeakResult(
            data=wrap_pcm_wav(pcm, sample_rate=int(sample_rate)),
            response_format="wav",
        )
