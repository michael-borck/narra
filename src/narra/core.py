"""Core: turn a source document into a podcast episode on disk.

The pipeline: read source → write a script with the chosen writer → voice each
line with its speaker's provider → stitch the clips into one MP3 → save with a
JSON sidecar. Per-line voicing keeps the provider abstraction uniform; a
single-call provider (Gemini multi-speaker) can be added later without changing
this shape.
"""

from __future__ import annotations

import hashlib
import io
import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from narra.formats import format_prompt, get_format
from narra.script import clean_lines, read_source, script_text
from narra.speakers import Speaker, resolve_speakers
from narra.writers.base import DialogueLine, WriterError

#: Pause between lines, in milliseconds (matches the original script).
PAUSE_MIN_MS = 180
PAUSE_MAX_MS = 420


@dataclass
class Episode:
    """One finished episode: audio plus the inputs that produced it."""

    lines: list[DialogueLine]
    audio: bytes
    source: str
    source_path: str
    format: str
    writer: str
    voices: list[dict[str, Any]] = field(default_factory=list)
    created: str = ""


class GenerationError(Exception):
    """Raised when an episode cannot be generated."""


def generate(
    source_path: str,
    settings: dict[str, Any],
    *,
    format: str | None = None,
    writer: str | None = None,
    voice: str | None = None,
    on_progress: Any = None,
) -> Episode:
    """Generate one episode from a source file.

    ``voice`` overrides every line's provider (otherwise each speaker uses the
    provider on its profile). ``on_progress`` is an optional callable that
    receives short status strings, used by the CLI and (later) the web UI.
    """
    chosen_format = format or str(settings.get("format") or "deep-dive")
    fmt = get_format(chosen_format)
    chosen_writer = writer or str(settings.get("writer") or "gemini")

    def progress(message: str) -> None:
        if on_progress:
            on_progress(message)

    try:
        text = read_source(source_path)
    except Exception as e:
        raise GenerationError(str(e)) from e

    from narra.script import outline_to_dialogue

    speakers = resolve_speakers(settings.get("speakers"))
    progress(f"Writing a '{fmt.key}' script with {chosen_writer}…")
    try:
        lines = outline_to_dialogue(
            text, format_prompt(fmt.key), chosen_writer, settings, speakers=speakers
        )
    except WriterError as e:
        raise GenerationError(str(e)) from e

    lines = clean_lines(lines)
    if not lines:
        raise GenerationError("The writer produced no usable dialogue lines.")

    progress(f"Voicing {len(lines)} lines…")
    try:
        audio = voice_lines(lines, speakers, settings, voice_override=voice, on_progress=progress)
    except GenerationError:
        raise
    except Exception as e:
        raise GenerationError(f"Voicing failed: {e}") from e

    return Episode(
        lines=lines,
        audio=audio,
        source=text,
        source_path=source_path,
        format=fmt.key,
        writer=chosen_writer,
        voices=[s.voice_ref() for s in speakers],
        created=datetime.now(timezone.utc).isoformat(),
    )


def _speaker_for(line: DialogueLine, speakers: list[Speaker], index: int) -> Speaker:
    """Pick the speaker profile for a line, tolerating unknown names."""
    by_name = {s.name.lower(): s for s in speakers}
    match = by_name.get(line.speaker.strip().lower())
    if match:
        return match
    if speakers:
        return speakers[index % len(speakers)]
    return Speaker(name=line.speaker or "Speaker")


