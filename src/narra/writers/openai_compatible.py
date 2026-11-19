"""OpenAI-compatible writer: any ``/v1/chat/completions`` endpoint.

Asks for a JSON object, then normalises the result to ``list[DialogueLine]``.
Works with OpenAI, LM Studio, llama.cpp, and OpenRouter. A local server
usually needs no key; the compatible class therefore treats the key as optional
and only requires a ``base_url`` so a stray OPENAI_API_KEY never silently
routes a prompt to the wrong server.
"""

from __future__ import annotations

import os

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


class OpenAICompatibleWriter(Writer):
    name = "openai-compatible"
    default_model = "gpt-4o-mini"

    def write(self, request: ScriptRequest) -> ScriptResult:
        base_url = request.base_url or os.getenv("OPENAI_BASE_URL")
        if not base_url:
            raise WriterError(
                "The 'openai-compatible' writer needs a base_url (config "
                "writers.openai-compatible.base_url or OPENAI_BASE_URL)."
            )
        base_url = base_url.rstrip("/")
        api_key = request.api_key or os.getenv("OPENAI_API_KEY")
        model = request.model or self.default_model

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": render_prompt(request)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
        }

        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=request.timeout,
            )
        except requests.RequestException as e:
            raise WriterError(f"openai-compatible writer error: {e}") from e

        if not response.ok:
            raise WriterError(
                f"openai-compatible writer returned {response.status_code}: "
                f"{_error_detail(response)}"
            )

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise WriterError(f"openai-compatible writer: unexpected response: {e}") from e

        return ScriptResult(
            lines=parse_lines(content), provider=self.name, model=model
        )


def _error_detail(response: requests.Response) -> str:
    """Best-effort human-readable error from an OpenAI-style response."""
    try:
        body = response.json()
        return str(body.get("error", {}).get("message") or body)
    except ValueError:
        return response.text[:300]
