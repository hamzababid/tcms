"""Response hardening (NFR-SEC-09, M8 D10) and the general rate limit (docs/06 §2.10, M8 D11, L9).

The API answers JSON and files, never HTML, so its CSP forbids everything; Caddy sets the single-page
app's CSP and HSTS (deploy/Caddyfile). Attachment downloads keep their own `Content-Security-Policy:
sandbox` (docs/06 §4.12): headers already on a response are not replaced.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections.abc import Awaitable, Callable
from http.cookies import SimpleCookie
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from tcms.api.problems import problem_response

SECURITY_HEADERS: Final = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}
UNLIMITED_PREFIXES: Final = ("/api/v1/health/",)
ACCEPTED_TTL: Final = 3600.0  # seconds a credential that worked stays exempt from the rejected-address block
ACCEPTED_MAX: Final = 50_000  # prune the memo above this many entries


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        # Signed-in data must not land in shared or browser caches (ASVS 8.2.1).
        response.headers.setdefault("Cache-Control", "no-store")
        if self.hsts:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class FixedWindowLimiter:
    """Requests per caller per 60-second window, in this process (docs/03 §13: one limiter per worker
    process, no shared store; with N processes the effective limit is up to N × the setting)."""

    def __init__(
        self, limit: int, *, window: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()
        self._next_sweep = 0.0

    def hit(self, key: str) -> tuple[bool, int, int]:
        """(allowed, remaining, seconds until the window resets)."""
        now = self.clock()
        with self._lock:
            if now >= self._next_sweep:
                self._hits = {k: v for k, v in self._hits.items() if now - v[0] < self.window}
                self._next_sweep = now + self.window
            start, count = self._hits.get(key, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            count += 1
            self._hits[key] = (start, count)
        reset = max(1, math.ceil(start + self.window - now))
        return count <= self.limit, max(0, self.limit - count), reset

    def blocked(self, key: str) -> int:
        """Seconds until the window resets if `key` is over the limit, else 0 (does not count a hit)."""
        now = self.clock()
        with self._lock:
            start, count = self._hits.get(key, (now, 0))
        if now - start >= self.window or count < self.limit:
            return 0
        return max(1, math.ceil(start + self.window - now))


def _credential(request: Request) -> str:
    return request.headers.get("authorization", "") or request.cookies.get("tcms_session", "")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def caller_key(request: Request) -> str:
    """The credential if there is one (hashed: keys stay in memory), else the client address."""
    credential = _credential(request)
    if credential:
        return "c:" + hashlib.sha256(credential.encode()).hexdigest()[:32]
    return "ip:" + _client_ip(request)


def _issued_session(response: Response) -> str | None:
    """The session cookie this response sets (sign-in, MFA step), if any."""
    for header in response.headers.getlist("set-cookie"):
        cookie = SimpleCookie()
        cookie.load(header)
        morsel = cookie.get("tcms_session")
        if morsel is not None and morsel.value:
            return morsel.value
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """The per-caller limit, plus a per-address limit on rejected credentials: without it a client could
    send a new made-up token with every request and get a fresh bucket each time (ASVS 2.4.1)."""

    def __init__(self, app: ASGIApp, *, limit: int) -> None:
        super().__init__(app)
        self.limiter = FixedWindowLimiter(limit)
        self.rejected = FixedWindowLimiter(limit)
        self._accepted: dict[str, float] = {}
        self._lock = threading.Lock()

    def _too_many(self, request: Request, headers: dict[str, str], reset: int) -> Response:
        return problem_response(
            request,
            status=429,
            code="rate_limited",
            title="Too many requests",
            detail=f"More than {self.limiter.limit} requests in a minute. Try again in {reset} s.",
            headers={**headers, "Retry-After": str(reset)},
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if not path.startswith("/api/") or path.startswith(UNLIMITED_PREFIXES):
            return await call_next(request)
        credential = bool(_credential(request))
        key = caller_key(request)
        ip_key = "ip:" + _client_ip(request)
        if credential and not self._recently_accepted(key) and (wait := self.rejected.blocked(ip_key)):
            limit = {"RateLimit-Limit": str(self.limiter.limit), "RateLimit-Remaining": "0"}
            return self._too_many(request, {**limit, "RateLimit-Reset": str(wait)}, wait)
        allowed, remaining, reset = self.limiter.hit(key)
        headers = {
            "RateLimit-Limit": str(self.limiter.limit),
            "RateLimit-Remaining": str(remaining),
            "RateLimit-Reset": str(reset),
        }
        if not allowed:
            return self._too_many(request, headers, reset)
        response = await call_next(request)
        if credential:
            if response.status_code == 401:
                self.rejected.hit(ip_key)
            else:
                self._accept(key)
        if issued := _issued_session(response):
            self._accept("c:" + hashlib.sha256(issued.encode()).hexdigest()[:32])  # just signed in
        response.headers.update(headers)
        return response

    def _accept(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._accepted) > ACCEPTED_MAX:
                self._accepted = {k: t for k, t in self._accepted.items() if now - t < ACCEPTED_TTL}
            self._accepted[key] = now

    def _recently_accepted(self, key: str) -> bool:
        """A credential that worked within the last hour: its holder is not blocked by someone else's
        rejected tokens from the same address (an office behind one NAT address)."""
        t = self._accepted.get(key)
        return t is not None and time.monotonic() - t < ACCEPTED_TTL
