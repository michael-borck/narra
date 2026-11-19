"""Gemini writer: structured script output via ``google-genai``.

Uses a typed ``response_schema`` so Gemini returns JSON we can trust, then
normalises it to ``list[DialogueLine]``.
"""

from __future__ import annotations

import json
import os

from narra.writers.base import (
    SYSTEM_PROMPT,
    ScriptRequest,
    ScriptResult,
    Writer,
    WriterError,
    parse_lines,
    render_prompt,
)


class GeminiWriter(Writer):
    name = "gemini"
    default_model = "gemini-flash-latest"

    def write(self, request: ScriptRequest) -> ScriptResult:
        try:
            from google import genai
            from google.genai import types
            from pydantic import BaseModel
        except ImportError as e:
            raise WriterError(
                "The 'gemini' writer needs google-genai. Install it with:\n"
                "  pip install \"narra[gemini]\""
            ) from e

        api_key = (
            request.api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        if not api_key:
            raise WriterError(
                "The 'gemini' writer needs an API key (config writers.gemini.api_key, "
                "GEMINI_API_KEY, or GOOGLE_API_KEY)."
            )
        model = request.model or self.default_model

        class _Line(BaseModel):
            speaker: str
            text: str

        class _Script(BaseModel):
            podcast_script: list[_Line]

        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(api_version="v1beta"),
            )
            response = client.models.generate_content(
                model=model,
                contents=f"{SYSTEM_PROMPT}\n\n{render_prompt(request)}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_Script,
                ),
            )
            text = response.text
            if not text:
                raise WriterError("gemini writer returned an empty response")
            payload = json.loads(text)
        except WriterError:
            raise
        except Exception as e:
            raise WriterError(f"gemini writer error: {e}") from e

        lines = parse_lines(payload)
        return ScriptResult(lines=lines, provider=self.name, model=model)
