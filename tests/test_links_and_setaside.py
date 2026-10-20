"""Email links (`?checkin=`, `?alert=`) and the monthly set-aside as a prepared action (SPEC §7.4, §8.2)."""

from __future__ import annotations

import asyncio
from typing import Any

from agent.turn import Out
from agent.widgets import WidgetEvent
from tests.test_journey import Driver, _approve, _to_goal_plan, svc  # noqa: F401  (fixture re-export)


def _open(d: Driver, kind: str, value: str) -> list[Out]:
    """The web app's opening run with a link it read from its address."""
    orch = d.svc.orchestrator
    t = asyncio.run(orch.run_turn(d.state, text=None, event=None, init=True, link=(kind, value)))
    asyncio.run(d.svc.orchestrator.compose(t))
    d.outs = t.outputs
    d.svc.save_state(d.state)
    return d.outs


def _notices(d: Driver) -> list[str]:
    return [o.notice["code"] for o in d.outs if o.kind == "notice" and o.notice]


def _standalone_goal(svc: Any) -> Driver:  # noqa: F811
    d = Driver(svc, host_mode="standalone")
    d.run(init=True)
    d.reply("start")
    while d.state.pending is not None and d.state.pending.skill == "profile":
        opts = d.state.pending.options
        d.reply(opts[1]["value"] if len(opts) > 1 else opts[0]["value"])
    d.event("confirm_card", "confirm", "profile")
    d.reply("near_customers")
    d.reply(d.state.pending.options[0]["value"])  # type: ignore[union-attr]
    d.reply(d.state.pending.options[0]["value"])  # type: ignore[union-attr]
    d.reply("looks_right")
    d.reply("looks_good")
    if d.state.step == "funding":
        d.reply("add_savings")
        d.reply("v6")
        d.reply("looks_good")
    _approve(d)
    assert d.state.goal_id
    return d


def _audit(svc: Any, kind: str) -> list[dict[str, Any]]:  # noqa: F811
    import json

    return [r for r in map(json.loads, svc.audit.path.read_text().splitlines()) if r.get("kind") == kind]


# ------------------------------------------------------------------ the check-in email's "Something changed"


def test_checkin_link_opens_the_form_for_that_goal_and_period(svc: Any) -> None:  # noqa: F811
    from datetime import timedelta

    from agent.render import month_label
    from app import auth

    d = _standalone_goal(svc)
    gid = d.state.goal_id
    assert gid
    svc.advance(d.user, 4)  # the monthly check-in email goes out for week 4
    d.state = svc.load_state(d.user)
    email = [e for e in svc.store.emails_for(d.user["id"]) if e["template"] == "checkin"]
    assert email, "the check-in email was sent"
    _open(d, "checkin", auth.checkin_token(gid, "w4"))
    form = d.widgets("checkin_form")
    assert form and not _notices(d)
    assert form[0].payload.goal_id == gid and form[0].payload.period == "w4"
    start = svc.gk.goal(gid).start_date
    asked = start + timedelta(weeks=4)  # the week the email went out; it asks about the month before
    assert form[0].payload.period_label == month_label(asked - timedelta(weeks=4), 0, "en")
    assert d.state.step == "goal_keeper"
    assert _audit(svc, "email_link")[-1]["ok"] is True
    # answering it spends that period: the email's one-tap "on plan as usual" link no longer records
    d.run(event=WidgetEvent(widget_id=form[0].id, event="checkin",
                            data={"profit_cny": "150000", "set_aside_cny": "20000", "period": "w4"}))
    assert d.widgets("status_card")
    assert svc.gk.quick_checkin(gid, "w4") is False


def test_checkin_link_invalid_expired_or_someone_elses_shows_a_plain_notice(svc: Any) -> None:  # noqa: F811
    from app import auth

    d = _standalone_goal(svc)
    gid = d.state.goal_id
    assert gid
    tok = auth.checkin_token(gid, "w0")
    tampered = tok[:-2] + ("00" if tok[-2:] != "00" else "11")
    for bad in ("forged.sig", "no-dot", tampered, auth.checkin_token(gid, "w0", ttl_s=-1),
                auth.checkin_token("g_someone_else", "w0"), auth.checkin_token(gid, "w99")):
        _open(d, "checkin", bad)
        assert _notices(d) == ["link_invalid"], bad
        assert not d.widgets("checkin_form")
    _open(d, "checkin", "recorded")  # where the one-tap link lands
    assert _notices(d) == ["checkin_recorded"]
    other = Driver.__new__(Driver)  # a second owner, signed in, with no goal
    other.svc, other.outs = svc, []
    other.user = svc.store.create_user("standalone", email="other@example.test", verified=True)
    other.state = svc.load_state(other.user)
    _open(other, "checkin", tok)
    assert _notices(other) == ["link_invalid"] and other.widgets("consent_card") == []


