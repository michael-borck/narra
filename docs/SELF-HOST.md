# Self-hosting Narra & bringing your own providers

Narra is yours to run. This guide covers the two things you configure — a
**writer** (the LLM that writes the script) and a **voice** (the TTS that speaks
each line) — plus how to expose it to other devices safely.

Everything lives in one config file, `~/.narra.yaml` (or `./narra.yaml` next to
where you run it). `narra init-config` writes an example you can edit.

---

## 1. The two providers

Narra splits the job in two, exactly like Canturía splits lyricist + singer:

- **Writer** — reads your source and writes the dialogue. One of:
  `gemini` (default), `openai-compatible` (BYOK), `ollama` (local).
- **Voice** — speaks each line. One of:
  `edge` (free), `openai-compatible`, `gemini`, `piper` (local), `kokoro` (local).

Each speaker can use a *different* voice provider, so you can mix, say, an
OpenAI voice for one host and a local Piper voice for the other.

## 2. Quick start with the free defaults

The default (`writer: gemini`, `voice: edge`) needs one key and no installs
beyond the package:

```bash
pip install "narra[gemini,edge,audio]"
export GEMINI_API_KEY=...            # or put it in ~/.narra.yaml
narra "paper.pdf" --out episode.mp3
```

Edge-TTS is free and needs no key. Gemini Flash is very cheap. That combination
is the lowest-friction path.

## 3. Bring your own OpenAI-compatible endpoint (BYOK)

Point Narra at any `/v1/chat/completions` (writer) and/or `/v1/audio/speech`
(voice) endpoint — OpenAI, LM Studio, llama.cpp, LocalAI, Speaches, vLLM,
OpenRouter.

```yaml
writer: openai-compatible
voice: openai-compatible

writers:
  openai-compatible:
    base_url: https://api.openai.com/v1     # must include /v1
    model: gpt-4o-mini
    api_key: "${OPENAI_API_KEY}"            # or set OPENAI_API_KEY

voices:
  openai-compatible:
    base_url: https://api.openai.com/v1
    model: gpt-4o-mini-tts
    api_key: "${OPENAI_API_KEY}"
```

Or from the CLI, one flag each:

```bash
narra "paper.pdf" \
  --writer openai-compatible --base-url http://127.0.0.1:1234/v1 --model qwen2.5 \
  --voice openai-compatible --voice-model kokoro --out episode.mp3
```

`--base-url` and `--api-key` apply to the active writer **and**, when the voice
is `openai`/`openai-compatible`, to the voice too. `--model` is the writer model;
`--voice-model` is the TTS model.

> Keys are referenced as `${VAR}` so no plaintext keys sit in files. They are
> never sent anywhere except the endpoint you configure, and never exposed to
  the browser.

## 4. Run fully local

### Writer: Ollama

```bash
ollama pull qwen3.5:4b
```

```yaml
writer: ollama
writers:
  ollama:
    base_url: http://127.0.0.1:11434
    model: qwen3.5:4b
```

### Voice: Piper (CPU, tiny, fast)

Piper needs no Python deps — Narra downloads a pinned runtime + voice on first
use into `~/.narra/piper/`.

```yaml
voice: piper
voices:
  piper:
    voice: en_GB-alan-low        # or en_US-amy-low
```

### Voice: Kokoro (CPU, better quality)

```bash
pip install "narra[local]"       # kokoro-onnx + numpy
```

```yaml
voice: kokoro
voices:
  kokoro:
    voice: af_sarah
```

The first synthesis downloads a ~120 MB model into `~/.narra/kokoro/`.

### Fully local, start to finish

```yaml
writer: ollama
voice: piper
```

With Ollama and Piper, nothing leaves your machine.

## 5. Sharing it on your network

`narra serve` binds `127.0.0.1` by default. To reach it from another device:

```bash
narra serve --host 0.0.0.0 --port 5372
```

Binding beyond localhost with no password set makes the CLI **generate an access
token** and print it. Pass it as `?token=...`, an `X-Narra-Token` header, or set
`serve.password` in the config. Put a reverse proxy (nginx / Caddy / Nginx Proxy
Manager) in front for TLS.

### Password-gate a shared instance

```yaml
serve:
  host: 0.0.0.0
  port: 5372
  password: "${NARRA_SERVE_PASSWORD}"
```

### Demo mode (public, rate-limited, non-storing)

```bash
narra serve --demo            # or NARRA_DEMO=1
```

See [`docs/demo-deploy.md`](./demo-deploy.md) for Docker/systemd/reverse-proxy
recipes.

## 6. Where things are

| What | Where |
|---|---|
| Config | `~/.narra.yaml` (chmod 600), `./narra.yaml`, or `--config` |
| Episodes | `~/Podcasts/Narra` (or `serve.out_dir`) — MP3 + `.json` sidecar |
| Piper runtime + voices | `~/.narra/piper/` (`NARRA_PIPER_DIR` to override) |
| Kokoro model | `~/.narra/kokoro/` (`NARRA_KOKORO_DIR` to override) |
| Web gallery | In memory only; Save is explicit |

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `needs a base_url` (openai-compatible voice) | set `voices.openai-compatible.base_url`, or pass `--base-url` |
| `429 no credits` | your OpenAI account is out of credits; switch writer/voice or add billing |
| `Reading PDFs needs pypdf` | you're on an old Narra; upgrade (`pip install -U narra`) — pypdf ships in core |
| `Stitching audio needs pydub` | `pip install "narra[audio]"` and have `ffmpeg` on PATH |
| Piper first run is slow | it downloads the runtime + voice once (~20 MB); later runs are fast |
| Kokoro first run is slow | it downloads a ~120 MB model once |
| `Could not reach Ollama` | start `ollama serve` and `ollama pull qwen3.5:4b` |