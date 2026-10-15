"""Transferencias acotadas y subprocesos sin shell."""

import asyncio
import ipaddress
import os
from pathlib import Path
import re
import signal
import socket
import sys
from urllib.parse import unquote, urljoin, urlsplit

import httpx


class TransferError(Exception):
    """Mensaje seguro que se puede mostrar en Telegram."""


def safe_name(name: str) -> str:
    name = re.sub(r'[^\w.() -]', '_', name.replace('\\', '/').rsplit('/', 1)[-1])
    return name[:160].strip('. ') or 'archivo.bin'


async def validate_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
            raise ValueError
        port = parts.port or (443 if parts.scheme == 'https' else 80)
        addresses = await asyncio.get_running_loop().getaddrinfo(
            parts.hostname, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError
    except (ValueError, OSError):
        raise TransferError('Usa un enlace HTTP/HTTPS público, sin credenciales ni direcciones privadas.') from None
    return url


async def download_http(url: str, directory: Path, max_bytes: int) -> Path:
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=20), trust_env=False) as client:
        for _ in range(6):
            await validate_url(url)
            async with client.stream('GET', url, headers={'Accept-Encoding': 'identity'}) as response:
                if response.is_redirect:
                    location = response.headers.get('location')
                    if not location:
                        raise TransferError('Redirección sin destino.')
                    url = urljoin(url, location)
                    continue
                response.raise_for_status()
                length = response.headers.get('content-length', '')
                if length.isdigit() and int(length) > max_bytes:
                    raise TransferError('El archivo supera MAX_DOWNLOAD_MB.')
                target = directory / safe_name(unquote(urlsplit(url).path.rsplit('/', 1)[-1]))
                size = 0
                # Raw bytes avoid unbounded decompression of a compressed response.
                with target.open('wb') as output:
                    async for chunk in response.aiter_raw(chunk_size=64 * 1024):
                        size += len(chunk)
                        if size > max_bytes:
                            raise TransferError('La descarga supera MAX_DOWNLOAD_MB.')
                        output.write(chunk)
                return target
    raise TransferError('Demasiadas redirecciones.')


async def run_tool(*args: str) -> None:
    try:
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True)
    except FileNotFoundError:
        raise TransferError('Falta una herramienta. Repite la celda de instalación.') from None
    try:
        code = await process.wait()
    except asyncio.CancelledError:
        # Terminate the full group, including ffmpeg/rclone children.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
        raise
    if code:
        raise TransferError('La herramienta falló. Comprueba el enlace, los permisos o la configuración de rclone.')


async def download_video(url: str, directory: Path, max_bytes: int) -> Path:
    await validate_url(url)
    tool = asyncio.create_task(run_tool(
        sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist',
        '--no-progress', '--restrict-filenames', '--max-filesize', str(max_bytes),
        '--socket-timeout', '30', '--retries', '2', '--concurrent-fragments', '1',
        '-f', 'best[ext=mp4]/best', '-o', str(directory / '%(title).100B.%(ext)s'), '--', url))
    try:
        # yt-dlp cannot always know the size in advance; enforce it while downloading too.
        while not tool.done():
            if sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()) > max_bytes:
                raise TransferError('El video supera MAX_DOWNLOAD_MB.')
            await asyncio.sleep(0.25)
        await tool
    finally:
        if not tool.done():
            tool.cancel()
            await asyncio.gather(tool, return_exceptions=True)
    files = [p for p in directory.iterdir() if p.is_file() and p.suffix not in ('.part', '.ytdl')]
    if len(files) != 1 or not 0 < files[0].stat().st_size <= max_bytes:
        raise TransferError('No se obtuvo un video válido dentro del límite configurado.')
    return files[0]


async def mirror_file(file: Path, destination: str) -> None:
    if not destination:
        raise TransferError('Configura RCLONE_DESTINATION y rclone antes de usar /mirror.')
    await run_tool('rclone', 'copyto', str(file), destination.rstrip('/') + '/' + file.name,
                   '--retries', '2', '--low-level-retries', '2')
