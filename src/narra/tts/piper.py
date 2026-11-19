"""Piper voice: local CPU, tiny ONNX voices, no Python ML deps.

Piper is a fast neural TTS that runs comfortably on CPU (~0.05x realtime on
arm64). This provider manages its own runtime on first use:

  ~/.narra/piper/
    piper/                 the piper binary + espeak-ng-data (release tarball)
    piper-phonemize/lib/   dylib deps (macOS archives omit them)
    voices/<name>.onnx     sha256-pinned voice + .onnx.json

The download URLs and voice pins mirror the ones proven in talk-buddy
(rhasspy/piper 2023.11.14-2, piper-phonemize 2023.11.14-4). Synthesis spawns
``piper -m voice.onnx --output-raw`` and wraps the 16-bit mono PCM in a WAV.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
from pathlib import Path
from typing import Any

from narra.tts._download import download, extract
from narra.tts.base import (
    SpeakRequest,
    SpeakResult,
    VoiceError,
    VoiceProvider,
    wrap_pcm_wav,
)

PIPER_RELEASE = "2023.11.14-2"
PHONEMIZE_RELEASE = "2023.11.14-4"
_GH = "https://github.com/rhasspy"
_HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

#: Pinned voices. Keys are the names you put in a speaker's voice_id.
VOICES: dict[str, dict[str, Any]] = {
    "en_GB-alan-low": {
        "url": f"{_HF}/en/en_GB/alan/low",
        "files": [
            ("en_GB-alan-low.onnx", "a1f60584620a2bed203de823d08f5abb336fb15f3d6f33f8c341e3e2cabf5dde"),
            ("en_GB-alan-low.onnx.json", "c8164cc04b6ce102c651ce4a1e788e8429fa638501fca0723860718d4b44637e"),
        ],
    },
    "en_US-amy-low": {
        "url": f"{_HF}/en/en_US/amy/low",
        "files": [
            ("en_US-amy-low.onnx", "a5a91abb7de0f104358a25aded480ddacf1ff0762886325886ec406a2e86aab3"),
            ("en_US-amy-low.onnx.json", "2250a9a605b8dc35a116717fadc5056695dd809e34a15d02f72a0f52d53d3ebb"),
        ],
    },
}

_LOCK = threading.Lock()


def _base_dir() -> Path:
    override = os.getenv("NARRA_PIPER_DIR")
    if override:
        return Path(override)
    home = os.getenv("NARRA_HOME") or str(Path.home() / ".narra")
    return Path(home) / "piper"


def _archive_assets() -> dict[str, str]:
    system = platform.system()
    machine = platform.machine()
    if system == "Darwin":
        arch = "aarch64" if machine == "arm64" else "x64"
        return {
            "piper": f"{_GH}/piper/releases/download/{PIPER_RELEASE}/piper_macos_{arch}.tar.gz",
            "phonemize": f"{_GH}/piper-phonemize/releases/download/{PHONEMIZE_RELEASE}/piper-phonemize_macos_{arch}.tar.gz",
        }
    if system == "Linux":
        arch = "aarch64" if machine == "arm64" else "x86_64"
        return {
            "piper": f"{_GH}/piper/releases/download/{PIPER_RELEASE}/piper_linux_{arch}.tar.gz",
            "phonemize": f"{_GH}/piper-phonemize/releases/download/{PHONEMIZE_RELEASE}/piper-phonemize_linux_{arch}.tar.gz",
        }
    return {
        "piper": f"{_GH}/piper/releases/download/{PIPER_RELEASE}/piper_windows_amd64.zip",
        "phonemize": f"{_GH}/piper-phonemize/releases/download/{PHONEMIZE_RELEASE}/piper-phonemize_windows_amd64.zip",
    }


def _binary_path(base: Path) -> Path:
    name = "piper.exe" if platform.system() == "Windows" else "piper"
    return base / "piper" / name


def _find_lib_dir(base: Path) -> Path | None:
    patterns = ["libpiper_phonemize*.dylib", "libpiper_phonemize*.so", "piper_phonemize.dll"]
    for pattern in patterns:
        for hit in base.rglob(pattern):
            return hit.parent
    return None


def _ensure_runtime(base: Path) -> tuple[Path, Path]:
    """Ensure the piper binary and phonemize libs exist; return (binary, lib_dir)."""
    binary = _binary_path(base)
    if not (binary.exists() and binary.stat().st_size > 1_000_000):
        assets = _archive_assets()
        archive = base / "piper.archive"
        download(assets["piper"], archive)
        extract(archive, base)
        archive.unlink(missing_ok=True)
        if platform.system() != "Windows":
            binary.chmod(0o755)

    lib_dir = _find_lib_dir(base)
    if lib_dir is None and platform.system() != "Windows":
        assets = _archive_assets()
        archive = base / "phonemize.archive"
        download(assets["phonemize"], archive)
        extract(archive, base)
        archive.unlink(missing_ok=True)
        lib_dir = _find_lib_dir(base)

    if not binary.exists():
        raise VoiceError("Piper binary is still missing after setup.")
    return binary, lib_dir or (base / "piper-phonemize" / "lib")


def _ensure_voice(base: Path, name: str) -> tuple[Path, int]:
    """Ensure a voice is downloaded and verified; return (onnx_path, sample_rate)."""
    spec = VOICES.get(name)
    if spec is None:
        raise VoiceError(
            f"Unknown Piper voice '{name}'. Known: {', '.join(sorted(VOICES))}."
        )
    voices_dir = base / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    for filename, sha in spec["files"]:
        dest = voices_dir / filename
        if dest.exists() and dest.stat().st_size > 0:
            from narra.tts._download import sha256_file

            if sha256_file(dest) == sha:
                continue
        download(f"{spec['url']}/{filename}", dest, sha256=sha)

    onnx = voices_dir / f"{name}.onnx"
    sample_rate = 22050
    try:
        cfg = json.loads((voices_dir / f"{name}.onnx.json").read_text(encoding="utf-8"))
        sample_rate = int(cfg.get("audio", {}).get("sample_rate") or sample_rate)
    except (OSError, ValueError):
        pass
    return onnx, sample_rate


class PiperVoice(VoiceProvider):
    name = "piper"
    default_model = None
    default_voice = "en_US-amy-low"

    def _resolve_voice(self, voice_id: str) -> str:
        if voice_id in VOICES:
            return voice_id
        if voice_id and (self._base / "voices" / f"{voice_id}.onnx").exists():
            return voice_id
        return self.default_voice

    def __init__(self) -> None:
        self._base = _base_dir()

    def synthesize(self, request: SpeakRequest) -> SpeakResult:
        with _LOCK:
            binary, lib_dir = _ensure_runtime(self._base)
            name = self._resolve_voice(request.voice_id)
            onnx, sample_rate = _ensure_voice(self._base, name)

        env = dict(os.environ)
        if platform.system() == "Darwin":
            env["DYLD_LIBRARY_PATH"] = str(lib_dir)
        elif platform.system() == "Linux":
            env["LD_LIBRARY_PATH"] = f"{lib_dir}:{env.get('LD_LIBRARY_PATH', '')}"

        try:
            result = subprocess.run(
                [str(binary), "-m", str(onnx), "--output-raw"],
                input=(request.text + "\n").encode("utf-8"),
                cwd=str(self._base / "piper"),
                env=env,
                capture_output=True,
                timeout=request.timeout,
            )
        except FileNotFoundError as e:
            raise VoiceError(f"Piper binary not found: {e}") from e
        except subprocess.TimeoutExpired as e:
            raise VoiceError("Piper timed out.") from e

        if result.returncode != 0:
            raise VoiceError(
                f"Piper exited {result.returncode}: "
                f"{result.stderr.decode('utf-8', 'replace').strip()[:400]}"
            )
        if not result.stdout:
            raise VoiceError("Piper produced no audio.")

        return SpeakResult(
            data=wrap_pcm_wav(result.stdout, sample_rate=sample_rate),
            response_format="wav",
        )
