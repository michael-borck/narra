"""OpenAI-compatible writer: any ``/v1/chat/completions`` endpoint.

Skeleton stub. The intended shape: POST ``{base_url}/chat/completions`` with
``response_format={"type": "json_object"}`` (or a strict schema where the server
supports it), parse the JSON into dialogue lines, and return a ``ScriptResult``.
Works with OpenAI, LM Studio, llama.cpp, and OpenRouter.
"""

from __future__ import annotations

from narra.writers.base import ScriptRequest, ScriptResult, Writer, WriterError


class OpenAICompatibleWriter(Writer):
    name = "openai-compatible"
    default_model = "gpt-4o-mini"

    def write(self, request: ScriptRequest) -> ScriptResult:
        # TODO(M1): requests.post(f"{base_url}/chat/completions",
        #   headers={Authorization: Bearer}, json={model, messages, response_format}).
        raise WriterError(
            "The 'openai-compatible' writer is not implemented yet "
            "(Narra 0.0.1 skeleton). See SPEC.md §10 M1."
        )
