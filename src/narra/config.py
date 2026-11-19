"""Layered configuration for Narra.

Layers, later wins:

1. Built-in defaults
2. ``~/.narra.yaml``  — your providers + keys, set once
3. ``./narra.yaml``   — per-directory overrides (or an explicit ``--config`` path)
4. CLI flags         — applied by the CLI on top of the loaded config

Secrets are referenced as ``${VAR}`` and expanded from the environment, so no
plaintext keys need to live in config files.
"""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""


DEFAULT_CONFIG: dict[str, Any] = {
    "writer": "gemini",
    "voice": "edge",
    "format": "deep-dive",
    "model": None,
    "voice_model": None,
    "timeout": 300,
    "writers": {},
    "voices": {},
    "speakers": [],
    "serve": {
        "host": "127.0.0.1",
        "port": 5372,
        "password": None,
        "out_dir": "~/Podcasts/Narra",
    },
}

_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env_vars(value: Any) -> Any:
    """Recursively expand ``${VAR}`` references in configuration values."""
    if isinstance(value, str):
        return _ENV_VAR_RE.sub(lambda m: os.getenv(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    return value


def _first_existing(*candidates: Path) -> Path | None:
    for path in candidates:
        if path.exists():
            return path
    return None


def find_home_config() -> Path | None:
    """The user-level config (~/.narra.yaml) — providers + keys, set once."""
    return _first_existing(
        Path.home() / ".narra.yaml",
        Path.home() / ".narra.yml",
    )


def find_project_config() -> Path | None:
    """The directory-level config (./narra.yaml)."""
    return _first_existing(
        Path("./narra.yaml"),
        Path("./narra.yml"),
    )


def _read_config_file(config_file: Path) -> dict[str, Any] | None:
    try:
        with open(config_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML in {config_file}: {e}") from e
    except OSError as e:
        raise ConfigurationError(f"Error reading {config_file}: {e}") from e
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigurationError(
            f"Config file {config_file} must contain a YAML mapping"
        )
    return data


def merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two config dicts (override wins)."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load configuration by layering defaults, home, and project files.

    An explicit ``config_path`` replaces the auto-discovered ./narra.yaml but
    still sits on top of ~/.narra.yaml.
    """
    config = copy.deepcopy(DEFAULT_CONFIG)

    sources: list[Path] = []
    if home_config := find_home_config():
        sources.append(home_config)
    if config_path:
        explicit = Path(config_path)
        if not explicit.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")
        sources.append(explicit)
    elif project_config := find_project_config():
        sources.append(project_config)

    for source in sources:
        file_config = _read_config_file(source)
        if file_config:
            config = merge_configs(config, file_config)

    return expand_env_vars(config)


def writer_settings(config: dict[str, Any], writer: str | None = None) -> dict[str, Any]:
    """Effective settings for one writer, merged from the top level and its block."""
    name = writer or str(config.get("writer") or "gemini")
    settings = {k: v for k, v in config.items() if k not in ("writers", "voices", "speakers")}
    override = (config.get("writers") or {}).get(name)
    if isinstance(override, dict):
        settings = merge_configs(settings, override)
    settings["writer"] = name
    return settings


def voice_settings(config: dict[str, Any], voice: str | None = None) -> dict[str, Any]:
    """Effective settings for one voice provider, merged from its block."""
    name = voice or str(config.get("voice") or "edge")
    settings: dict[str, Any] = {}
    override = (config.get("voices") or {}).get(name)
    if isinstance(override, dict):
        settings = merge_configs(settings, override)
    settings["voice"] = name
    return settings


EXAMPLE_CONFIG = """\
# Narra configuration
#
# Layered, later wins:
#   1. built-in defaults
#   2. ~/.narra.yaml   (personal: providers, API keys — set once)
#   3. ./narra.yaml    (per-directory overrides; or pass --config FILE)
#   4. CLI flags       (e.g. --writer, --voice, --format)
#
# Secrets: reference environment variables as ${VAR} — no plaintext keys.

writer: gemini                 # gemini | openai-compatible | ollama
voice: edge                    # edge | openai-compatible | gemini | piper | kokoro
format: deep-dive              # deep-dive | brief | critique | debate | <custom>

writers:
  gemini:
    model: gemini-flash-latest
    # api_key: "${GEMINI_API_KEY}"   # defaults to the env var anyway

  openai-compatible:           # LocalAI, LM Studio, llama.cpp, OpenRouter, OpenAI
    base_url: https://api.openai.com/v1
    model: gpt-4o-mini
    # api_key: "${OPENAI_API_KEY}"   # optional for local servers

  ollama:                      # local, no key
    base_url: http://127.0.0.1:11434
    model: qwen3.5:4b

voices:
  edge: {}                     # free, no key; default

  openai-compatible:           # OpenAI standard /v1/audio/speech
    base_url: https://api.openai.com/v1
    model: gpt-4o-mini-tts
    # api_key: "${OPENAI_API_KEY}"

  gemini:                      # native TTS
    model: gemini-3.8-flash-tts
    # api_key: "${GEMINI_API_KEY}"

  piper:                       # local CPU
    voice: en_GB-alan-low

  kokoro:                      # local CPU
    voice: bm_george

# 1–N speakers. Each may point at a different voice provider.
speakers:
  - name: Alex
    persona: Storyteller who sees the big picture.
    voice: { provider: edge, voice_id: en-US-AndrewNeural }
  - name: Sam
    persona: Curious skeptic who asks sharp follow-ups.
    voice: { provider: edge, voice_id: en-US-AvaNeural }

serve:
  host: 127.0.0.1
  port: 5372                  # "NARR" on a phone keypad
  # password: "${NARRA_SERVE_PASSWORD}"
  out_dir: ~/Podcasts/Narra
"""


def save_example_config(path: str = "narra.yaml") -> Path:
    """Write an example configuration file and return its path."""
    target = Path(path)
    if target.exists():
        raise ConfigurationError(f"Refusing to overwrite existing {target}")
    target.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    return target
