"""HTTP hardening (app/security.py, docs/SECURITY.md): security headers, the same-origin check on
state-changing requests, the upload cap enforced while the body streams in, per-user rate limits."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent.reader import MAX_BYTES
from app import security

PNG = (Path(__file__).resolve().parents[1] / "data" / "demo" / "docs" / "fitout_quote.png").read_bytes()
AGUI = {"threadId": "t", "runId": "r", "state": {}, "messages": [], "tools": [], "context": [],
        "forwardedProps": {"init": True}}


@pytest.fixture()
def main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("WAYPOINT_VAR", str(tmp_path))
    monkeypatch.setenv("WAYPOINT_DB_URL", f"sqlite:///{tmp_path / 'sec.sqlite3'}")
    monkeypatch.setenv("WAYPOINT_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("WAYPOINT_SMTP_PORT", "1")
    monkeypatch.setenv("WAYPOINT_DEMO", "1")
    monkeypatch.setenv("WAYPOINT_BASE_URL", "https://waypoint.example")
    import app.main
    import app.store

    importlib.reload(app.store)
    importlib.reload(app.main)
    return app.main


@pytest.fixture()
def client(main: Any) -> Iterator[TestClient]:
    with TestClient(main.app, base_url="https://waypoint.example", headers={"origin": "https://waypoint.example"}) as c:  # noqa: E501
        yield c


def _sign_in(c: TestClient) -> None:
    tok = c.get("/api/demo/sso-token").json()["token"]
    assert c.post("/api/auth/webank-sso", json={"token": tok}).status_code == 200


# ------------------------------------------------------------------ headers


def _assert_hardened(resp: Any) -> None:
    csp = resp.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "script-src 'self';" in csp and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert "https://www.onemap.gov.sg" in csp
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "microphone=(self)" in resp.headers["permissions-policy"]
    assert "geolocation=()" in resp.headers["permissions-policy"]


def test_every_response_carries_the_security_headers(client: TestClient) -> None:
    for resp in (
        client.get("/api/health"),                                          # JSON
        client.get("/api/goal"),                                            # 401
        client.post("/api/auth/logout", headers={"origin": "https://evil.example"}),  # our own 403
        client.get("/api/checkin/quick", params={"token": "x.y"}, follow_redirects=False),  # redirect
    ):
        _assert_hardened(resp)
    # served over HTTPS (WAYPOINT_BASE_URL), so browsers are told to stay on HTTPS
    assert client.get("/api/health").headers["strict-transport-security"].startswith("max-age=")


def test_the_streamed_chat_carries_the_headers_too(client: TestClient) -> None:
    _sign_in(client)
    resp = client.post("/api/agui", json=AGUI, headers={"accept": "text/event-stream"})
    assert resp.status_code == 200
    _assert_hardened(resp)


def test_swagger_page_gets_its_own_policy_and_the_app_keeps_the_strict_one(client: TestClient) -> None:
    docs = client.get("/api/docs")
    assert docs.status_code == 200 and "cdn.jsdelivr.net" in docs.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in docs.headers["content-security-policy"]
    assert "cdn.jsdelivr.net" not in client.get("/api/health").headers["content-security-policy"]


# ------------------------------------------------------------------ CSRF


def test_state_changing_requests_from_another_origin_are_refused(client: TestClient, main: Any) -> None:
    _sign_in(client)
    evil = {"origin": "https://evil.example"}
    assert client.post("/api/agui", json=AGUI, headers=evil).status_code == 403
    assert client.patch("/api/account", json={"lang": "zh"}, headers=evil).status_code == 403
    r = client.delete("/api/account", headers=evil)
    assert r.status_code == 403 and r.json() == {"detail": "cross_origin_request"}
    assert client.post("/api/upload", files={"file": ("q.png", PNG, "image/png")}, headers=evil).status_code == 403  # noqa: E501
    assert client.get("/api/account").status_code == 200  # still signed in, nothing deleted
    assert client.get("/api/account").json()["lang"] == "en"


def test_origin_null_and_requests_with_neither_origin_nor_referer_are_refused(main: Any) -> None:
    with TestClient(main.app, base_url="https://waypoint.example") as bare:
        tok = bare.get("/api/demo/sso-token").json()["token"]
        assert bare.post("/api/auth/webank-sso", json={"token": tok}).status_code == 403
        assert bare.post("/api/auth/webank-sso", json={"token": tok}, headers={"origin": "null"}).status_code == 403  # noqa: E501
        # Referer from our own page is enough when Origin is absent; a foreign one is not
        ok = bare.post("/api/auth/webank-sso", json={"token": tok},
                       headers={"referer": "https://waypoint.example/#chat"})
        assert ok.status_code == 200
        foreign = {"referer": "https://waypoint.example.evil.example/"}
        assert bare.post("/api/auth/logout", headers=foreign).status_code == 403


def test_dev_origins_are_allowed_and_safe_methods_and_the_signed_link_need_no_origin(main: Any) -> None:
    with TestClient(main.app, base_url="https://waypoint.example") as c:
        for o in ("http://127.0.0.1:5173", "http://localhost:8000", "https://WAYPOINT.example:443"):
            assert c.post("/api/auth/logout", headers={"origin": o}).status_code == 200, o
        assert c.get("/api/health").status_code == 200
        r = c.get("/api/checkin/quick", params={"token": "bad.sig"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/?checkin=expired"


def test_allowed_origins_reads_the_base_url_and_the_extra_list() -> None:
    got = security.allowed_origins("https://app.example/path", extra="https://a.example, ftp://x, ")
    assert {"https://app.example", "https://a.example", "http://127.0.0.1:5173"} <= got
    assert not any(o.startswith("ftp") for o in got)
    assert "http://localhost:8200" in security.allowed_origins("http://127.0.0.1:8200", extra="")
    assert "http://localhost:8200" not in security.allowed_origins("https://app.example", extra="")
    assert security.origin_of("null") is None and security.origin_of("http://h:80/x") == "http://h"


# ------------------------------------------------------------------ upload size


def test_an_oversized_upload_is_refused_from_its_declared_length(client: TestClient) -> None:
    _sign_in(client)
    big = b"\x89PNG\r\n\x1a\n" + b"\0" * (MAX_BYTES + security.MULTIPART_SLACK)
    r = client.post("/api/upload", files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413 and r.json()["detail"] == "too_large"


def test_a_file_just_over_10_mb_is_refused_by_the_chunked_read(client: TestClient) -> None:
    _sign_in(client)
    big = b"\x89PNG\r\n\x1a\n" + b"\0" * (MAX_BYTES - 7)  # MAX_BYTES + 1, under the body cap's slack
    r = client.post("/api/upload", files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 413 and r.json()["detail"] == "too_large"


def test_a_body_without_a_length_is_cut_off_while_streaming_not_after() -> None:
    """At the ASGI level: no Content-Length, chunks keep coming; the middleware stops pulling them
    as soon as the cap is passed and answers 413, so the rest is never read into memory or disk."""
    reached_app: list[bool] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        reached_app.append(True)
        while (await receive()).get("more_body"):
            pass

    chunk = b"x" * (1024 * 1024)
    pulled = 0

    async def receive() -> dict[str, Any]:
        nonlocal pulled
        pulled += 1
        return {"type": "http.request", "body": chunk, "more_body": pulled < 1000}

    sent: list[dict[str, Any]] = []

    async def send(m: dict[str, Any]) -> None:
        sent.append(m)

    mw = security.Hardening(app, origins=frozenset({"https://w.example"}), body_limits={"/api/upload": 3 * len(chunk)})  # noqa: E501
    scope = {"type": "http", "method": "POST", "path": "/api/upload", "headers": [(b"origin", b"https://w.example")]}  # noqa: E501
    with pytest.raises(Exception) as exc:  # the bare app has no exception handler; FastAPI's turns it into 413  # noqa: E501
        asyncio.run(mw(scope, receive, send))
    assert getattr(exc.value, "status_code", None) == 413
    assert reached_app and pulled == 4  # 4 MB pulled of a 1000 MB body


def test_a_real_quote_still_uploads_and_wrong_magic_bytes_are_still_refused(client: TestClient) -> None:
    _sign_in(client)
    assert client.post("/api/upload", files={"file": ("q.png", PNG, "image/png")}).status_code == 200
    fake = client.post("/api/upload", files={"file": ("q.png", b"<html>not a png</html>", "image/png")})
    assert fake.status_code == 422 and fake.json()["detail"] == "unsupported_type"


# ------------------------------------------------------------------ rate limits


def test_the_chat_is_rate_limited_per_user_with_a_plain_notice(
    client: TestClient, main: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "chat_rate", security.UserRateLimit("Too many messages.", (2, 60)))
    _sign_in(client)
    for _ in range(2):
        assert client.post("/api/agui", json=AGUI).status_code == 200
    r = client.post("/api/agui", json=AGUI)
    assert r.status_code == 429 and r.json()["detail"] == "Too many messages."
    assert 1 <= int(r.headers["retry-after"]) <= 60
    _assert_hardened(r)
    # another owner is not affected
    with TestClient(main.app, base_url="https://waypoint.example", headers={"origin": "https://waypoint.example"}) as other:  # noqa: E501
        tok = main.auth.sso_token("webank:someone-else")
        assert other.post("/api/auth/webank-sso", json={"token": tok}).status_code == 200
        assert other.post("/api/agui", json=AGUI).status_code == 200


def test_uploads_are_rate_limited_per_user(client: TestClient, main: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: E501
    monkeypatch.setattr(main, "upload_rate", security.UserRateLimit("Too many uploads.", (1, 600)))
    _sign_in(client)
    assert client.post("/api/upload", files={"file": ("q.png", PNG, "image/png")}).status_code == 200
    r = client.post("/api/upload", files={"file": ("q.png", PNG, "image/png")})
    assert r.status_code == 429 and r.json()["detail"] == "Too many uploads."


def test_the_default_limits_leave_room_for_a_person() -> None:
    import app.main as m

    assert m.chat_rate.limiters[0].limit >= 20 and m.chat_rate.limiters[0].window == 60
    assert m.upload_rate.limiters[0].limit >= 10


def test_a_placeholder_sso_secret_is_refused_outside_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import auth

    monkeypatch.setenv("WAYPOINT_SSO_SECRET", "change-me")
    monkeypatch.setenv("WAYPOINT_DEMO", "0")
    with pytest.raises(RuntimeError, match="placeholder"):
        auth._sso_secret()
    monkeypatch.setenv("WAYPOINT_DEMO", "1")
    assert auth._sso_secret() != "change-me", "demo mode swaps a placeholder for a random secret"
    monkeypatch.setenv("WAYPOINT_SSO_SECRET", "")
    assert len(auth._sso_secret()) == 64, "blank: a random one per process"
    monkeypatch.setenv("WAYPOINT_SSO_SECRET", "a-long-operator-chosen-value-0123456789")
    monkeypatch.setenv("WAYPOINT_DEMO", "0")
    assert auth._sso_secret() == "a-long-operator-chosen-value-0123456789"


def test_env_example_leaves_the_sso_secret_blank_and_says_demo_is_for_local_judging() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "\nWAYPOINT_SSO_SECRET=\n" in text, "blank: the app generates a random one"
    assert "WAYPOINT_DEMO=1" in text and "local judging only" in text
