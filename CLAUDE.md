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

## Status (0.6.0 — M4 desktop release)

- **M1 done:** `narra "source.pdf" --format ... --out ...` runs end to end.
  - Writers: `gemini` (default, `gemini-flash-latest`, v1beta), `openai-compatible`
    (BYOK `/v1/chat/completions`, JSON), `ollama` (`/api/chat` + JSON schema).
  - Voices: `edge` (free default), `openai-compatible` (`/v1/audio/speech`),
    `gemini` (native TTS, 24 kHz PCM wrapped to WAV).
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
- **M3 done:** local CPU voices + compare.
  - `piper` — managed runtime + sha256-pinned voices under `~/.narra/piper/`
    (`NARRA_PIPER_DIR` to override). Pure stdlib; downloads the rhasspy release
    + phonemize dylibs on first use, spawns `piper --output-raw`, wraps WAV.
  - `kokoro` — `kokoro-onnx` (lazy import); downloads `kokoro-v1.0.onnx` +
    `voices-v1.0.bin` to `~/.narra/kokoro/`. Needs `pip install "narra[local]"`.
  - Per-speaker voice overrides (any speaker → any provider).
  - `narra compare SRC --voice edge --voice gemini [--out-dir]` writes one MP3
    per voice from a single script.
- **M4 done:** Tauri v2 desktop shell (`desktop/`).
  - `desktop/src-tauri/src/main.rs` — bootstraps a private uv venv, installs
    `narra[serve]==NARRA_VERSION` (0.6.0), runs `narra serve --no-browser
    --desktop --host 127.0.0.1 --port <rand> --out-dir ~/Podcasts/Narra` as a
    sidecar, shows the served UI in an iframe.
  - `serve` gained `--no-browser`, `--desktop`, `--out-dir` for the sidecar.
  - Settings sheet (`desktop/ui/index.html`) reads/writes `~/.narra.yaml`
    (chmod 600): writer, voice, Gemini/OpenAI/Ollama keys+models, piper/kokoro
    voices. `NARRA_DEV_PATH` installs the local source for dev.
  - `cargo check` passes; icons are Canturía placeholders for now.
  - `.github/workflows/desktop.yml` builds installers on `v*` tags (same tag as
    the PyPI release) via the shared app-hq pipeline (stable `Narra-*` asset
    aliases). No bundled sidecar — the Python runtime is uv-installed on first
    launch, so no sidecar Mach-O signing is needed (unlike Document Lens).
  - **Auto-update** (0.6.0): `tauri-plugin-updater` + `plugins.updater` in
    `tauri.conf.json` (endpoint `releases/latest/download/latest.json`, pinned
    pubkey). `check_update`/`install_update` commands; the shell header shows
    a "⬇ Update" button when an update is available. `updater: true` in
    `desktop.yml` makes CI publish a signed `latest.json`. Updater private key
    + password live in repo secrets (`TAURI_SIGNING_PRIVATE_KEY[_PASSWORD]`);
    the public key is in `tauri.conf.json`, the private key in `~/.certs/`.
- **Live-verified:** Gemini writer + edge voice (CLI, 71 s); Gemini writer +
  Gemini voice (CLI, two-speaker); full web flow (script → 48 s MP3 → gallery →
  save → round-trip); **Piper local voice** (downloaded + synthesized a 5.5 s
  WAV); **narra compare** (edge 47.0 s vs piper 47.6 s); sidecar flags serve.
- **Not live-verified:** OpenAI-compatible writer/voice (key has no credits,
  429), Kokoro (310 MB model not pulled), and the Tauri window itself (only
  `cargo check`, no display) — unit-tested / compile-checked.
- **Still to do:** demo mode, real app icon.
- No infographic / show-notes card — that is a separate tool.

## Landing page

`landing/index.html` (adapted from Canturía) is deployed to GitHub Pages at
https://michael-borck.github.io/narra/ by `.github/workflows/pages.yml`. It has
platform detection, direct `/releases/latest/download/Narra-*` links (releases
page hidden), and links to Limn / Canturía / Debrief / Talk Buddy. Hero image:
`landing/assets/narra.png` (headless-Chrome capture of `narra serve`).

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
twine upload dist/narra-0.6.0*     # uses ~/.pypirc
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