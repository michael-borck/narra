# Narra desktop

A native shell (Tauri v2) around the Python core. It uses the OS webview, so
the installer stays small: no bundled browser engine, no 1 GB Python bundle.

## How it works

1. **First launch** bootstraps a private runtime: finds (or downloads) `uv`,
   creates a venv in the app-data dir with a uv-managed Python, and installs
   `narra[serve]` pinned to `NARRA_VERSION` in `src-tauri/src/main.rs`.
2. The shell runs `narra serve` on a random localhost port as a sidecar
   (killed on exit) and shows the web UI in the window.
3. **Settings** (from the header) is the BYO screen: the writer (Gemini,
   OpenAI-compatible, or Ollama), the default voice (edge, OpenAI-compatible,
   Gemini, Piper, or Kokoro), and the keys/endpoints each needs → written to
   `~/.narra.yaml` (chmod 600), the same config the CLI uses. Episodes are
   saved to `~/Podcasts/Narra`.

Privacy: no account, no telemetry, no bundled cloud — the only egress is the
request to the writer and voice providers the user configures.

## Develop

```bash
cargo install tauri-cli --locked
cd desktop
npm install
cargo tauri dev
```

The sidecar installs `narra[serve]==0.3.0` from PyPI. To use the local source
instead, set `NARRA_DEV_PATH="/Volumes/Crucial X9/Projects/podcast-gen"`; the
first run downloads `uv` if needed, then installs the editable package. Delete
the app-data `runtime/narra-version` marker to force a reinstall after Python
changes.

On this repo's exFAT drive, set `CARGO_TARGET_DIR` to an internal disk.

## Release

The desktop build uses the same `v*` tag as the PyPI release (e.g. `v0.5.0`):
`desktop.yml` calls the shared app-hq Tauri pipeline, and `NARRA_VERSION` in
`src-tauri/src/main.rs` plus the versions in `src-tauri/tauri.conf.json` +
`src-tauri/Cargo.toml` all match the Python package version. Then:

```bash
git tag v0.5.0 && git push origin v0.5.0
```

CI builds macOS (arm64 + x86_64), Windows (msi/exe) and Linux (AppImage/deb/rpm)
installers. macOS builds are signed and notarized when the Apple secrets are
set; Windows/Linux are unsigned.

### Sidecars

Narra does not bundle a Python sidecar — the shell installs `narra[serve]` into
a uv venv on first launch (like Canturía). So there is no Mach-O sidecar to sign
at build time; tauri-action signs the Rust shell, and the runtime download is
per-user. (The app-hq `PyInstaller / sidecar bundles` steps only apply to apps
that ship a bundled backend, e.g. Document Lens.)

## Icons

`src-tauri/icons/` currently carries a placeholder waveform icon borrowed from
Canturía. Replace the SVG and rerun the conversion when a real Narra icon is
designed.