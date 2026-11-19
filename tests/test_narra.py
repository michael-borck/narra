"""Skeleton tests: packaging, registries, config, and clean failure paths."""

from __future__ import annotations

import re
import shutil

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
    assert re.match(r"^\d+\.\d+\.\d+", narra.__version__)


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


def test_generate_fails_cleanly_without_key(tmp_path, monkeypatch):
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    src = tmp_path / "a.txt"
    src.write_text("Some source text about a topic.", encoding="utf-8")
    settings = load_config()
    with pytest.raises(core.GenerationError) as exc:
        core.generate(str(src), settings, writer="gemini")
    assert "api key" in str(exc.value).lower()


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


# --- M2: web UI ------------------------------------------------------------


def _client(config=None, token=None):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from narra.serve import create_app

    return fastapi_testclient.TestClient(create_app(config or {}, token=token))


def test_config_lists_formats_and_speakers():
    client = _client({"writer": "gemini", "voice": "edge"})
    cfg = client.get("/api/config").json()
    assert {f["key"] for f in cfg["formats"]} >= {"deep-dive", "brief", "critique", "debate"}
    assert cfg["speakers"][0]["name"] == "Alex"
    assert "gemini" in cfg["writers"]


def test_script_endpoint(monkeypatch):
    from narra.writers.base import DialogueLine

    monkeypatch.setattr(
        "narra.serve.outline_to_dialogue",
        lambda *a, **k: [DialogueLine("Alex", "Hello"), DialogueLine("Sam", "Hi")],
    )
    client = _client()
    res = client.post("/api/script", json={"source_text": "src", "format": "brief"})
    assert res.status_code == 200
    body = res.json()
    assert [ln["speaker"] for ln in body["lines"]] == ["Alex", "Sam"]


def test_script_endpoint_surfaces_writer_error(monkeypatch):
    from narra.writers.base import WriterError

    def boom(*a, **k):
        raise WriterError("no key")

    monkeypatch.setattr("narra.serve.outline_to_dialogue", boom)
    client = _client()
    res = client.post("/api/script", json={"source_text": "src"})
    assert res.status_code == 400
    assert "no key" in res.json()["detail"]


