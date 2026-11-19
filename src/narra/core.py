"""Core: turn a source document into a podcast episode on disk.

``generate`` is a skeleton in 0.0.1: it reads the source, resolves the format
and speakers, and then hands off to a writer + voice, which raise "not
implemented yet" until M1/M3. The save + JSON sidecar helpers are real.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from narra.formats import format_prompt, get_format
from narra.script import clean_lines, read_source, script_text
from narra.speakers import resolve_speakers
from narra.writers.base import DialogueLine, WriterError

_AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}


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
) -> Episode:
    """Generate one episode from a source file.

    Skeleton: reads the source and resolves everything, then calls the writer
    (which raises a clear "not implemented yet" error until M1). Voicing and
    stitching land in M1/M3.
    """
    chosen_format = format or str(settings.get("format") or "deep-dive")
    fmt = get_format(chosen_format)
    chosen_writer = writer or str(settings.get("writer") or "gemini")

    try:
        text = read_source(source_path)
    except Exception as e:
        raise GenerationError(str(e)) from e

    from narra.script import outline_to_dialogue

    try:
        lines = outline_to_dialogue(text, format_prompt(fmt.key), chosen_writer, settings)
    except WriterError as e:
        raise GenerationError(str(e)) from e

    return Episode(
        lines=clean_lines(lines),
        audio=b"",
        source=text,
        source_path=source_path,
        format=fmt.key,
        writer=chosen_writer,
        voices=[s.voice_ref() for s in resolve_speakers(settings.get("speakers"))],
        created=datetime.now(timezone.utc).isoformat(),
    )


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
        raise GenerationError(
            "Episode has no audio yet — voicing is not implemented in the "
            "0.0.1 skeleton. See SPEC.md §10 M1."
        )

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
