"""SPEC §12.4: magic links expire and are single-use, the email and IP rate limits hold, and every email
template renders and goes out through the configured SMTP sender (to a local stdlib sink, not Mailpit)."""

from __future__ import annotations

import importlib
import re
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.smtp_sink import SmtpSink, html_part, text_part

LINK = re.compile(r"http://\S+/api/auth/verify\?token=([\w-]+)&lang=(en|zh)")


@pytest.fixture()
def sink(monkeypatch: pytest.MonkeyPatch) -> Iterator[SmtpSink]:
    with SmtpSink() as s:
        monkeypatch.setenv("WAYPOINT_SMTP_HOST", "127.0.0.1")
        monkeypatch.setenv("WAYPOINT_SMTP_PORT", str(s.port))
        yield s


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sink: SmtpSink) -> Iterator[TestClient]:
    monkeypatch.setenv("WAYPOINT_VAR", str(tmp_path))
    monkeypatch.setenv("WAYPOINT_DB_URL", f"sqlite:///{tmp_path / 'api.sqlite3'}")
    monkeypatch.setenv("WAYPOINT_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("WAYPOINT_DEMO", "1")
    import app.auth
    import app.main
    import app.store

    importlib.reload(app.store)
    importlib.reload(app.main)
    # the limiters live for the process; start each test with fresh ones at the production limits
    monkeypatch.setattr(app.auth, "per_email", app.auth.RateLimiter(limit=3, window_s=15 * 60))
    monkeypatch.setattr(app.auth, "per_ip", app.auth.RateLimiter(limit=10, window_s=15 * 60))
    with TestClient(app.main.app, headers={"origin": app.main.BASE_URL}) as c:
        yield c


def _request_link(c: TestClient, sink: SmtpSink, email: str = "chen@example.com") -> str:
    before = len(sink.messages)
    assert c.post("/api/auth/request-link", json={"email": email, "lang": "en"}).status_code == 202
    assert len(sink.messages) == before + 1
    rcpt, msg = sink.messages[-1]
    assert rcpt == [email]
    m = LINK.search(text_part(msg))
    assert m is not None
    return m.group(1)


def test_a_magic_link_signs_in_once_and_a_second_use_is_refused(client: TestClient, sink: SmtpSink) -> None:
    token = _request_link(client, sink)
    first = client.get(f"/api/auth/verify?token={token}&lang=en", follow_redirects=False)
    assert first.status_code == 303 and first.headers["location"] == "/"
    assert "wp_session=" in first.headers["set-cookie"]
    assert client.get("/api/goal").status_code != 401  # signed in
    client.cookies.clear()
    again = client.get(f"/api/auth/verify?token={token}&lang=en", follow_redirects=False)
    assert again.status_code == 303 and again.headers["location"] == "/?auth=expired"
    assert "set-cookie" not in again.headers
    assert client.get("/api/goal").status_code == 401


def test_a_magic_link_expires_after_15_minutes(
    client: TestClient, sink: SmtpSink, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.store

    token = _request_link(client, sink)
    real_now = app.store.now
    monkeypatch.setattr(app.store, "now", lambda: real_now() + timedelta(minutes=16))
    late = client.get(f"/api/auth/verify?token={token}", follow_redirects=False)
    assert late.status_code == 303 and late.headers["location"] == "/?auth=expired"
    assert "set-cookie" not in late.headers
    assert client.get("/api/goal").status_code == 401
    assert client.get("/api/auth/verify?token=not-a-token", follow_redirects=False).headers["location"] == "/?auth=expired"  # noqa: E501


def test_a_link_inside_its_15_minutes_still_works(
    client: TestClient, sink: SmtpSink, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.store

    token = _request_link(client, sink)
    real_now = app.store.now
    monkeypatch.setattr(app.store, "now", lambda: real_now() + timedelta(minutes=14))
    ok = client.get(f"/api/auth/verify?token={token}", follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/"


def test_three_links_per_email_then_silence(client: TestClient, sink: SmtpSink) -> None:
    for _ in range(3):
        _request_link(client, sink, "chen@example.com")
    # the fourth is still 202 (no account enumeration) but sends nothing and makes no link
    r = client.post("/api/auth/request-link", json={"email": "Chen@Example.com "})
    assert r.status_code == 202 and r.json() == {"status": "sent"}
    assert len(sink.messages) == 3
    # another address from the same IP is not held back by this one's limit
    _request_link(client, sink, "li@example.com")


def test_ten_links_per_ip_then_silence(client: TestClient, sink: SmtpSink) -> None:
    for i in range(10):
        _request_link(client, sink, f"owner{i}@example.com")
    r = client.post("/api/auth/request-link", json={"email": "owner10@example.com"})
    assert r.status_code == 202
    assert len(sink.messages) == 10


def test_an_invalid_email_is_422_and_sends_nothing(client: TestClient, sink: SmtpSink) -> None:
    assert client.post("/api/auth/request-link", json={"email": "not an email"}).status_code == 422
    assert sink.messages == []


def test_the_rate_limiter_window_slides(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import auth

    t = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: t[0])
    lim = auth.RateLimiter(limit=3, window_s=900)
    assert all(lim.allow("k") for _ in range(3))
    assert not lim.allow("k")
    t[0] += 899
    assert not lim.allow("k")  # still inside the window
    t[0] += 2
    assert lim.allow("k")  # the first three have left the window
    assert lim.allow("other")


# ------------------------------------------------------------------ email templates

CONTEXTS: dict[str, dict[str, Any]] = {
    "sign_in": {"url": "http://127.0.0.1:8000/api/auth/verify?token=T&lang=en"},
    "verify_email": {"url": "http://127.0.0.1:8000/api/auth/verify?token=V"},
    "welcome": {"url": "http://127.0.0.1:8000/", "goal_sentence": "Open in Tampines by Nov 2027",
                "next_step": "Ask WeBank for consent", "next_act_by": "3 Nov 2026"},
    "checkin": {"url": "http://127.0.0.1:8000/?checkin=g1", "quick_url": "http://127.0.0.1:8000/api/checkin/quick?token=Q"},  # noqa: E501
    "digest": {"url": "http://127.0.0.1:8000/", "status_line": "On plan", "next_step": "ODI filing",
               "next_act_by": "1 Dec 2026"},
    "alert": {"url": "http://127.0.0.1:8000/?alert=a1", "headline": "Your opening date moved", "act_by": "8 Dec 2026"},  # noqa: E501
    "milestone": {"url": "http://127.0.0.1:8000/", "step_label": "ODI filing", "act_by": "1 Dec 2026"},
}


def test_the_contexts_cover_every_template() -> None:
    from typing import get_args

    from app.email import sender

    assert set(CONTEXTS) == set(get_args(sender.Template)) == set(sender.SUBJECTS)


@pytest.mark.parametrize("lang", ["en", "zh"])
@pytest.mark.parametrize("template", sorted(CONTEXTS))
def test_each_template_renders_and_sends_through_smtp(
    template: str, lang: str, sink: SmtpSink, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.email import sender
    from app.store import Store

    monkeypatch.setenv("WAYPOINT_MAIL_FROM", "Waypoint <no-reply@waypoint.test>")
    store = Store(f"sqlite:///{tmp_path / 'mail.sqlite3'}")
    user = store.create_user("standalone", email="chen@example.com", verified=True, lang=lang)
    ctx = {"demo": True, **CONTEXTS[template]}
    assert sender.send(store, "chen@example.com", template, lang, ctx, user["id"])  # type: ignore[arg-type]
    [(rcpt, msg)] = sink.messages
    assert rcpt == ["chen@example.com"]
    assert msg["To"] == "chen@example.com" and "no-reply@waypoint.test" in msg["From"]
    assert msg["Subject"] == sender.SUBJECTS[template][lang]
    text, html = text_part(msg), html_part(msg)
    for value in CONTEXTS[template].values():  # every value the template is given reaches the text part
        assert value in text, (template, value)
    assert CONTEXTS[template]["url"].replace("&", "&amp;") in html
    assert "<html" in html.lower() and "{{" not in html and "{%" not in html + text
    assert not re.search(r"S\$|SGD|RMB|CNY|¥|元", text + html)  # no amounts unless the context carries them
    if lang == "zh":
        assert re.search(r"[一-鿿]", text)
    [logged] = store.emails_for(user["id"])
    assert logged["template"] == template and logged["delivered"] and logged["error"] is None
    assert logged["to_hash"] != "chen@example.com"  # the recipient is logged hashed


def test_a_send_that_cannot_reach_smtp_is_logged_as_not_delivered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.email import sender
    from app.store import Store

    with SmtpSink() as s:
        port = s.port  # a port that is closed once the sink stops
    monkeypatch.setenv("WAYPOINT_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("WAYPOINT_SMTP_PORT", str(port))
    store = Store(f"sqlite:///{tmp_path / 'mail.sqlite3'}")
    user = store.create_user("standalone", email="chen@example.com", verified=True, lang="en")
    assert not sender.send(store, "chen@example.com", "sign_in", "en", CONTEXTS["sign_in"], user["id"])
    [logged] = store.emails_for(user["id"])
    assert not logged["delivered"] and logged["error"]
