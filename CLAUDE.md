# Narra — agent handover

`SPEC.md` is the source of truth. This file is the short working note.

## What it is

A privacy-first **source → podcast episode** tool. Point it at a PDF or text
file, choose a format (deep-dive, brief, critique, debate, or a custom
briefing), a *writer* (the LLM that writes the script) and a *voice* (TTS, one
per speaker). Get an MP3. Same shape as Limn and Canturía: Python core + Typer
CLI + FastAPI single page + Tauri v2 shell. PyPI package and CLI: `narra`.

Two provider abstractions, chosen independently:
- **writer** — `gemini` (default), `openai-compatible` (BYOK), `ollama` (local)
- **voice** — `edge` (default, free), `openai` / `openai-compatible`
  (`/v1/audio/speech`), `gemini` (native), `piper` (local CPU), `kokoro`
  (local CPU / Speaches)

## Status (0.2.0 — M2)

- **M1 done:** `narra "source.pdf" --format ... --out ...` runs end to end.
  - Writers: `gemini` (default, `gemini-flash-latest`, v1beta), `openai-compatible`
    (BYOK `/v1/chat/completions`, JSON), `ollama` (`/api/chat` + JSON schema).
  - Voices: `edge` (free default), `openai-compatible` (`/v1/audio/speech`),
    `gemini` (native TTS, 24 kHz PCM wrapped to WAV). `piper` + `kokoro` are
    still stubs (M3).
  - `core.generate()`: read source → writer → per-line voicing → pydub stitch
    (180–420 ms pauses) → MP3 + JSON sidecar. `--voice` overrides all lines;
    per-speaker providers come from `speakers:` profiles.
- **M2 done:** `narra serve` web UI (`src/narra/serve.py` + `serve_page.html`).
  - Two-step flow: `POST /api/script` (write) → `POST /api/audio` (speak), so the
    script is editable before any TTS spend.
  - Endpoints: `/api/config`, `/api/extract` (txt/pdf upload), `/api/script`,
    `/api/audio`, `/api/episodes` (list/audio/delete/save). Optional token gate
    (`X-Narra-Token` / `?token=` / cookie); generated for non-local binds.
  - In-memory gallery (cap 50); Save writes MP3 + sidecar to `serve.out_dir`
    (default `~/Podcasts/Narra`). Self-contained page, no CDNs.
- **Live-verified:** Gemini writer + edge voice (CLI, 71 s); Gemini writer +
  Gemini voice (CLI, two-speaker); full web flow (script → 48 s MP3 → gallery →
  save → audio round-trip) via HTTP.
- **Not live-verified:** OpenAI-compatible writer/voice (key has no credits, 429)
  — unit-tested with mocked HTTP. Ollama not run (no local server).
- **Still skeleton:** `piper`/`kokoro` (M3), desktop (M4).
- No infographic / show-notes card — that is a separate tool.

## Local commands

```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/narra"   # repo is on exFAT
uv sync --all-groups
uv run --no-sync ruff check src tests
uv run --no-sync basedpyright
uv run --no-sync pytest
```

## Publish (skeleton → PyPI)

```bash
uv build
twine upload dist/narra-0.2.0*     # uses ~/.pypirc
```

CI `publish.yml` also builds on `v*` tags via `pypa/gh-action-pypi-publish`, but
it needs a `PYPI_API_TOKEN` repo secret; the manual twine path is the reliable
one until that secret is set.

## Machine gotchas

- The repo is on an exFAT drive. Keep the venv on the internal disk via
  `UV_PROJECT_ENVIRONMENT`; macOS writes AppleDouble `._*` files that break
  `uv sync` otherwise. `.gitignore` and the build exclude `._*`.
- Source material lives in `../` siblings: `generate_podcast.py` (this folder,
  truncated at the Gemini TTS branch) and `~/Downloads/generate_notebook.py`
  (the complete original it was split from — use it to reconstruct the Gemini
  voice path).

## Decisions

- Two providers (writer + voice), like Canturía's lyricist + ACE-Step split.
- Ship edge as the free default voice; Gemini writer as the default writer to
  match the original script's behaviour.
- Formats are a registry, not hardcoded; the four shipped presets came from the
  original `STYLE_PROMPTS`.
- 1–N speakers with per-speaker voice override (open-notebook idea); Alex/Sam
  are the two defaults.
- Default serve port 5372 ("NARR").
- Attribution retained for GroqCasters (J. Gravelle, MIT) and Open Notebook
  (MIT) — see SPEC §8.
- Build order: skeleton → M1 CLI/web → M2 → M3 local voices → M4 desktop.

## Reference

- Original script: `generate_podcast.py` (this dir) and the complete
  `~/Downloads/generate_notebook.py`.
- Pattern siblings: `../limn` (providers, serve, Tauri), `../song-gen`
  (canturía — lyricists, serve, pyproject, workflows), `../talk-buddy`
  (Piper bridge, sha256 model install).
- External ideas: https://github.com/jgravelle/GroqCasters,
  https://github.com/lfnovo/open-notebook.