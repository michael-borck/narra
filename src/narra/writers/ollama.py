"""Ollama writer: a local chat model, no key.

Uses Ollama's native ``/api/chat`` with ``format`` set to a JSON schema hint so
the model replies with structured JSON. ``think`` is disabled where supported.
"""

from __future__ import annotations

import json

import requests

from narra.writers.base import (
    SYSTEM_PROMPT,
    ScriptRequest,
    ScriptResult,
    Writer,
    WriterError,
    parse_lines,
    render_prompt,
)

#: A minimal JSON schema hint for /api/chat "format".
_LINE_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"speaker": {"type": "string"}, "text": {"type": "string"}},
                "required": ["speaker", "text"],
            },
        }
    },
    "required": ["lines"],
}


class OllamaWriter(Writer):
    name = "ollama"
    default_model = "qwen3.5:4b"
    default_base_url = "http://127.0.0.1:11434"

    def write(self, request: ScriptRequest) -> ScriptResult:
        base_url = (request.base_url or self.default_base_url).rstrip("/")
        model = request.model or self.default_model
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": render_prompt(request)},
            ],
            "stream": False,
            "format": _LINE_SCHEMA,
            "options": {"temperature": 0.7},
        }

        try:
            response = requests.post(
                f"{base_url}/api/chat", json=payload, timeout=request.timeout
            )
        except requests.RequestException as e:
            raise WriterError(
                f"Could not reach Ollama at {base_url}: {e}. Is it running?"
            ) from e

        if not response.ok:
            raise WriterError(
                f"ollama writer returned {response.status_code}: {response.text[:300]}"
            )

        try:
            content = response.json()["message"]["content"]
        except (KeyError, ValueError) as e:
            raise WriterError(f"ollama writer: unexpected response: {e}") from e

        try:
            data = json.loads(content) if isinstance(content, str) else content
        except ValueError as e:
            raise WriterError(f"ollama writer: model did not return JSON: {e}") from e

        return ScriptResult(lines=parse_lines(data), provider=self.name, model=model)
