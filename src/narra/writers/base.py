"""Writer abstraction: a source document goes in, a script comes out.

Writers are thin clients over one LLM backend each. They raise WriterError on
any failure — Narra fails loudly rather than degrading to a canned script.
"""

from __future__ import annotations

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
