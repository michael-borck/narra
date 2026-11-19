"""Ollama writer: a local chat model, no key.

Skeleton stub. The intended shape: POST ``{base_url}/api/chat`` (or the
OpenAI-compatible ``/v1/chat/completions``) with a JSON-format instruction, and
return a ``ScriptResult``. Default model resolved from ``/api/tags``.
"""

from __future__ import annotations

from narra.writers.base import ScriptRequest, ScriptResult, Writer, WriterError


class OllamaWriter(Writer):
    name = "ollama"
    default_model = "qwen3.5:4b"

    def write(self, request: ScriptRequest) -> ScriptResult:
        # TODO(M1): POST {base_url}/api/chat, think=false, format=JSON schema.
        raise WriterError(
            "The 'ollama' writer is not implemented yet (Narra 0.0.1 skeleton). "
            "See SPEC.md §10 M1."
        )
