"""Gemini writer: structured script output via ``google-genai``.

Skeleton stub — the interface is fixed, the body lands in M1. The intended
shape: pass ``ScriptRequest`` to ``client.models.generate_content`` with a typed
``response_schema`` of ``list[DialogueLine]`` and return a ``ScriptResult``.
"""

from __future__ import annotations

from narra.writers.base import ScriptRequest, ScriptResult, Writer, WriterError


class GeminiWriter(Writer):
    name = "gemini"
    default_model = "gemini-3.5-flash"

    def write(self, request: ScriptRequest) -> ScriptResult:
        # TODO(M1): build the client from request.api_key, call
        # client.models.generate_content(model=..., contents=prompt,
        #   config=GenerateContentConfig(response_mime_type="application/json",
        #   response_schema=list[DialogueLine])), validate, return lines.
        raise WriterError(
            "The 'gemini' writer is not implemented yet (Narra 0.0.1 skeleton). "
            "See SPEC.md §10 M1."
        )
