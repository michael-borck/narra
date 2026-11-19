"""Narra CLI: ``narra "source.pdf" --out episode.mp3``, plus ``narra serve``.

The default command routes a bare invocation to ``generate`` so
``narra "paper.pdf"`` just works, the same shape as limn.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from typer.core import TyperGroup

from narra import __version__
from narra.config import ConfigurationError, load_config
from narra.config import save_example_config as _save_example_config
from narra.core import GenerationError
from narra.core import generate as _generate
from narra.formats import format_options

console = Console()
err_console = Console(stderr=True, style="bold red")


class DefaultCommandGroup(TyperGroup):
    """Route bare invocations to ``generate`` so ``narra "a source"`` just works.

    ``narra serve ...`` and ``narra generate ...`` hit their commands normally;
    anything else (a path, or generate's options) is prefixed with ``generate``.
    """

    default_command = "generate"
    _root_tokens = {"-h", "--help", "-V", "--version"}

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        if args and args[0] not in self.commands and args[0] not in self._root_tokens:
            args = [self.default_command, *args]
        return super().parse_args(ctx, args)


app = typer.Typer(
    cls=DefaultCommandGroup,
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"narra {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False, "-V", "--version", callback=_version_callback, is_eager=True
    ),
) -> None:
    """Narra — tell a source document into a multi-speaker podcast episode."""


def _load(config: str | None) -> dict[str, Any]:
    try:
        return load_config(config)
    except ConfigurationError as e:
        err_console.print(str(e))
        raise typer.Exit(code=1) from e


def _apply_overrides(
    settings: dict[str, Any],
    writer: str | None,
    voice: str | None,
    format: str | None,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
) -> dict[str, Any]:
    """Overlay CLI flags on top of the loaded config (flags win)."""
    if writer:
        settings["writer"] = writer
    if voice:
        settings["voice"] = voice
    if format:
        settings["format"] = format
    if model:
        settings["model"] = model
    if base_url or api_key:
        active = str(settings.get("writer") or "gemini")
        block = settings.setdefault("writers", {}).setdefault(active, {})
        if base_url:
            block["base_url"] = base_url
        if api_key:
            block["api_key"] = api_key
    return settings


@app.command()
def init_config(
    path: str = typer.Argument("narra.yaml", help="Where to write the example config."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite if it exists."),
) -> None:
    """Write an example ``narra.yaml`` you can edit."""
    from pathlib import Path

    target = Path(path)
    if force and target.exists():
        target.unlink()
    try:
        written = _save_example_config(str(target))
    except ConfigurationError as e:
        err_console.print(str(e))
        raise typer.Exit(code=1) from e
    console.print(f"Wrote example config to {written}")


@app.command()
def formats() -> None:
    """List the built-in script formats."""
    for option in format_options():
        console.print(f"{option['key']:<12} {option['label']}")


@app.command()
def generate(
    source: str = typer.Argument(..., help="Path to a .pdf or .txt source file."),
    out: str | None = typer.Option(None, "--out", "-o", help="Output audio file."),
    out_dir: str | None = typer.Option(
        None, "--out-dir", help="Directory for auto-named output."
    ),
    format: str | None = typer.Option(None, "--format", "-f", help="Script format."),
    writer: str | None = typer.Option(None, "--writer", "-w", help="Script writer."),
    voice: str | None = typer.Option(None, "--voice", help="Voice provider."),
    model: str | None = typer.Option(None, "--model", "-m", help="Writer model."),
    base_url: str | None = typer.Option(None, "--base-url", help="Writer base URL."),
    api_key: str | None = typer.Option(None, "--api-key", help="Writer API key."),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file."),
) -> None:
    """Generate a podcast episode from a source file."""
    settings = _apply_overrides(
        _load(config), writer, voice, format, model, base_url, api_key
    )

    def progress(message: str) -> None:
        console.print(f"  {message}")

    try:
        episode = _generate(
            source, settings, format=format, writer=writer, voice=voice,
            on_progress=progress,
        )
    except GenerationError as e:
        err_console.print(str(e))
        raise typer.Exit(code=1) from e

    from narra.core import save_episode

    try:
        audio, sidecar = save_episode(episode, out=out, out_dir=out_dir)
    except GenerationError as e:
        err_console.print(str(e))
        raise typer.Exit(code=1) from e
    console.print(f"Saved {audio}")
    console.print(f"Wrote {sidecar}")


@app.command()
def compare(
    source: str = typer.Argument(..., help="Path to a .pdf or .txt source file."),
    voice: list[str] | None = typer.Option(
        None, "--voice", "-v", help="Voice provider to compare (repeatable)."
    ),
    format: str | None = typer.Option(None, "--format", "-f", help="Script format."),
    writer: str | None = typer.Option(None, "--writer", "-w", help="Script writer."),
    model: str | None = typer.Option(None, "--model", "-m", help="Writer model."),
    out_dir: str | None = typer.Option(
        None, "--out-dir", help="Directory for the compared episodes."
    ),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file."),
) -> None:
    """A/B two or more voices on the same script (writes one MP3 per voice)."""
    from pathlib import Path

    from narra.core import (
        Episode,
        GenerationError,
        save_episode,
        slugify,
        unique_path,
        voice_lines,
    )
    from narra.formats import format_prompt, get_format
    from narra.script import outline_to_dialogue, read_source
    from narra.speakers import resolve_speakers
    from narra.writers.base import WriterError

    voices = voice or ["edge", "gemini"]
    settings = _apply_overrides(
        _load(config), writer, None, format, model, None, None
    )
    chosen_format = format or str(settings.get("format") or "deep-dive")
    fmt = get_format(chosen_format)
    chosen_writer = writer or str(settings.get("writer") or "gemini")
    speakers = resolve_speakers(settings.get("speakers"))

    try:
        text = read_source(source)
    except Exception as e:
        err_console.print(str(e))
        raise typer.Exit(code=1) from e

    console.print(f"Writing a '{fmt.key}' script with {chosen_writer}…")
    try:
        lines = outline_to_dialogue(
            text, format_prompt(fmt.key), chosen_writer, settings, speakers=speakers
        )
    except WriterError as e:
        err_console.print(str(e))
        raise typer.Exit(code=1) from e

    base_dir = Path(out_dir).expanduser() if out_dir else Path(".")
    for provider in voices:
        console.print(f"Voicing with {provider}…")
        try:
            audio = voice_lines(lines, speakers, settings, voice_override=provider)
            episode = Episode(
                lines=lines,
                audio=audio,
                source=text,
                source_path=source,
                format=fmt.key,
                writer=chosen_writer,
                voices=[s.voice_ref() for s in speakers],
            )
            stem = slugify(f"{Path(source).stem} {fmt.key} {provider}")
            target = unique_path(base_dir / f"{stem}.mp3")
            audio_path, _ = save_episode(episode, out=str(target))
        except GenerationError as e:
            err_console.print(f"{provider}: {e}")
            continue
        console.print(f"  {provider}: {audio_path}")


@app.command()
def serve(
    host: str | None = typer.Option(None, "--host", help="Bind host."),
    port: int | None = typer.Option(None, "--port", "-p", help="Bind port."),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file."),
) -> None:
    """Run the local web UI (needs the [serve] extra)."""
    settings = _load(config)
    serve_cfg = settings.get("serve") or {}
    bind_host = host or str(serve_cfg.get("host") or "127.0.0.1")
    bind_port = int(port or serve_cfg.get("port") or 5372)
    try:
        from narra.serve import create_app
    except ImportError as e:
        err_console.print(
            "The web UI needs the [serve] extra. Install with:\n"
            '  pip install "narra[serve]"'
        )
        raise typer.Exit(code=1) from e

    import secrets

    import uvicorn

    password = serve_cfg.get("password")
    if not password and bind_host not in ("127.0.0.1", "localhost", "::1"):
        password = secrets.token_urlsafe(9)
        console.print(
            f"Binding to {bind_host} with no password set — generated one: {password}"
        )

    uvicorn.run(create_app(settings, token=password), host=bind_host, port=bind_port)


if __name__ == "__main__":
    app()
