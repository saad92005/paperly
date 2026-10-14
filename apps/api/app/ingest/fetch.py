"""Outbound HTTP with an SSRF guard (docs/08): https/http only, public IPs only, size cap,
manual redirects re-checked at every hop."""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

from app.errors import AppError


class FetchBlocked(AppError):
    code, status, message = "validation_error", 422, "That URL can't be fetched."


class TooLarge(AppError):
    code, status, message = "too_large", 413, "The file is larger than the upload limit."


class FetchFailed(AppError):
    code, status, message = "not_found", 404, "Couldn't download that paper."


def _public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            return False
    return True


async def check_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in ("https", "http") or not u.hostname:
        raise FetchBlocked()
    if u.port not in (None, 80, 443):
        raise FetchBlocked()
    if not await asyncio.to_thread(_public, u.hostname):
        raise FetchBlocked()


async def fetch_bytes(
    url: str, *, max_bytes: int, user_agent: str, accept: str = "*/*", max_redirects: int = 5
) -> tuple[bytes, str]:
    headers = {"User-Agent": user_agent, "Accept": accept}
    async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=10), follow_redirects=False) as c:
        for _ in range(max_redirects + 1):
            await check_url(url)
            async with c.stream("GET", url, headers=headers) as r:
                if r.status_code in (301, 302, 303, 307, 308) and "location" in r.headers:
                    url = urljoin(url, r.headers["location"])
                    continue
                if r.status_code >= 400:
                    raise FetchFailed(details={"status": r.status_code})
                declared = int(r.headers.get("content-length") or 0)
                if declared > max_bytes:
                    raise TooLarge()
                buf = bytearray()
                async for part in r.aiter_bytes():
                    buf.extend(part)
                    if len(buf) > max_bytes:
                        raise TooLarge()
                return bytes(buf), r.headers.get("content-type", "")
    raise FetchFailed("Too many redirects.")
