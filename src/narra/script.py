"""Source reading and script assembly.

``read_source`` is real (txt + pdf). The outline → expand → dialogue
generation is a skeleton: it will call a writer and return dialogue lines.
"""

from __future__ import annotations

import re
from pathlib import Path

from narra.writers.base import DialogueLine


class SourceError(Exception):
    """Raised when a source file cannot be read."""


def read_source(file_path: str) -> str:
    """Read a .pdf or text file into plain text.

    PDFs are read with pypdf (imported lazily so the core CLI has no hard
    dependency on it until a PDF is actually passed).
    """
    path = Path(file_path)
    if not path.exists():
        raise SourceError(f"Source file not found: {file_path}")

    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:  # pragma: no cover - depends on environment
            raise SourceError(
                "Reading PDFs needs pypdf. Install it with: pip install pypdf"
            ) from e
        try:
            reader = PdfReader(str(path))
        except Exception as e:
            raise SourceError(f"Could not read PDF {file_path}: {e}") from e
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise SourceError(f"Could not read {file_path}: {e}") from e


def clean_lines(lines: list[DialogueLine]) -> list[DialogueLine]:
    """Drop empty lines and trim whitespace; keep order."""
    cleaned: list[DialogueLine] = []
    for line in lines:
        text = line.text.strip()
        if text and any(c.isalnum() for c in text):
            cleaned.append(DialogueLine(speaker=line.speaker.strip(), text=text))
    return cleaned


def script_text(lines: list[DialogueLine]) -> str:
    """Flatten dialogue into a single spoken transcript."""
    return "\n\n".join(line.text.strip() for line in lines)


def outline_to_dialogue(
    source_text: str,
    format_instruction: str,
    writer_name: str,
    settings: dict[str, object],
) -> list[DialogueLine]:
    """Generate dialogue from a source using the chosen writer.

    Skeleton: resolves the writer and delegates. The writer raises a clear
    "not implemented yet" error until M1 lands.
    """
    from narra.config import writer_settings
    from narra.speakers import resolve_speakers
    from narra.writers import get_writer
    from narra.writers.base import ScriptRequest

    effective = writer_settings(settings, writer_name)  # type: ignore[arg-type]
    writer = get_writer(writer_name)
    request = ScriptRequest(
        source_text=source_text[:50000],
        format_instruction=format_instruction,
        speakers=resolve_speakers(effective.get("speakers")),  # type: ignore[arg-type]
        model=effective.get("model"),
        base_url=effective.get("base_url"),
        api_key=effective.get("api_key"),
        timeout=float(effective.get("timeout") or 300),
    )
    result = writer.write(request)
    return clean_lines(result.lines)


# Compile a simple sentence-ish splitter for later sentence-level timing use.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    """Split text into sentences (best-effort, for timing/SSML later)."""
    return [s for s in _SENTENCE_RE.split(text.strip()) if s]
