"""Format registry: a name -> the prompt fragment that shapes a script.

A format is either a shipped preset or a custom briefing (free text). The
writer rules are appended to every format so a cold open, concrete facts, and
no stage directions are enforced consistently.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Format:
    """One script format: a key, a label, and the prompt fragment."""

    key: str
    label: str
    instruction: str


FORMATS: dict[str, Format] = {
    "deep-dive": Format(
        key="deep-dive",
        label="Deep dive",
        instruction=(
            "Write an 18-24 line lively two-host Deep Dive between Alex (storyteller "
            "who sees the big picture) and Sam (curious skeptic who asks sharp "
            "follow-ups and translates jargon). Mix longer explanations with short "
            "3-6 word reactions. Connect non-obvious dots in the source."
        ),
    ),
    "brief": Format(
        key="brief",
        label="Brief",
        instruction=(
            "Write a tight, single-host Brief delivered ONLY by Alex (6-8 short "
            "lines, under 90 seconds spoken). Every single line MUST have speaker "
            "set to 'Alex'. Lead with the core headline, hit the 3 sharpest facts, "
            "and close with one clear takeaway."
        ),
    ),
    "critique": Format(
        key="critique",
        label="Critique",
        instruction=(
            "Write a 16-20 line constructive Critique between Alex and Sam acting as "
            "candid domain reviewers. Highlight what is genuinely strong, then "
            "directly dissect gaps, risks, missing evidence, or areas that could be "
            "tightened."
        ),
    ),
    "debate": Format(
        key="debate",
        label="Debate",
        instruction=(
            "Write an 18-22 line structured Debate. Alex argues the optimistic/pro "
            "case from the source; Sam plays the tough skeptic highlighting "
            "trade-offs, blind spots, and counterarguments. Do not let them agree "
            "prematurely."
        ),
    ),
}

#: Appended to every format so the writer follows the same rules.
WRITER_RULES = (
    "Rules:\n"
    "- Start with a cold open (NO \"Welcome back to the show\" or generic greetings).\n"
    "- Cite concrete facts, numbers, or names from the source text.\n"
    "- Avoid AI clichés (\"delve into\", \"game-changer\", \"tapestry\", "
    "\"at the end of the day\").\n"
    "- Keep lines conversational with no stage directions or sound effects."
)


def get_format(name: str | None) -> Format:
    """Resolve a format by key, or treat the text itself as a custom briefing.

    An unknown key is not an error: it is used verbatim as a custom briefing so
    users can pass their own episode profile without editing config.
    """
    key = (name or "deep-dive").strip()
    if key in FORMATS:
        return FORMATS[key]
    lowered = key.lower()
    if lowered in FORMATS:
        return FORMATS[lowered]
    return Format(key=key, label=key[:32], instruction=key)


def format_options() -> list[dict[str, str]]:
    """Format choices for the CLI help and web UI."""
    return [{"key": f.key, "label": f.label} for f in FORMATS.values()]


def format_prompt(name: str | None) -> str:
    """The full prompt fragment for a format: instruction plus shared rules."""
    fmt = get_format(name)
    return f"{fmt.instruction}\n\n{WRITER_RULES}"
