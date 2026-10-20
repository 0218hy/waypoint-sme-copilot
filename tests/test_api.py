"""The HTTP surface: auth, the AG-UI stream (cards first, words fill their slots), REST guards."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("WAYPOINT_VAR", str(tmp_path))
    monkeypatch.setenv("WAYPOINT_DB_URL", f"sqlite:///{tmp_path / 'api.sqlite3'}")
    monkeypatch.setenv("WAYPOINT_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("WAYPOINT_SMTP_PORT", "1")
    monkeypatch.setenv("WAYPOINT_DEMO", "1")
    import app.main
    import app.store

    importlib.reload(app.store)
    importlib.reload(app.main)
    # a browser sends Origin on every POST/PATCH/DELETE; the CSRF check requires it (tests/test_security.py)
    with TestClient(app.main.app, headers={"origin": app.main.BASE_URL}) as c:
        yield c


def _events(resp: Any) -> list[dict[str, Any]]:
    out = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def _sign_in(c: TestClient) -> None:
    tok = c.get("/api/demo/sso-token").json()["token"]
    assert c.post("/api/auth/webank-sso", json={"token": tok}).status_code == 200


def _run(c: TestClient, **fp: Any) -> list[dict[str, Any]]:
    body = {"threadId": "t", "runId": "r", "state": {}, "messages": [], "tools": [], "context": [],
            "forwardedProps": fp}
    return _events(c.post("/api/agui", json=body, headers={"accept": "text/event-stream"}))


def test_requires_sign_in(client: TestClient) -> None:
    assert client.post("/api/agui", json={"threadId": "t", "runId": "r", "state": {}, "messages": [],
                                          "tools": [], "context": [], "forwardedProps": {}}).status_code == 401  # noqa: E501
    assert client.get("/api/goal").status_code == 401


def test_cards_stream_before_words_and_words_fill_their_slots(client: TestClient) -> None:
    _sign_in(client)
    evs = _run(client, init=True)
    types = [e["type"] for e in evs]
    assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED"
    slots = [e["value"]["id"] for e in evs if e["type"] == "CUSTOM" and e["name"] == "waypoint.text_slot"]
    texts = [e["messageId"] for e in evs if e["type"] == "TEXT_MESSAGE_START"]
    widgets = [i for i, e in enumerate(evs) if e["type"] == "TOOL_CALL_START"]
    assert slots and set(texts) == set(slots)
    first_text = next(i for i, e in enumerate(evs) if e["type"] == "TEXT_MESSAGE_START")
    assert all(w < first_text for w in widgets), "every card arrives before the model's words"


def test_widget_event_round_trip_and_transcript_order(client: TestClient) -> None:
    _sign_in(client)
    evs = _run(client, init=True)
    consent = next(e for e in evs if e["type"] == "TOOL_CALL_START" and e["toolCallName"] == "consent_card")
    evs = _run(client, widget_event={"widget_id": consent["toolCallId"], "event": "consent", "value": True})
    assert any(e["type"] == "TOOL_CALL_START" and e["toolCallName"] == "profile_card" for e in evs)
    snap = _run(client, init=True)[1]
    assert snap["type"] == "MESSAGES_SNAPSHOT"
    roles = [m["role"] for m in snap["messages"]]
    assert roles.count("assistant") >= 4


def test_preview_and_demo_guards(client: TestClient) -> None:
    _sign_in(client)
    assert client.get("/api/preview/setaside", params={"share": 1.5}).status_code == 422
    assert client.post("/api/demo/advance", json={"weeks": 4, "scenario": "rob_a_bank"}).status_code == 422
    assert client.get("/api/health").json()["ok"] is True


def test_one_tap_checkin_link_is_signed_and_single_use(client: TestClient) -> None:
    from app import auth

    assert client.get("/api/checkin/quick", params={"token": "forged.sig"}, follow_redirects=False).headers[
        "location"].endswith("expired")
    tok = auth.checkin_token("g_missing", "2026-11")
    tampered = tok[:-2] + ("00" if tok[-2:] != "00" else "11")
    assert client.get("/api/checkin/quick", params={"token": tampered}, follow_redirects=False).headers[
        "location"].endswith("expired")


def test_state_is_saved_before_the_ui_hears_of_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.main as m

    _sign_in(client)
    seen: list[str] = []
    real_save, real_compose = m.services.save_state, m.services.orchestrator.compose

    def save(state: Any) -> None:
        seen.append("save")
        real_save(state)

    async def compose(turn: Any) -> None:
        seen.append("compose")
        await real_compose(turn)

    monkeypatch.setattr(m.services, "save_state", save)
    monkeypatch.setattr(m.services.orchestrator, "compose", compose)
    _run(client, init=True)
    assert seen and seen[0] == "save" and seen.index("save") < seen.index("compose")


def test_webank_sign_in_carries_the_contact_email_for_reminders(client: TestClient) -> None:
    _sign_in(client)
    acc = client.get("/api/account").json()
    assert acc["email"] and acc["host_mode"] == "embedded", "reminders need somewhere to go"


def test_a_new_account_starts_in_the_language_picked_on_the_sign_in_page(client: TestClient) -> None:
    tok = client.get("/api/demo/sso-token").json()["token"]
    assert client.post("/api/auth/webank-sso", json={"token": tok, "lang": "zh"}).status_code == 200
    assert client.get("/api/account").json()["lang"] == "zh"
    evs = _run(client, init=True)
    assert any(e["type"] == "STATE_SNAPSHOT" and e["snapshot"].get("lang") == "zh" for e in evs)


def test_an_owner_can_get_a_checkable_proof_of_their_audit_records(client: TestClient) -> None:
    from agent import audit as A

    _sign_in(client)
    evs = _run(client, init=True)
    consent = next(e for e in evs if e["type"] == "TOOL_CALL_START" and e["toolCallName"] == "consent_card")
    _run(client, widget_event={"widget_id": consent["toolCallId"], "event": "consent", "value": True})
    p = client.get("/api/audit/proof").json()
    assert p["chain_intact"] and p["records"] and p["head"]["seq"] >= p["records"][-1]["seq"]
    assert all(r["owner"] == p["records"][0]["owner"] for r in p["records"]), "only this owner's records"
    assert A.check_proof(p)[0]
    p["records"][0]["kind"] = "edited"
    assert not A.check_proof(p)[0], "an edited record no longer matches its hash"
    assert "audit_proof" in client.get("/api/account/export").json()


def test_an_email_link_is_checked_on_the_server_and_a_bad_one_is_a_plain_notice(client: TestClient) -> None:
    _sign_in(client)
    _run(client, init=True)
    evs = _run(client, email_link={"kind": "checkin", "value": "forged.sig"})
    notices = [e["value"] for e in evs if e["type"] == "CUSTOM" and e["name"] == "waypoint.notice"]
    assert notices == [{"code": "link_invalid", "retry": False}]
    assert not any(e["type"] == "TOOL_CALL_START" and e["toolCallName"] == "checkin_form" for e in evs)
    evs = _run(client, email_link={"kind": "alert", "value": "a_nope"})
    assert [e["value"]["code"] for e in evs if e["type"] == "CUSTOM" and e["name"] == "waypoint.notice"] == [
        "link_invalid"
    ]
    # anything else is not a link: ignored
    evs = _run(client, email_link={"kind": "reset_password", "value": "x"})
    assert not [e for e in evs if e["type"] == "CUSTOM" and e["name"] == "waypoint.notice"]


def test_the_mock_webank_signing_step_is_demo_only_and_signs_only_what_is_pending(client: TestClient) -> None:
    _sign_in(client)
    assert client.get("/api/demo/webank").json() == {"instructions": [], "simulated": True}
    assert client.post("/api/demo/webank/sign", json={"instruction_id": "si_nope"}).status_code == 409


def test_setaside_preview_before_a_plan_is_409_not_500(client: TestClient) -> None:
    _sign_in(client)
    _run(client, init=True)
    r = client.get("/api/preview/setaside", params={"share": 0.3})
    assert r.status_code == 409 and r.json()["detail"].startswith("no_plan_yet")


def test_one_tap_checkin_get_changes_nothing_and_the_button_posts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.main
    from app import auth

    calls: list[tuple[str, str]] = []

    def fake(goal_id: str, period: str) -> bool:
        if goal_id == "g_gone":
            raise KeyError(goal_id)
        calls.append((goal_id, period))
        return calls.count((goal_id, period)) == 1

    monkeypatch.setattr(app.main.services.gk, "quick_checkin", fake)
    tok = auth.checkin_token("g_1", "w4")
    page = client.get("/api/checkin/quick", params={"token": tok}, follow_redirects=False)
    assert page.status_code == 200 and calls == [], "opening the link (or a mail scanner) records nothing"
    assert 'method="post"' in page.text and 'action="/api/checkin/quick"' in page.text
    assert f'name="token" value="{tok}"' in page.text and "<script" not in page.text
    assert page.headers["cache-control"] == "no-store"
    origin = {"origin": app.main.BASE_URL}
    r = client.post("/api/checkin/quick", data={"token": tok}, headers=origin, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?checkin=recorded" and calls == [("g_1", "w4")]
    r = client.post("/api/checkin/quick", data={"token": tok}, headers=origin, follow_redirects=False)
    assert r.headers["location"] == "/?checkin=already", "single use per period"
    foreign = client.post("/api/checkin/quick", data={"token": tok}, headers={"origin": "https://evil.example"})
    assert foreign.status_code == 403 and len(calls) == 2
    bad = client.post("/api/checkin/quick", data={"token": "x.y"}, headers=origin, follow_redirects=False)
    assert bad.headers["location"] == "/?checkin=expired"
    gone = auth.checkin_token("g_gone", "w4")
    r = client.post("/api/checkin/quick", data={"token": gone}, headers=origin, follow_redirects=False)
    assert r.headers["location"] == "/?checkin=expired"


def test_a_malformed_widget_event_is_a_422_with_a_plain_notice(client: TestClient) -> None:
    _sign_in(client)
    _run(client, init=True)
    for bad in ({"widget_id": 5}, {"event": "consent"}, "not an object"):
        body = {"threadId": "t", "runId": "r", "state": {}, "messages": [], "tools": [], "context": [],
                "forwardedProps": {"widget_event": bad}}
        r = client.post("/api/agui", json=body, headers={"accept": "text/event-stream"})
        assert r.status_code == 422, (bad, r.status_code)
        assert r.json()["detail"] == "invalid_widget_event" and "tap the card again" in r.json()["notice"]
