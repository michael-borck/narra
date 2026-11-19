# Narra — specification

> *narra (Spanish): "tell!" / "narrate!" — the second-person command to tell a story.*

A small, privacy-first tool that turns a source document into a two (or more)
speaker podcast episode. Give it a PDF or text file, pick a format, choose who
writes the script and which voices speak it, and get an MP3. No account, no
telemetry, bring your own providers.

---

## 1. Vision

Most "NotebookLM-style" audio tools are a single locked-in web service (an
account, your documents on their servers) or a heavy research platform
(notebooks, embeddings, chat, Docker). **Narra sits deliberately in between:**
the simplest possible "source → podcast episode" surface that you own.

- **Give it a source → get an episode.** That's the whole interaction.
- **No account, no lock-in, privacy by default.** Your documents and audio are
  yours. On the desktop nothing leaves your machine except the request to the
  writer and voice providers *you* configure.
- **Bring your own providers.** A *writer* (an LLM that turns source text into a
  script) and a *voice* (text-to-speech), each configured independently. Use a
  cloud key, an OpenAI-compatible endpoint, or a local CPU model.
- **Minimal by design.** Format, speakers, and one Generate button. Advanced
  knobs live in the providers and the config, not in the main flow.

## 2. Principles

1. **Simple beats powerful.** One source in, one episode out. Advanced options
   stay in config.
2. **Local-first & private.** No account, no telemetry, no server-side storage
   of sources or audio. The web UI keeps its session gallery in memory; nothing
   is written to disk unless you press Save.
3. **Provider-shaped, not provider-locked.** The core does not depend on any one
   writer or voice. Writers and voices are thin modules behind one interface.
4. **Progressive surfaces.** The same core powers a CLI, a web UI, and a desktop
   app. Each is optional.
5. **Fail visibly.** A provider error stops the run with a clear message; no
   silent fallback to a different provider.

## 3. Surfaces

### v1 — CLI

```bash
narra "paper.pdf" --format deep-dive --out episode.mp3
narra "notes.txt" --format brief --writer openai-compatible --voice edge
narra init-config                 # write an example narra.yaml
narra compare "paper.pdf" --voice edge --voice gemini   # A/B two voices
narra serve                       # local web UI
```

Options: `--format`, `--writer`, `--voice`, `--speakers`, `--out`, `--out-dir`,
`--config`, `--base-url`, `--api-key`, `--model`, `--voice-model`, `--timeout`.

### v2 — Web UI (`narra serve`)

A single page (FastAPI + a self-contained HTML page, no CDNs):

- A **source** box (paste text or pick a file).
- A **format** selector: your shipped presets as chips, plus a custom briefing.
- A **speaker strip**: 1–N speakers, each with a name, a persona, and a voice
  picked from any configured voice provider.
- **Generate** → a pending card (writing script, then voicing lines) → an audio
  card with a player.
- **Preview script** before committing audio: edit the lines, then **Speak
  this script**.
- In-memory session gallery (capped) with **Save / Download / Again / Delete**.
- A **Help** sheet: what each format does, where the script comes from, BYOK,
  local voices, and where files are saved.

Binds `127.0.0.1` by default; an optional shared password gates hosted
instances. Keys live in config, never in the browser.

### v3 — Desktop (Tauri v2 + Python sidecar)

A native, installable app. Tauri v2 uses the OS webview. On first launch it
bootstraps a private runtime with `uv`, creates a venv in the app-data
directory, installs `narra[serve]==<pin>`, runs `narra serve` on a random
localhost port, and shows the served UI. A Settings sheet reads/writes
`~/.narra.yaml` (merge-preserving, chmod 600) — the same file the CLI uses.
Saves land in `~/Podcasts/Narra`. Distributed as a signed installer; not on the
Mac App Store (runtime-download rules).

### Demo — "try before install" (later)

A hosted instance that is rate-limited and non-storing: generate a couple of
episodes, nothing saved server-side, with a banner inviting users to install
locally for full control and privacy.

## 4. The pipeline

```
source (pdf/txt)
      │  read_source()
      ▼
  writer (LLM)  ──► script: [DialogueLine]   (outline → expand → dialogue)
      │
      ▼
  speakers: each line assigned a speaker → a voice from a voice provider
      │
      ▼
  voices (TTS)  ──► per-line audio  ──► concatenate (pauses) ──► episode.mp3
      │
      ▼
  save + <episode>.json sidecar
```

