import argparse
import asyncio
import io
import os
import random
import tempfile
from pathlib import Path
from pydantic import BaseModel
from google import genai
from google.genai import types
from pypdf import PdfReader
import edge_tts
from pydub import AudioSegment

# --- 1. Schema & Style Prompts ---

class DialogueLine(BaseModel):
    speaker: str  # "Alex" or "Sam"
    text: str

class PodcastOutput(BaseModel):
    podcast_script: list[DialogueLine]

STYLE_PROMPTS = {
    "deep-dive": (
        "Write an 18-24 line lively two-host Deep Dive between Alex (storyteller who sees the big picture) "
        "and Sam (curious skeptic who asks sharp follow-ups and translates jargon). "
        "Mix longer explanations with short 3-6 word reactions. Connect non-obvious dots in the source."
    ),
    "brief": (
        "Write a tight, single-host Brief delivered ONLY by Alex (6-8 short lines, under 90 seconds spoken). "
        "Every single line MUST have speaker set to 'Alex'. "
        "Lead with the core headline, hit the 3 sharpest facts, and close with one clear takeaway."
    ),
    "critique": (
        "Write a 16-20 line constructive Critique between Alex and Sam acting as candid domain reviewers. "
        "Highlight what is genuinely strong, then directly dissect gaps, risks, missing evidence, "
        "or areas that could be tightened."
    ),
    "debate": (
        "Write an 18-22 line structured Debate. Alex argues the optimistic/pro case from the source; "
        "Sam plays the tough skeptic highlighting trade-offs, blind spots, and counterarguments. "
        "Do not let them agree prematurely."
    ),
}


# --- 2. Extract Text ---

def read_source(file_path: str) -> str:
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8")


# --- 3. Generate Podcast Script with Gemini ---

def generate_script(
    client: genai.Client, source_text: str, model: str, style: str
) -> list[DialogueLine]:
    prompt = f"""
    You are creating a Gemini Notebook-style audio overview from the source text below.

    Style ({style}):
    {STYLE_PROMPTS[style]}

    Rules:
    - Start with a cold open (NO "Welcome back to the show" or generic greetings).
    - Cite concrete facts, numbers, or names from the source text.
    - Avoid AI clichés ("delve into", "game-changer", "tapestry", "at the end of the day").
    - Keep lines conversational with no stage directions or sound effects.

    SOURCE TEXT:
    {source_text[:50000]}
    """

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PodcastOutput,
        ),
    )
    return PodcastOutput.model_validate_json(response.text).podcast_script


# --- 4A. Synthesize with Edge TTS ---

EDGE_VOICES = {
    "Alex": "en-US-AndrewNeural",  # Male
    "Sam": "en-US-AvaNeural",      # Female
}

async def build_podcast_edge(script: list[DialogueLine], output_path: str):
    valid_lines = [
        line for line in script
        if line.text.strip() and any(c.isalnum() for c in line.text)
    ]
    unique_speakers = {line.speaker for line in valid_lines}

    single_voice = None
    if len(unique_speakers) == 1:
        gender, single_voice = random.choice([
            ("male", "en-US-AndrewNeural"),
            ("female", "en-US-AvaNeural"),
        ])
        print(f"Single speaker detected -> coin flip picked {gender} voice ({single_voice})")

    combined = AudioSegment.empty()

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, line in enumerate(valid_lines):
            text = line.text.strip()
            voice = single_voice or EDGE_VOICES.get(line.speaker, "en-US-AndrewNeural")
            clip_path = os.path.join(tmpdir, f"line_{i}.mp3")

            for attempt in range(3):
                try:
                    communicate = edge_tts.Communicate(text, voice)
                    await communicate.save(clip_path)
                    break
                except edge_tts.exceptions.NoAudioReceived:
                    if attempt == 2:
                        print(f"Failed on line {i} ({voice}): {text!r}")
                        raise
                    await asyncio.sleep(1.5)

            pause_ms = random.randint(180, 420)
            combined += AudioSegment.from_mp3(clip_path) + AudioSegment.silent(duration=pause_ms)

    combined.export(output_path, format="mp3")
    print(f"Saved Edge TTS podcast to {output_path}")


# --- 4B. Synthesize with Gemini Native TTS ---

def build_podcast_gemini(
    client: genai.Client,
    script: list[DialogueLine],
    output_path: str,
    tts_model: str,
):
    valid_lines = [
        line for line in script
        if line.text.strip() and any(c.isalnum() for c in line.text)
    ]
    unique_speakers = {line.speaker for line in valid_lines}

    if len(unique_speakers) == 1:
        gender, chosen_voice = random.choice([
            ("male", "Fenrir"),
            ("female", "Leda"),
        ])
        print(f"Single speaker detected -> coin flip picked {gender} voice ({chosen_voice})")

        contents = "\n\n".join(line.text.strip() for line in valid_lines)
        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=chosen_voice
                )
            )
        )
    else:
        parts = [