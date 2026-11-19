"""Speakers: who talks, their persona, and which voice speaks each line.

A :class:`Speaker` is one voice in the episode. ``voice`` is a reference of the
form ``{provider, voice_id, model}`` so two speakers in the same episode can be
voiced by two different providers (open-notebook's per-speaker override).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Speaker:
    """One speaker in an episode."""

    name: str
    persona: str = ""
    provider: str = "edge"
    voice_id: str = "en-US-AndrewNeural"
    model: str | None = None

    def voice_ref(self) -> dict[str, Any]:
        """The voice reference as a plain dict (for config / JSON sidecars)."""
        ref: dict[str, Any] = {"provider": self.provider, "voice_id": self.voice_id}
        if self.model:
            ref["model"] = self.model
        return ref


def _from_config(item: Any) -> Speaker:
    """Build a Speaker from a config mapping (dict) or a bare name (str)."""
    if isinstance(item, str):
        return Speaker(name=item)
    if not isinstance(item, dict):
        raise ValueError(f"Invalid speaker entry: {item!r}")
    name = str(item.get("name") or "").strip()
    if not name:
        raise ValueError(f"Speaker entry needs a name: {item!r}")
    voice = item.get("voice") or {}
    if isinstance(voice, str):
        voice = {"provider": voice}
    if not isinstance(voice, dict):
        raise ValueError(f"Speaker 'voice' must be a mapping: {item!r}")
    return Speaker(
        name=name,
        persona=str(item.get("persona") or ""),
        provider=str(voice.get("provider") or "edge"),
        voice_id=str(voice.get("voice_id") or "en-US-AndrewNeural"),
        model=voice.get("model"),
    )


DEFAULT_SPEAKERS: list[Speaker] = [
    Speaker(
        name="Alex",
        persona="Storyteller who sees the big picture.",
        provider="edge",
        voice_id="en-US-AndrewNeural",
    ),
    Speaker(
        name="Sam",
        persona="Curious skeptic who asks sharp follow-ups and translates jargon.",
        provider="edge",
        voice_id="en-US-AvaNeural",
    ),
]


def resolve_speakers(config_speakers: list[Any] | None) -> list[Speaker]:
    """Turn a config ``speakers`` list into Speaker objects.

    Falls back to the Alex/Sam defaults when nothing is configured.
    """
    if not config_speakers:
        return [Speaker(**vars(s)) for s in DEFAULT_SPEAKERS]
    speakers = [_from_config(item) for item in config_speakers]
    names = [s.name for s in speakers]
    if len(names) != len(set(names)):
        raise ValueError(f"Speaker names must be unique: {names}")
    return speakers