### Formats (writer styles)

`formats.py` is a registry mapping a format key to a prompt fragment. Shipped:

| Key | Shape |
|---|---|
| `deep-dive` | 18–24 lines, two hosts (Alex storyteller, Sam skeptic) |
| `brief` | 6–8 short lines, single host (Alex), under 90 s |
| `critique` | 16–20 lines, candid domain reviewers (Alex + Sam) |
| `debate` | 18–22 lines, optimistic pro vs tough skeptic |

A format may also be a **custom briefing** (free text) for open-notebook-style
"episode profiles". Writer rules are appended to every format: cold open (no
"welcome back"), cite concrete facts, avoid AI clichés, no stage directions.

### Writers (write the script)

| Name | What | Auth |
|---|---|---|
| `gemini` | Google Gemini (`google-genai`), default `gemini-flash-latest` | `GEMINI_API_KEY` |
| `openai-compatible` | Any `/v1/chat/completions`: OpenAI, LM Studio, llama.cpp, OpenRouter | Bearer key (optional locally) |
| `ollama` | Local Ollama chat model | none |

The writer receives the source text plus the format and returns structured
`[DialogueLine]`. Gemini uses a typed schema; the OpenAI-compatible writer asks
for JSON and validates.

### Voices (speak each line)

`tts/` exposes one interface, `synthesize(text, voice, opts) -> audio bytes`.
Shipped:

| Name | What | Auth / notes |
|---|---|---|
| `edge` | edge-tts neural voices, free | none (default) |
| `openai` / `openai-compatible` | OpenAI standard `POST {base}/audio/speech` (`model`, `input`, `voice`, `response_format`, `speed`) | Bearer key (optional for local Speaches/LocalAI) |
| `gemini` | Gemini native TTS (single- or multi-speaker), 24 kHz PCM | `GEMINI_API_KEY` |
| `piper` | Local CPU, tiny ONNX voices, ~0.05× realtime | sha256-verified first-run download |
| `kokoro` | Local CPU via `kokoro-onnx` (~120 MB), or a Speaches server | local or server URL |

Two concatenation strategies must be supported: **per-line** (edge, piper,
kokoro, openai-compatible — synthesize each line, stitch with 180–420 ms pauses)
and **single-call** (gemini native multi-speaker — one request returns the whole
dialogue).

### Speakers