def voice_lines(
    lines: list[DialogueLine],
    speakers: list[Speaker],
    settings: dict[str, Any],
    *,
    voice_override: str | None = None,
    on_progress: Any = None,
) -> bytes:
    """Synthesize every line and stitch the clips into one MP3."""
    try:
        from pydub import AudioSegment
    except ImportError as e:
        raise GenerationError(
            "Stitching audio needs pydub (and ffmpeg on PATH). Install with:\n"
            "  pip install \"narra[audio]\""
        ) from e

    from narra.config import voice_settings
    from narra.tts import get_voice
    from narra.tts.base import SpeakRequest, SpeakResult

    providers: dict[str, Any] = {}
    combined = AudioSegment.empty()

    try:
        for index, line in enumerate(lines):
            speaker = _speaker_for(line, speakers, index)
            provider_name = voice_override or speaker.provider or "edge"
            provider = providers.get(provider_name)
            if provider is None:
                provider = get_voice(provider_name)
                providers[provider_name] = provider

            vset = voice_settings(settings, provider_name)
            request = SpeakRequest(
                text=line.text,
                # When a provider is forced (e.g. compare), the speaker's voice
                # id belongs to a different provider, so let this provider use
                # its own default.
                voice_id="" if voice_override else speaker.voice_id,
                model=speaker.model or vset.get("model"),
                base_url=vset.get("base_url"),
                api_key=vset.get("api_key"),
                timeout=float(vset.get("timeout") or 120),
            )
            if on_progress:
                on_progress(
                    f"  line {index + 1}/{len(lines)} "
                    f"[{speaker.name} → {provider_name}]"
                )
            result = provider.synthesize(request)
            assert isinstance(result, SpeakResult)
            clip = AudioSegment.from_file(
                io.BytesIO(result.data), format=result.response_format
            )
            combined += clip

            if index < len(lines) - 1:
                combined += AudioSegment.silent(
                    duration=random.randint(PAUSE_MIN_MS, PAUSE_MAX_MS)
                )

        buffer = io.BytesIO()
        combined.export(buffer, format="mp3")
        return buffer.getvalue()
    except FileNotFoundError as e:
        raise GenerationError(
            "Audio stitching needs ffmpeg on PATH. Install it (e.g. "
            "`brew install ffmpeg`, `apt install ffmpeg`, or `winget install ffmpeg`)."
        ) from e


def slugify(text: str, max_length: int = 48) -> str:
    """Filesystem-safe slug for a default output name."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or "episode"


def unique_path(path: Path) -> Path:
    """Avoid clobbering existing files by appending -2, -3, ..."""
    if not path.exists():
        return path
    for i in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{i}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not find a free filename near {path}")


def source_hash(text: str) -> str:
    """Short content hash for reproducibility sidecars."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def metadata_for(episode: Episode) -> dict[str, Any]:
    """Reproducibility sidecar for one saved episode."""
    return {
        "format": episode.format,
        "writer": episode.writer,
        "voices": episode.voices,
        "source_path": episode.source_path,
        "source_hash": source_hash(episode.source),
        "source_chars": len(episode.source),
        "lines": len(episode.lines),
        "transcript": script_text(episode.lines),
        "created": episode.created or datetime.now(timezone.utc).isoformat(),
        "app": "narra",
    }


def write_metadata(audio_path: Path, metadata: dict[str, Any]) -> Path:
    """Write a ``<episode>.json`` sidecar next to the audio; return its path."""
    sidecar = audio_path.with_suffix(audio_path.suffix + ".json")
    sidecar.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return sidecar


def save_episode(
    episode: Episode,
    out: str | None = None,
    out_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write one episode and its sidecar; return ``(audio, metadata)``.

    ``out`` is an exact file. Without it, the episode is named from the source
    stem and format and written into ``out_dir`` (the current directory by
    default). Existing files are never overwritten.
    """
    if not episode.audio:
        raise GenerationError("Episode has no audio.")

    if out:
        target = Path(out).expanduser()
        if target.parent != Path("."):
            target.parent.mkdir(parents=True, exist_ok=True)
        if not target.suffix:
            target = target.with_suffix(".mp3")
    else:
        base_dir = Path(out_dir).expanduser() if out_dir else Path(".")
        base_dir.mkdir(parents=True, exist_ok=True)
        stem = slugify(f"{Path(episode.source_path).stem} {episode.format}")
        target = unique_path(base_dir / f"{stem}.mp3")

    target.write_bytes(episode.audio)
    sidecar = write_metadata(target, metadata_for(episode))
    return target, sidecar