def test_audio_creates_gallery_episode(monkeypatch):
    monkeypatch.setattr("narra.core.voice_lines", lambda *a, **k: b"ID3fakeaudio")
    client = _client()
    res = client.post(
        "/api/audio",
        json={"lines": [{"speaker": "Alex", "text": "Hello"}], "format": "brief"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["audio"]
    ep_id = data["id"]

    listing = client.get("/api/episodes").json()["episodes"]
    assert any(e["id"] == ep_id for e in listing)

    audio = client.get(f"/api/episodes/{ep_id}/audio")
    assert audio.status_code == 200
    assert audio.content == b"ID3fakeaudio"

    assert client.delete(f"/api/episodes/{ep_id}").status_code == 200
    assert client.get(f"/api/episodes/{ep_id}/audio").status_code == 404


def test_audio_rejects_empty(monkeypatch):
    client = _client()
    res = client.post("/api/audio", json={"lines": [{"speaker": "Alex", "text": "  "}]})
    assert res.status_code == 400


def test_save_endpoint(monkeypatch, tmp_path):
    from narra import core

    monkeypatch.setattr("narra.core.voice_lines", lambda *a, **k: b"ID3x")
    target = tmp_path / "ep.mp3"
    target.write_bytes(b"ID3x")

    def fake_save(episode, out=None, out_dir=None):
        return target, target.with_suffix(".mp3.json")

    monkeypatch.setattr(core, "save_episode", fake_save)
    client = _client({"serve": {"out_dir": str(tmp_path)}})
    ep_id = client.post(
        "/api/audio", json={"lines": [{"speaker": "Alex", "text": "Hi"}]}
    ).json()["id"]
    res = client.post(f"/api/episodes/{ep_id}/save")
    assert res.status_code == 200
    assert res.json()["path"] == str(target)


def test_extract_txt():
    client = _client()
    res = client.post(
        "/api/extract", files={"file": ("a.txt", b"hello world", "text/plain")}
    )
    assert res.status_code == 200
    assert res.json()["text"] == "hello world"


def test_token_guard():
    client = _client({}, token="s3cret")
    assert client.get("/api/config").status_code == 401
    assert client.get("/api/config", headers={"X-Narra-Token": "s3cret"}).status_code == 200
    assert client.get("/api/config?token=s3cret").status_code == 200


# --- M1: writer helpers ------------------------------------------------------


def test_parse_lines_accepts_shapes():
    from narra.writers.base import parse_lines

    as_list = parse_lines([{"speaker": "Alex", "text": "Hi"}])
    assert as_list[0].speaker == "Alex"

    as_script = parse_lines({"podcast_script": [{"speaker": "Sam", "text": "Yo"}]})
    assert as_script[0].text == "Yo"

    as_pairs = parse_lines([["Alex", "Pair form"]])
    assert as_pairs[0].text == "Pair form"


def test_parse_lines_rejects_empty():
    from narra.writers.base import WriterError, parse_lines

    with pytest.raises(WriterError):
        parse_lines({"lines": []})
    with pytest.raises(WriterError):
        parse_lines("not json")


def test_render_prompt_includes_source_and_speakers():
    from narra.speakers import Speaker
    from narra.writers.base import ScriptRequest, render_prompt

    request = ScriptRequest(
        source_text="The source body.",
        format_instruction="Be brief.",
        speakers=[Speaker(name="Ana", persona="Curious.")],
    )
    prompt = render_prompt(request)
    assert "The source body." in prompt
    assert "Be brief." in prompt
    assert "Ana" in prompt


# --- M1: openai-compatible writer + voice (mocked HTTP) ----------------------


class _FakeResponse:
    def __init__(self, *, ok=True, payload=None, content=b"", status=200, text=""):
        self.ok = ok
        self._payload = payload or {}
        self.content = content
        self.status_code = status
        self.text = text

    def json(self):
        return self._payload


def test_openai_writer_parses_response(monkeypatch):
    import narra.writers.openai_compatible as mod

    payload = {
        "choices": [
            {"message": {"content": '{"lines": [{"speaker": "Alex", "text": "Hello"}]}'}}
        ]
    }
    monkeypatch.setattr(mod.requests, "post", lambda *a, **k: _FakeResponse(payload=payload))

    writer = mod.OpenAICompatibleWriter()
    result = writer.write(
        mod.ScriptRequest(
            source_text="src",
            format_instruction="fmt",
            base_url="http://x.local/v1",
            model="m",
        )
    )
    assert result.lines[0].text == "Hello"


def test_openai_writer_requires_base_url():
    import narra.writers.openai_compatible as mod
    from narra.writers.base import WriterError

    writer = mod.OpenAICompatibleWriter()
    with pytest.raises(WriterError):
        writer.write(mod.ScriptRequest(source_text="s", format_instruction="f"))


def test_openai_voice_returns_bytes(monkeypatch):
    import narra.tts.openai_compat as mod

    monkeypatch.setattr(
        mod.requests, "post", lambda *a, **k: _FakeResponse(content=b"ID3fake")
    )
    voice = mod.OpenAICompatibleVoice()
    result = voice.synthesize(
        mod.SpeakRequest(text="hi", base_url="http://x.local/v1", voice_id="alloy")
    )
    assert result.data == b"ID3fake"


# --- M1: core voicing + stitching -------------------------------------------


def test_voice_lines_stitches_and_maps_speakers(monkeypatch):
    pytest.importorskip("pydub")
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH")
    import io

    from pydub import AudioSegment

    import narra.tts as tts
    from narra.speakers import Speaker
    from narra.tts.base import SpeakRequest, SpeakResult
    from narra.writers.base import DialogueLine

    wav = io.BytesIO()
    AudioSegment.silent(duration=150).export(wav, format="wav")
    wav_bytes = wav.getvalue()

    seen: list[str] = []

    class FakeVoice:
        name = "fake"

        def synthesize(self, request: SpeakRequest) -> SpeakResult:
            seen.append(request.voice_id)
            return SpeakResult(data=wav_bytes, response_format="wav")

    monkeypatch.setattr(tts, "get_voice", lambda name: FakeVoice())

    speakers = [
        Speaker(name="Alex", voice_id="en-US-AndrewNeural"),
        Speaker(name="Sam", voice_id="en-US-AvaNeural"),
    ]
    lines = [
        DialogueLine(speaker="Alex", text="One"),
        DialogueLine(speaker="Sam", text="Two"),
        DialogueLine(speaker="Alex", text="Three"),
    ]
    audio = core.voice_lines(lines, speakers, load_config())

    assert audio[:3] == b"ID3" or audio[:2] in (b"\xff\xfb", b"\xff\xf3")
    assert seen == ["en-US-AndrewNeural", "en-US-AvaNeural", "en-US-AndrewNeural"]