A `Speaker` has a `name`, an optional `persona` (fed to the writer), and a
`voice` reference `{provider, voice_id, model}`. Two defaults ship: **Alex**
(male) and **Sam** (female). A format that is single-host uses Alex only. The
web UI and config can define 1–N speakers; each may point at a *different* voice
provider (open-notebook's per-speaker override).

## 5. Config

Layered, later wins (mirrors limn/canturía):

1. Built-in defaults.
2. `~/.narra.yaml` — your providers + keys, set once.
3. `./narra.yaml` (or `--config FILE`).
4. CLI flags / environment.

```yaml
writer: gemini                 # gemini | openai-compatible | ollama
voice: edge                    # edge | openai-compatible | gemini | piper | kokoro
format: deep-dive

writers:
  gemini:
    model: gemini-3.5-flash
    api_key: "${GEMINI_API_KEY}"
  openai-compatible:
    base_url: https://api.openai.com/v1
    model: gpt-4o-mini
    api_key: "${OPENAI_API_KEY}"
  ollama:
    base_url: http://127.0.0.1:11434
    model: qwen3.5:4b

voices:
  edge: {}
  openai-compatible:
    base_url: https://api.openai.com/v1
    model: gpt-4o-mini-tts
    api_key: "${OPENAI_API_KEY}"
  gemini:
    model: gemini-3.8-flash-tts
    api_key: "${GEMINI_API_KEY}"
  piper:
    voice: en_GB-alan-low
  kokoro:
    voice: bm_george

speakers:
  - name: Alex
    persona: Storyteller who sees the big picture.
    voice: { provider: edge, voice_id: en-US-AndrewNeural }
  - name: Sam
    persona: Curious skeptic who asks sharp follow-ups.
    voice: { provider: edge, voice_id: en-US-AvaNeural }

serve:
  host: 127.0.0.1
  port: 5372
  password: "${NARRA_SERVE_PASSWORD}"
  out_dir: ~/Podcasts/Narra
```

Secrets are referenced as `${VAR}` so no plaintext keys live in files. Default
serve port **5372** ("NARR" on a phone keypad).

## 6. Architecture

```
narra/
  config.py              layered config + ${VAR} expansion
  formats.py             format registry + writer rules
  speakers.py            Speaker dataclass, defaults, voice refs
  writers/
    base.py              Writer ABC, ScriptRequest/ScriptResult
    gemini.py  openai_compatible.py  ollama.py
  tts/
    base.py              VoiceProvider ABC, SpeakRequest
    edge.py  openai_compat.py  gemini.py  piper.py  kokoro.py
  script.py              read_source(), outline→dialogue, text cleanup
  core.py                generate(): script → per-line audio → episode + sidecar
  cli.py                 Typer CLI
  serve.py               FastAPI app factory [serve extra]
  serve_page.html        self-contained web UI (package data)
  desktop/               Tauri v2 shell + uv-bootstrapped sidecar
tests/
```

- **Python 3.10+**, `typer`, `rich`, `requests`, `pyyaml`, `pydantic`.
- **Extras:** `audio=[pydub]`, `edge=[edge-tts]`, `gemini=[google-genai]`,
  `local=[piper-tts, kokoro-onnx, numpy]`, `serve=[fastapi, uvicorn]`.
- **Packaging:** hatchling; `pip install narra`, publish to PyPI.

## 7. Privacy and storage

- No account, no telemetry, no logging of sources or scripts.
- The only egress is the request to the writer and voice providers you
  configure. Piper and Kokoro run locally; Ollama is local.
- The web session gallery is in memory, capped, and dies with the process.
- Save writes the audio plus a `<episode>.json` sidecar (writer, voice,
  format, source hash, settings) into `~/Podcasts/Narra` (configurable). Save
  never overwrites.
- Keys are never exposed to the browser.

## 8. Attribution

Narra borrows ideas, with acknowledgment, from:

- **GroqCasters** by J. Gravelle (MIT) — the outline → expand → dialogue
  pipeline, host personas, and voice cloning from a short sample. © J. Gravelle;
  a mention is retained per the licence.
- **Open Notebook** by lfnovo and contributors (MIT) — episode profiles,
  per-speaker voice-model overrides, the "what each model sees" privacy framing,
  and background-job retry.
- The author's own **limn**, **canturía**, and **talk-buddy** — the
  provider/config/serve architecture, the `compare` workflow, and the
  sha256-verified first-run model download for Piper.

## 9. Non-goals

- Not a research notebook, chat, or embeddings tool. Narra makes one thing:
  an episode from a source.
- Not a DAW or audio editor.
- Not a model host — Narra calls the providers you point it at.
- No infographic / show-notes card in v1 (a separate tool handles that).

## 10. Milestones

1. **M1 — Core + CLI.** `narra "source" --format ... --out ...`; Gemini writer +
   OpenAI-compatible writer; edge + OpenAI-compatible voices; layered config;
   PyPI publish.
2. **M2 — Web UI.** `narra serve` with source box, format chips, speaker strip,
   preview/edit script, session gallery with Save/Download/Again/Delete, password
   gate, Help sheet.
3. **M3 — Local + BYOK voices.** Piper + Kokoro (CPU) with sha256 model
   download, Gemini native TTS (single + multi-speaker), per-speaker voice
   override, `narra compare` voices.
4. **M4 — Desktop + landing.** Tauri shell, first-run uv runtime, Settings
   sheet, CI installers, demo mode, landing page.

## 11. Release notes

- **0.0.1 — skeleton.** The frame: installs, imports, `narra --version` /
  `init-config` work, providers and `generate()` stubbed. Proved the name, repo,
  CI, and packaging.
- **0.1.0 — M1.** The core runs end to end: source → script → per-line voicing →
  stitched MP3 + JSON sidecar. Writers: `gemini` (v1beta, `gemini-flash-latest`),
  `openai-compatible`, `ollama`. Voices: `edge`, `openai-compatible`, `gemini`.
  `piper` / `kokoro` remain stubs for M3.
- **0.2.0 — M2.** `narra serve`: a single-page web UI with a two-step flow
  (write script → edit → speak), source paste + txt/pdf upload, format chips,
  editable speaker strip, in-memory gallery with Save/Download/Delete, and an
  optional token gate. Same core as the CLI.