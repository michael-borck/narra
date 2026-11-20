# Narra web UI / demo container.
#
# Provider config comes from a narra.yaml mounted at /config, secrets from env:
#
#   docker build -t narra .
#   docker run -d -p 5372:5372 \
#     -v ./narra.yaml:/config/narra.yaml:ro \
#     -e GEMINI_API_KEY=... \
#     -e NARRA_DEMO=1 \
#     narra
#
# NARRA_DEMO=1 -> shared demo (no token, rate-limited, non-storing).
# Without it, binding 0.0.0.0 auto-generates an access token (see logs).
FROM python:3.12-slim

ARG NARRA_VERSION=0.8.0
RUN pip install --no-cache-dir "narra[serve]==${NARRA_VERSION}"

RUN useradd --create-home narra
USER narra
WORKDIR /config

EXPOSE 5372
ENTRYPOINT ["narra", "serve", "--host", "0.0.0.0", "--no-browser"]