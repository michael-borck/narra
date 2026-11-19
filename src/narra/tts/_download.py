"""Small download + extract helpers for managed model assets.

Used by the local voice providers (Piper, Kokoro) to fetch a runtime or voice
on first use. Downloads go to a ``.part`` file and are atomically renamed only
after an optional sha256 check passes, so a half-written download is never used.
"""

from __future__ import annotations

import hashlib
import os
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from urllib.request import Request, urlopen

Progress = Callable[[int, int], None]

#: Modules that ship a standalone runtime sometimes need extraction filters.
try:  # Python 3.12+ deprecates the default tar extraction filter.
    _TAR_FILTER: str | None = "data"
except Exception:  # pragma: no cover
    _TAR_FILTER = None


class DownloadError(Exception):
    """Raised when an asset cannot be downloaded or verified."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(
    url: str,
    dest: str | Path,
    *,
    sha256: str | None = None,
    progress: Progress | None = None,
) -> Path:
    """Download ``url`` to ``dest``, verifying sha256 if given."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    request = Request(url, headers={"User-Agent": "narra"})
    try:
        with urlopen(request, timeout=180) as response, open(tmp, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done, total)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise DownloadError(f"Could not download {url}: {e}") from e

    if sha256 and sha256_file(tmp) != sha256:
        tmp.unlink(missing_ok=True)
        raise DownloadError(f"sha256 mismatch for {url} — refusing to install")
    os.replace(tmp, dest)
    return dest


def extract(archive: str | Path, dest: str | Path) -> Path:
    """Extract a .zip or tar archive into ``dest``."""
    archive = Path(archive)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            if _TAR_FILTER:
                t.extractall(dest, filter=_TAR_FILTER)  # type: ignore[arg-type]
            else:  # pragma: no cover
                t.extractall(dest)
    return dest
