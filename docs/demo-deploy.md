# Hosting the Narra demo

The demo is a shared, rate-limited, non-storing instance of `narra serve` —
visitors generate a couple of episodes in the browser, and a banner invites them
to install locally for real use.

## What `--demo` changes

- **No token** — friction-free, guarded by limits instead.
- **Rate limit** — 6 episodes/hour per client IP (X-Forwarded-For aware).
- **Locked spend** — the writer and voice come from the server config only, so
   visitors can't route spend to other providers the host has keys for.
- **Bounded scripts** — 40 lines max per episode, so a demo can't run for hours.
- **Non-storing** — server-side Save is disabled (403); the UI offers Download
   instead. Gallery entries live in RAM and expire after 15 min.
- **Banner** — the page tells visitors it's a demo and how to install.

## Run it — Docker Compose (recommended for a VPS)

Everything lives in [`deploy/`](../deploy): a compose file that builds the
image from this repo, plus templates for config and secrets. On the VPS:

```bash
mkdir narra && cd narra
base=https://raw.githubusercontent.com/michael-borck/narra/main/deploy
curl -O $base/docker-compose.yml
curl -o narra.yaml $base/narra.yaml.example
curl -o .env $base/.env.example

$EDITOR narra.yaml   # writer + voice + provider settings
$EDITOR .env         # GEMINI_API_KEY / OPENAI_API_KEY; NARRA_DEMO=1 is preset

docker compose up -d
```

Remove `NARRA_DEMO` from `.env` to run a private (non-demo) instance instead:
binding 0.0.0.0 inside the container auto-generates an access token — read it
with `docker compose logs narra`.

Plain `docker run` works too:

```bash
docker build -t narra https://github.com/michael-borck/narra.git
docker run -d --name narra-demo --restart unless-stopped \
  -p 127.0.0.1:5372:5372 \
  -v ./narra.yaml:/config/narra.yaml:ro \
  -e GEMINI_API_KEY=... \
  -e NARRA_DEMO=1 \
  narra
```

## Run it — bare (pip + systemd)

```bash
pip install "narra[serve]"

# narra.yaml next to the working dir (or ~/.narra.yaml):
#   writer: gemini
#   voice: edge

narra serve --demo --host 127.0.0.1 --port 5372
# or: NARRA_DEMO=1 narra serve ...
```

Put a reverse proxy (nginx / Nginx Proxy Manager / Caddy) in front for TLS,
e.g. `app.narra.example.org` → `127.0.0.1:5372`. The rate limiter reads the
first `X-Forwarded-For` entry, which every mainstream proxy sets.

### systemd unit

```ini
[Unit]
Description=Narra demo
After=network.target

[Service]
ExecStart=/opt/narra/.venv/bin/narra serve --demo --no-browser --port 5372
WorkingDirectory=/opt/narra
Environment=GEMINI_API_KEY=...

[Install]
WantedBy=multi-user.target
```

## Notes

- The demo still calls your configured writer and voice — so set them to free or
  cheap providers (edge-tts is free; Gemini Flash is very cheap) and add your own
  budget alarms.
- The demo never writes to disk. If you want a shared instance that *does* save,
  leave `--demo` off and set a `serve.password`; the CLI generates one when you
  bind beyond localhost.