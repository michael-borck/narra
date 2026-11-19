# Narra — tell it into a podcast

> *narra (Spanish): "tell!" / "narrate!"*

A small, privacy-first tool that turns a source document into a two (or more)
speaker podcast episode. Give it a PDF or text file, pick a format, choose who
writes the script and which voices speak it, and get an MP3. No account, no
telemetry, bring your own providers.

## Install

```bash
pip install "narra[gemini,edge,audio]"   # writer + free voice + stitching
export GEMINI_API_KEY=...                # default writer
```

## Use

```bash
narra "paper.pdf" --format deep-dive --out episode.mp3
narra "notes.txt" --format brief --voice edge
narra init-config                   # write an example narra.yaml
narra serve                         # local web UI (pip install "narra[serve]")
```

Or as a library:

```python
from narra.config import load_config
from narra import core

settings = load_config()
episode = core.generate("paper.pdf", settings, format="deep-dive")
```

## Providers

- **Writer** (writes the script): `gemini` (default), `openai-compatible` (BYOK,
  any `/v1/chat/completions`), `ollama` (local).
- **Voice** (speaks each line): `edge` (free, default), `openai` /
  `openai-compatible` (OpenAI standard `/v1/audio/speech`), `gemini` (native
  TTS), `piper` (local CPU), `kokoro` (local CPU).

Keys live in `~/.narra.yaml` (or `${VAR}` references), never in the browser.

## Status

**0.2.0 — M2.** The core runs end to end (source → script → voicing → MP3 +
sidecar), and `narra serve` adds a local web UI: paste or upload a source, pick a
format and speakers, **write the script, edit it, then speak it** — with an
in-memory gallery and Save. `piper`/`kokoro` (M3) and the desktop app (M4) are
still to come. See `SPEC.md` for the full design and milestones.

## Privacy

No account. No telemetry. The only network egress is the request to the writer
and voice providers you configure. Piper and Kokoro run locally; Ollama is
local. Audio saves to `~/Podcasts/Narra` with a JSON sidecar.

## Credits

Narra borrows ideas, with acknowledgment, from
[GroqCasters](https://github.com/jgravelle/GroqCasters) (J. Gravelle, MIT),
[Open Notebook](https://github.com/lfnovo/open-notebook) (MIT), and the author's
own [limn](https://github.com/michael-borck/limn),
[canturía](https://github.com/michael-borck/canturia), and
[talk-buddy](https://github.com/michael-borck/talk-buddy).

## Licence

MIT © Michael Borck.