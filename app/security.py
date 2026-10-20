"""HTTP hardening (docs/SECURITY.md): security headers on every response, a same-origin check on
state-changing requests (CSRF), a size cap on upload bodies enforced while they stream in, and
per-user rate limits for the chat and uploads.

One ASGI middleware does the first three, in this order: headers are attached to whatever response
goes out (including its own refusals), then the origin check, then the body cap.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth import RateLimiter

# The built web app loads only its own files, OneMap tiles, and data:/blob: images (Leaflet's icons,
# a picked photo's preview). No inline scripts. Inline styles stay allowed: React and Leaflet set
# style attributes, and a style can't run code.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https://www.onemap.gov.sg",
    "font-src 'self' data:",
    "connect-src 'self'",
    "media-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
# FastAPI's Swagger page (demo mode only) loads its script and styles from jsDelivr with an inline
# bootstrap script; it gets its own policy so the app's stays strict.
DOCS_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "style-src 'self' https://cdn.jsdelivr.net",
    "img-src 'self' data: https://fastapi.tiangolo.com",
    "frame-ancestors 'none'",
])
DOCS_PATHS = ("/api/docs", "/api/docs/oauth2-redirect")
# Voice input uses the microphone and "Take a photo" may use the camera; nothing else is needed.
PERMISSIONS_POLICY = "microphone=(self), camera=(self), geolocation=(), payment=(), usb=(), serial=(), bluetooth=()"  # noqa: E501

STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
DEV_ORIGINS = tuple(f"http://{h}:{p}" for h in ("127.0.0.1", "localhost") for p in (8000, 5173))
MULTIPART_SLACK = 64 * 1024  # boundaries and part headers around the file itself


def origin_of(url: str) -> str | None:
    p = urlsplit(url.strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    default = {"http": 80, "https": 443}[p.scheme]
    port = "" if p.port in (None, default) else f":{p.port}"
    return f"{p.scheme}://{p.hostname.lower()}{port}"


def allowed_origins(base_url: str, extra: str | None = None) -> frozenset[str]:
    """The app's own origin (WAYPOINT_BASE_URL), the local dev origins (ports 8000 and 5173), and any
    listed in WAYPOINT_ALLOWED_ORIGINS (comma-separated)."""
    urls: Iterable[str] = [base_url, *DEV_ORIGINS, *(extra or os.environ.get("WAYPOINT_ALLOWED_ORIGINS", "")).split(",")]  # noqa: E501
    found = {o for o in (origin_of(u) for u in urls if u.strip()) if o}
    # a local base URL is reachable as both 127.0.0.1 and localhost
    for o in list(found):
        for a, b in (("://127.0.0.1", "://localhost"), ("://localhost", "://127.0.0.1")):
            if a in o:
                found.add(o.replace(a, b))
    return frozenset(found)


class Hardening:
    """ASGI middleware: security headers, same-origin check, upload body cap."""

    def __init__(
        self, app: ASGIApp, *, origins: frozenset[str], body_limits: dict[str, int], hsts: bool = False
    ) -> None:
        self.app = app
        self.origins = origins
        self.body_limits = body_limits
        self.hsts = hsts  # only when the app is served over HTTPS (WAYPOINT_BASE_URL)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        csp = DOCS_CSP if path in DOCS_PATHS else CSP

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                have = {k.lower() for k, _ in headers}
                for k, v in (
                    (b"content-security-policy", csp.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", PERMISSIONS_POLICY.encode()),
                    (b"x-frame-options", b"DENY"),  # for browsers that predate frame-ancestors
                ):
                    if k not in have:
                        headers.append((k, v))
                if self.hsts and b"strict-transport-security" not in have:
                    headers.append((b"strict-transport-security", b"max-age=31536000"))
                message = {**message, "headers": headers}
            await send(message)

        method: str = scope.get("method", "GET")
        if method in STATE_CHANGING and not self._same_origin(scope):
            await _json(send_with_headers, 403, {"detail": "cross_origin_request"})
            return

        limit = self.body_limits.get(path) if method in STATE_CHANGING else None
        if limit is None:
            await self.app(scope, receive, send_with_headers)
            return
        declared = _header(scope, b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _json(send_with_headers, 413, {"detail": "too_large"})  # refused before reading a byte
            return

        seen = 0

        async def capped_receive() -> Message:
            # Raised mid-parse; FastAPI re-raises HTTPException from body reading, the parser closes
            # its spooled files, and the exception handler answers 413.
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise HTTPException(status_code=413, detail="too_large")
            return message

        await self.app(scope, capped_receive, send_with_headers)

    def _same_origin(self, scope: Scope) -> bool:
        """Origin must be one of ours; without Origin, the Referer's origin must be. A browser sends
        Origin on every POST/PATCH/DELETE, so a request with neither is refused too."""
        origin = _header(scope, b"origin")
        if origin is not None:
            return origin_of(origin) in self.origins  # "null" (sandboxed frames, file://) fails here
        referer = _header(scope, b"referer")
        return referer is not None and origin_of(referer) in self.origins


def _header(scope: Scope, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k.lower() == name:
            return str(v.decode("latin-1"))
    return None


async def _json(send: Send, status: int, body: dict[str, Any]) -> None:
    data = json.dumps(body).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode())],
    })
    await send({"type": "http.response.body", "body": data})


class UserRateLimit:
    """Per-user sliding windows (in memory, per process: see docs/SECURITY.md). Over any window the
    request is refused with 429, a plain notice, and Retry-After."""

    def __init__(self, notice: str, *windows: tuple[int, int]) -> None:
        self.notice = notice
        self.limiters = [RateLimiter(limit=n, window_s=s) for n, s in windows]

    def check(self, user_id: str) -> None:
        for lim in self.limiters:
            if not lim.allow(user_id):
                oldest = lim.hits[user_id][0]
                wait = max(1, math.ceil(lim.window - (time.monotonic() - oldest)))
                raise HTTPException(status_code=429, detail=self.notice, headers={"Retry-After": str(wait)})
