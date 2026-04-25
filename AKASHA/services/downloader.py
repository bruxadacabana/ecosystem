"""
AKASHA — Download service
Gerencia downloads assíncronos com rastreamento de progresso em DB.
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

import database

_log = logging.getLogger(__name__)

_DEFAULT_DEST = Path.home() / "Downloads"

_active: dict[int, asyncio.Task] = {}


def is_active(download_id: int) -> bool:
    task = _active.get(download_id)
    return task is not None and not task.done()


async def start_download(download_id: int, url: str, dest_dir: str = "") -> None:
    """Agenda o download em background; retorna imediatamente."""
    dest = Path(dest_dir) if dest_dir else _DEFAULT_DEST
    dest.mkdir(parents=True, exist_ok=True)
    task = asyncio.get_running_loop().create_task(
        _run(download_id, url, dest)
    )
    _active[download_id] = task
    task.add_done_callback(lambda _: _active.pop(download_id, None))


async def cancel_download(download_id: int) -> bool:
    task = _active.get(download_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _run(download_id: int, url: str, dest: Path) -> None:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()

                filename = _extract_filename(resp, url)
                size_bytes = int(resp.headers.get("content-length", 0))

                out_path = _unique_path(dest / filename)
                await database.update_download_start(
                    download_id, out_path.name, str(dest), size_bytes
                )

                downloaded = 0
                _last_db_write = 0
                with out_path.open("wb") as fh:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if downloaded - _last_db_write >= 512 * 1024:
                            await database.update_download_progress(
                                download_id, downloaded, size_bytes or downloaded
                            )
                            _last_db_write = downloaded

                await database.finish_download(
                    download_id, out_path.name, "done"
                )

    except asyncio.CancelledError:
        await database.finish_download(download_id, "", "error", "cancelado pelo usuário")
    except Exception as exc:
        _log.warning("download %d falhou: %s", download_id, exc)
        await database.finish_download(download_id, "", "error", str(exc)[:200])


def _extract_filename(resp: httpx.Response, url: str) -> str:
    cd = resp.headers.get("content-disposition", "")
    if cd:
        m = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd, re.I)
        if m:
            return unquote(m.group(1).strip().strip('"\''))

    path_part = unquote(urlsplit(url).path.rstrip("/"))
    name = Path(path_part).name
    if name:
        return name

    ct = resp.headers.get("content-type", "").split(";")[0].strip()
    ext = mimetypes.guess_extension(ct) or ".bin"
    return f"download{ext}"


def _unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    i = 1
    while True:
        candidate = p.parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1
