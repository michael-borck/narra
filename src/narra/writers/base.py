"""Writer abstraction: a source document goes in, a script comes out.

Writers are thin clients over one LLM backend each. They raise WriterError on
any failure — Narra fails loudly rather than degrading to a canned script.

The prompt and JSON parsing are shared here so every backend produces the same
``list[DialogueLine]`` shape.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from narra.speakers import Speaker


class WriterError(Exception):
    """Raised when a writer cannot produce a script."""


@dataclass
class DialogueLine:
    """One spoken line in the episode."""

    speaker: str
    text: str


@dataclass
class ScriptRequest:
    """Everything a writer needs for one script."""

    source_text: str
    format_instruction: str
    speakers: list[Speaker] = field(default_factory=list)
    max_chars: int = 50000
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout: float = 300.0


@dataclass
class ScriptResult:
    """A written script plus whatever the backend reported about it."""

    lines: list[DialogueLine]
    provider: str
    model: str | None = None


SYSTEM_PROMPT = (
    "You are a podcast scriptwriter. You turn source material into a lively, "
    "conversational podcast script. You reply with strict JSON only."
)

#: Keys a backend might use for the list of lines, in priority order.
_LINE_KEYS = ("lines", "podcast_script", "script", "dialogue", "turns")


def render_prompt(request: ScriptRequest) -> str:
    """Compose the user prompt shared by every writer backend."""
    names = ", ".join(s.name for s in request.speakers) or "Alex, Sam"
    parts = [
        "Write the podcast script now.",
        f"Format:\n{request.format_instruction}",
        f"Speakers (use these exact names for the 'speaker' field): {names}.",
    ]
    personas = "\n".join(
        f"- {s.name}: {s.persona}" for s in request.speakers if s.persona
    )
    if personas:
        parts.append(f"Speaker notes:\n{personas}")
    parts.append("SOURCE TEXT:\n" + request.source_text[: request.max_chars])
    return "\n\n".join(parts)


def parse_lines(data: Any) -> list[DialogueLine]:
    """Parse a backend's JSON into dialogue lines.

    Accepts a bare list, or a mapping with one of the known keys
    (``lines`` / ``podcast_script`` / ``script`` / ...), and both dict and
    ``[speaker, text]`` pair items. Raises WriterError if nothing usable is
    found.
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError as e:
            raise WriterError(f"Writer returned invalid JSON: {e}") from e

    items: Any = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in _LINE_KEYS:
            if isinstance(data.get(key), list):
                items = data[key]
                break

    if not items:
        raise WriterError("Writer returned no dialogue lines.")

    lines: list[DialogueLine] = []
    for item in items:
        speaker = ""
        text = ""
        if isinstance(item, dict):
            speaker = str(item.get("speaker") or item.get("role") or "Alex").strip()
            text = str(item.get("text") or item.get("line") or "").strip()
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            speaker = str(item[0]).strip()
            text = str(item[1]).strip()
        if text:
            lines.append(DialogueLine(speaker=speaker, text=text))

    if not lines:
        raise WriterError("Writer returned no usable dialogue lines.")
    return lines


class Writer(ABC):
    """One backend: turn a ScriptRequest into dialogue lines."""

    name: str = "base"

    @abstractmethod
    def write(self, request: ScriptRequest) -> ScriptResult:
        """Write a script. Raises WriterError on failure."""
        raise NotImplementedError

    def unsupported(self, request: ScriptRequest) -> list[tuple[str, Any]]:
        """(label, value) pairs of request fields this backend ignores."""
        return []