# ------------------------------------------------------------------ the alert email's link


def test_alert_link_opens_that_alert_with_its_repairs(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_goal_plan(d)
    _approve(d)
    svc.advance(d.user, 4, scenario="sales_dip")
    for _ in range(3):
        svc.advance(d.user, 4)
    alerts = svc.store.alerts_for(d.state.goal_id)
    assert alerts and alerts[-1]["repairs"]
    d.state = svc.load_state(d.user)
    _open(d, "alert", alerts[-1]["id"])
    card = d.widgets("alert_card")
    assert card and card[0].payload.alert_id == alerts[-1]["id"]
    assert d.widgets("repair_options") and not _notices(d)
    _open(d, "alert", "a_does_not_exist")
    assert _notices(d) == ["link_invalid"] and not d.widgets("alert_card")


# ------------------------------------------------------------------ the monthly set-aside


def _goal_with_transfer(svc: Any) -> Driver:  # noqa: F811
    d = Driver(svc)
    _to_goal_plan(d)
    d.reply("add_transfer")
    _approve(d)
    assert d.state.goal_id
    return d


def _setaside_card(d: Driver) -> Any:
    cards = [w for w in d.widgets("approval_card") if w.payload.action == "recurring_setaside"]
    return cards[-1] if cards else None


def test_choosing_the_monthly_transfer_issues_one_prepared_action_card(svc: Any) -> None:  # noqa: F811
    from agent.render import money
    from mock_webank import feed as mw
    from mock_webank import instructions as MI

    d = _goal_with_transfer(svc)
    card = _setaside_card(d)
    assert card is not None, "a recurring_setaside card follows the approved goal"
    assert len(d.widgets("approval_card")) == 1, "one extra card, no more"
    goal = svc.gk.goal(d.state.goal_id)
    lines = {ln.label: ln.value for ln in card.payload.lines}
    assert lines["Each month"] == money(goal.setaside_monthly_cny, "CNY", "en")
    assert lines["Into"].endswith(mw.accounts(d.user["id"])["savings"][-4:])
    assert lines["First transfer"] == "1 Nov 2026"  # demo today is 19 Oct 2026
    assert MI.for_owner(d.user["id"]) == [], "nothing is prepared before the owner approves"

    d.event("approval_card", "approve", data={"card_hash": card.payload.card_hash})
    recs = MI.for_owner(d.user["id"])
    assert len(recs) == 1 and recs[0]["status"] == "pending_signature"
    assert recs[0]["terms"]["amount_cny"] == str(goal.setaside_monthly_cny)
    assert any(b.key == "setaside_prepared" for b in (o.beat for o in d.outs) if b is not None) or any(
        "setaside_prepared" in t for t in d.texts()
    )
    prepared = _audit(svc, "setaside_prepared")
    assert prepared and prepared[-1]["card_hash"] == card.payload.card_hash
    assert svc.gk.setaside_needed(d.state) is False, "not offered again while it covers the amount"

    # the owner signs in WeBank's own flow (simulated in the demo)
    signed = svc.gk.sign_setaside(d.user["id"], recs[0]["id"])
    assert signed is not None and signed["status"] == "signed"
    assert _audit(svc, "setaside_signed")[-1]["via"] == "webank_mock"
    assert svc.gk.sign_setaside(d.user["id"], recs[0]["id"]) is None, "signed already: can't sign twice"


def test_a_replayed_or_forged_setaside_card_is_refused(svc: Any) -> None:  # noqa: F811
    from mock_webank import instructions as MI

    d = _goal_with_transfer(svc)
    card = _setaside_card(d)
    wid = card.id
    # forged: a hash the server never issued
    d.run(event=WidgetEvent(widget_id=wid, event="approve", data={"card_hash": "0" * 64}))
    assert MI.for_owner(d.user["id"]) == []
    assert _audit(svc, "approval_refused")[-1]["reason"] == "hash_mismatch"
    fresh = _setaside_card(d)
    assert fresh is not None and fresh.id != wid, "an updated card follows"
    # the old card can't be used again
    d.run(event=WidgetEvent(widget_id=wid, event="approve", data={"card_hash": card.payload.card_hash}))
    assert MI.for_owner(d.user["id"]) == []
    # approve the fresh one, then replay it
    ev = WidgetEvent(widget_id=fresh.id, event="approve", data={"card_hash": fresh.payload.card_hash})
    d.run(event=ev)
    assert len(MI.for_owner(d.user["id"])) == 1
    d.run(event=ev)
    assert len(MI.for_owner(d.user["id"])) == 1, "a replay prepares nothing"
    assert _audit(svc, "approval_refused")[-1]["reason"] == "unknown_or_used_card"


def test_setaside_card_refuses_a_reused_nonce_or_changed_terms() -> None:
    from agent.approval import check_approval, new_card

    terms = {"amount_cny": "23000", "start_date": "2026-11-01"}
    card = new_card("recurring_setaside", "u1", terms, "w1")
    assert check_approval(card, card.card_hash, terms, set()).ok
    assert check_approval(card, card.card_hash, terms, {card.nonce}).reason == "nonce_reused"
    changed = {**terms, "amount_cny": "30000"}
    assert check_approval(card, card.card_hash, changed, set()).reason == "state_changed"


def test_r2_pause_holds_the_setaside_back(svc: Any) -> None:  # noqa: F811
    from mock_webank import feed as mw
    from mock_webank import instructions as MI
    from sim.shocks import above_normal_draw

    d = _goal_with_transfer(svc)
    card = _setaside_card(d)
    mw.add_shocks(d.user["id"], above_normal_draw(svc.today(), after_weeks=0))  # borrowing jumps today
    assert svc.gk.setaside_blockers(d.state) == ["R2"]
    d.event("approval_card", "approve", data={"card_hash": card.payload.card_hash})
    assert MI.for_owner(d.user["id"]) == [], "no set-aside is prepared while R2 pauses it"
    assert _audit(svc, "approval_refused")[-1]["rules"] == ["R2"]
    assert _audit(svc, "setaside_held")
    assert _setaside_card(d) is None


def test_r5_floor_holds_the_setaside_back(svc: Any) -> None:  # noqa: F811
    d = _goal_with_transfer(svc)
    rec = svc.store.goal(d.state.goal_id)
    rec["goal"]["floor_risk"] = "0.5"
    svc.store.save_goal(d.state.goal_id, d.user["id"], rec)
    assert "R5" in svc.gk.setaside_blockers(d.state)


def test_standalone_mode_gets_no_setaside_card(svc: Any) -> None:  # noqa: F811
    s = _standalone_goal(svc)
    s.state.goal_prefs["recurring_setaside"] = True  # not offered in standalone mode, even if set
    assert svc.gk.setaside_needed(s.state) is False


def test_signed_transfer_pauses_at_floor_plus_buffer_every_month(svc: Any) -> None:  # noqa: F811
    """Judge review 2026-10-20: the plan's set-aside stops at floor + buffer, but the instruction the owner
    signed paused only below the floor, checked once. Now the signed terms carry floor + buffer, the bank
    checks it before every monthly transfer, and the card says so."""
    from agent.render import money
    from mock_webank import feed as mw
    from mock_webank import instructions as MI
    from tools.funding import safety_floor

    d = _goal_with_transfer(svc)
    card = _setaside_card(d)
    goal = svc.gk.goal(d.state.goal_id)
    fl = safety_floor(mw.get_feed(d.user["id"], svc.today()))
    assert fl is not None and goal.funding.buffer_cny == fl.buffer_cny
    keep = fl.floor_cny + fl.buffer_cny
    terms = svc.gk.setaside_terms(d.state)
    assert terms["pause_below_cny"] == str(keep) and terms["checked"] == "before_each_transfer"
    lines = {ln.label: ln.value for ln in card.payload.lines}
    assert money(keep, "CNY", "en") in lines["Pauses"] and "each transfer" in lines["Pauses"]
    # approval day: home cash sits at floor + buffer once the spare cash is in the pot; that is not a hold
    assert svc.gk.setaside_blockers(d.state) == []
    d.event("approval_card", "approve", data={"card_hash": card.payload.card_hash})
    recs = MI.for_owner(d.user["id"])
    assert recs and recs[0]["terms"]["pause_below_cny"] == str(keep)
