"""Skeleton tests: packaging, registries, config, and clean failure paths."""

from __future__ import annotations

import pytest

import narra
from narra import core, formats, speakers
from narra.config import (
    ConfigurationError,
    load_config,
    merge_configs,
    save_example_config,
)
from narra.script import SourceError, read_source
from narra.tts import VOICES, get_voice
from narra.tts.base import VoiceError
from narra.writers import WRITERS, get_writer
from narra.writers.base import WriterError


def test_version():
    assert narra.__version__ == "0.0.1"


def test_formats_registry():
    keys = {f["key"] for f in formats.format_options()}
    assert {"deep-dive", "brief", "critique", "debate"} <= keys


def test_custom_format_is_verbatim():
    fmt = formats.get_format("narrate a 5-part history of coffee")
    assert "coffee" in fmt.instruction
    assert formats.WRITER_RULES in formats.format_prompt(fmt.key)


def test_speaker_defaults():
    resolved = speakers.resolve_speakers(None)
    assert [s.name for s in resolved] == ["Alex", "Sam"]
    assert resolved[0].voice_id == "en-US-AndrewNeural"


def test_speaker_from_config():
    resolved = speakers.resolve_speakers(
        [{"name": "Ana", "voice": {"provider": "kokoro", "voice_id": "bm_george"}}]
    )
    assert resolved[0].name == "Ana"
    assert resolved[0].provider == "kokoro"


def test_duplicate_speakers_rejected():
    with pytest.raises(ValueError):
        speakers.resolve_speakers([{"name": "A"}, {"name": "A"}])


def test_config_merge():
    base = {"a": 1, "nested": {"x": 1}}
    merged = merge_configs(base, {"nested": {"y": 2}, "b": 3})
    assert merged == {"a": 1, "nested": {"x": 1, "y": 2}, "b": 3}


def test_config_example_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = save_example_config("narra.yaml")
    assert path.exists()
    settings = load_config(str(path))
    assert settings["writer"] == "gemini"
    assert settings["serve"]["port"] == 5372
    with pytest.raises(ConfigurationError):
        save_example_config("narra.yaml")


def test_writer_registry():
    assert set(WRITERS) == {"gemini", "openai-compatible", "ollama"}
    assert isinstance(get_writer("gemini"), WRITERS["gemini"])
    with pytest.raises(WriterError):
        get_writer("nope")


def test_voice_registry():
    assert {"edge", "openai", "openai-compatible", "gemini", "piper", "kokoro"} <= set(
        VOICES
    )
    assert isinstance(get_voice("edge"), VOICES["edge"])
    with pytest.raises(VoiceError):
        get_voice("nope")


def test_read_source_txt(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hello world", encoding="utf-8")
    assert read_source(str(src)) == "hello world"
    with pytest.raises(SourceError):
        read_source(str(tmp_path / "missing.txt"))


def test_generate_fails_cleanly_on_stub_writer(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("Some source text about a topic.", encoding="utf-8")
    settings = load_config()
    with pytest.raises(core.GenerationError) as exc:
        core.generate(str(src), settings)
    assert "not implemented" in str(exc.value).lower()


def test_slugify():
    assert core.slugify("Hello, World! Episode 1") == "hello-world-episode-1"
    assert core.slugify("***") == "episode"


def test_save_without_audio_raises(tmp_path):
    ep = core.Episode(
        lines=[], audio=b"", source="x", source_path="a.txt",
        format="brief", writer="gemini",
    )
    with pytest.raises(core.GenerationError):
        core.save_episode(ep, out=str(tmp_path / "x.mp3"))


def test_serve_app():
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from narra.serve import create_app

    client = fastapi_testclient.TestClient(create_app({"writer": "gemini"}))
    assert client.get("/api/health").json()["ok"] is True
    assert "Narra" in client.get("/").text
