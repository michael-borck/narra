"""Writer registry: name -> thin script-writing client."""

from __future__ import annotations

from narra.writers.base import (
    DialogueLine,
    ScriptRequest,
    ScriptResult,
    Writer,
    WriterError,
)
from narra.writers.gemini import GeminiWriter
from narra.writers.ollama import OllamaWriter
from narra.writers.openai_compatible import OpenAICompatibleWriter

__all__ = [
    "DialogueLine",
    "ScriptRequest",
    "ScriptResult",
    "Writer",
    "WriterError",
    "WRITERS",
    "get_writer",
    "GeminiWriter",
    "OpenAICompatibleWriter",
    "OllamaWriter",
]

WRITERS: dict[str, type[Writer]] = {
    "gemini": GeminiWriter,
    "openai-compatible": OpenAICompatibleWriter,
    "ollama": OllamaWriter,
}


def get_writer(name: str) -> Writer:
    """Instantiate a writer by name."""
    try:
        writer_cls = WRITERS[name.lower()]
    except KeyError:
        known = ", ".join(sorted(set(WRITERS)))
        raise WriterError(f"Unknown writer '{name}'. Choose from: {known}") from None
    return writer_cls()
