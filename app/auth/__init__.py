"""Auth (SPEC §9): email magic links and a mock WeBank SSO.

Magic links are single-use, expire in 15 minutes, and are rate-limited per email and per IP. The
session cookie is HttpOnly, SameSite=Lax, and Secure outside local development. No passwords.
The mock SSO verifies an HMAC-signed token from the mock identity provider (demo only).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque

SESSION_COOKIE = "wp_session"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[A-Za-z]{2,}$")
# Placeholders that must never sign anything: anyone who read .env.example could forge tokens with them.
PLACEHOLDER_SECRETS = frozenset({"change-me", "changeme", "change_me", "secret", "password", "test", "dev"})


def _sso_secret() -> str:
    """WAYPOINT_SSO_SECRET signs SSO tokens and check-in links. Blank: a random one per process.
    A placeholder is refused outside demo mode (start-up fails) and replaced by a random one in demo."""
    raw = os.environ.get("WAYPOINT_SSO_SECRET", "").strip()
    if raw.lower() in PLACEHOLDER_SECRETS:
        if os.environ.get("WAYPOINT_DEMO", "1") != "1":
            raise RuntimeError(
                "WAYPOINT_SSO_SECRET is a placeholder; leave it blank or set a long random value"
            )
        raw = ""
    return raw or secrets.token_hex(32)


_SSO_SECRET = _sso_secret()


class RateLimiter:
    """Sliding-window limiter, in memory (per process)."""

    def __init__(self, limit: int, window_s: int) -> None:
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


per_email = RateLimiter(limit=3, window_s=15 * 60)
per_ip = RateLimiter(limit=10, window_s=15 * 60)


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip()))


def sso_token(subject: str, ttl_s: int = 300, email: str | None = None) -> str:
    """Mock WeBank IdP: an HMAC-signed token for a simulated business customer. WeBank already holds the
    customer's verified contact email, so the token carries it (that is where reminders go)."""
    claims: dict[str, object] = {"sub": subject, "exp": int(time.time()) + ttl_s}
    if email:
        claims["email"] = email
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
    sig = hmac.new(_SSO_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_sso(token: str) -> dict[str, str] | None:
    """The token's subject and (if any) email, or None when the signature or expiry fails."""
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    good = hmac.new(_SSO_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, sig):
        return None
    data = json.loads(base64.urlsafe_b64decode(body.encode()))
    if int(data.get("exp", 0)) < time.time():
        return None
    out = {"sub": str(data["sub"])}
    if data.get("email"):
        out["email"] = str(data["email"])
    return out


def cookie_secure() -> bool:
    return os.environ.get("WAYPOINT_COOKIE_SECURE", "0") == "1"


def checkin_token(goal_id: str, period: str, ttl_s: int = 21 * 86400) -> str:
    """A signed one-tap link for "on plan as usual" (one goal, one check-in period)."""
    body = base64.urlsafe_b64encode(
        json.dumps({"g": goal_id, "p": period, "exp": int(time.time()) + ttl_s}).encode()
    ).decode()
    sig = hmac.new(_SSO_SECRET.encode(), b"checkin:" + body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_checkin(token: str) -> tuple[str, str] | None:
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    good = hmac.new(_SSO_SECRET.encode(), b"checkin:" + body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, sig):
        return None
    data = json.loads(base64.urlsafe_b64decode(body.encode()))
    if int(data.get("exp", 0)) < time.time():
        return None
    return str(data["g"]), str(data["p"])
