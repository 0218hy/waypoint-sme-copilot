"""Goal Keeper pieces of SPEC §7.2–§7.4: the weekly scheduler (idempotent per goal and period),
marking milestones done (a real step, legal order, money steps confirmed), and the milestone drafts
(the consent request grounded in code facts; checklists from data with sources)."""

from __future__ import annotations

import re
import time
from collections import Counter
from datetime import date
from typing import Any

import pytest

from agent.widgets import WidgetEvent
from tests.test_journey import Driver, _approve, _to_goal_plan, svc  # noqa: F401  (fixture re-export)


def _goal(d: Driver) -> None:
    _to_goal_plan(d)
    _approve(d)
    assert d.state.goal_id


def _emails(s: Any, d: Driver) -> Counter[str]:
    return Counter(e["template"] for e in s.store.emails_for(d.user["id"]))


def _period_emails(s: Any, d: Driver) -> int:
    """Emails that use a period: the digest, or the alert that replaces it that week."""
    c = _emails(s, d)
    return c["digest"] + c["alert"]


def _set_frequency(s: Any, d: Driver, freq: str) -> None:
    s.gk.update_prefs(d.state.goal_id, {"checkin_frequency": freq})


# ------------------------------------------------------------------ 1. the weekly scheduler


def test_weekly_job_is_idempotent_per_week_with_a_fake_clock(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _goal(d)
    gid = d.state.goal_id
    assert svc.run_scheduled() == {"checks": 0, "emails": 0}, "week 0: the goal was just checked and welcomed"
    svc.store.advance_clock(1)  # the fake clock: today moves, nothing runs
    assert svc.run_scheduled()["checks"] == 1
    n = len(svc.store.checkins_for(gid))
    for _ in range(3):  # a repeated run in the same week does nothing
        assert svc.run_scheduled() == {"checks": 0, "emails": 0}
    assert len(svc.store.checkins_for(gid)) == n


def _quiet_checks(s: Any, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Stub the plan check (no alerts) to look at the email cadence alone; returns the weeks checked."""
    weeks: list[int] = []

    def check(goal_id: str, state: Any, owner_numbers: Any = None) -> Any:
        goal = s.gk.goal(goal_id)
        weeks.append(s.gk.elapsed(goal))
        return goal, None, {}

    monkeypatch.setattr(s.gk, "check", check)
    return weeks


def test_emails_follow_the_chosen_frequency_and_never_double_send(svc: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811, E501
    d = Driver(svc)
    _goal(d)
    weeks = _quiet_checks(svc, monkeypatch)
    _set_frequency(svc, d, "monthly")
    base = _period_emails(svc, d)
    for week in range(1, 4):  # monthly = every four weeks
        svc.store.advance_clock(1)
        svc.run_scheduled()
        assert _period_emails(svc, d) == base, f"no digest in week {week}"
    svc.store.advance_clock(1)
    svc.run_scheduled()
    svc.run_scheduled()
    assert _period_emails(svc, d) == base + 1

    _set_frequency(svc, d, "fortnightly")
    svc.store.advance_clock(1)
    svc.run_scheduled()
    assert _period_emails(svc, d) == base + 1
    svc.store.advance_clock(1)
    svc.run_scheduled()
    svc.run_scheduled()
    assert _period_emails(svc, d) == base + 2

    _set_frequency(svc, d, "weekly")
    svc.store.advance_clock(1)
    svc.run_scheduled()
    svc.run_scheduled()
    assert _period_emails(svc, d) == base + 3
    assert weeks == list(range(1, 8)), "one check per week, whatever the email frequency"


def test_an_alert_is_emailed_at_once_and_only_once(svc: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811, E501
    from datetime import UTC, datetime

    from tools.models import Alert, GoalStatus

    d = Driver(svc)
    _goal(d)
    _set_frequency(svc, d, "monthly")

    def check(goal_id: str, state: Any, owner_numbers: Any = None) -> Any:
        goal = svc.gk.goal(goal_id)
        alert = Alert(
            id=f"a_test{svc.gk.elapsed(goal)}", goal_id=goal_id, created_at=datetime.now(UTC), kind="date_slip",  # noqa: E501
            status_before=GoalStatus.ON_TRACK, status_after=GoalStatus.AT_RISK,
        )
        svc.store.save_alert(alert.id, goal_id, alert.model_dump(mode="json"))
        return goal, alert, {}

    monkeypatch.setattr(svc.gk, "check", check)
    svc.store.advance_clock(1)
    assert svc.run_scheduled() == {"checks": 1, "emails": 1}, "an alert doesn't wait for the monthly email"
    assert svc.run_scheduled() == {"checks": 0, "emails": 0}
    assert _emails(svc, d)["alert"] == 1
    assert svc.load_state(d.user).last_alert_id == "a_test1"


def test_a_missed_run_catches_up_once(svc: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    d = Driver(svc)
    _goal(d)
    _quiet_checks(svc, monkeypatch)
    _set_frequency(svc, d, "weekly")
    svc.store.advance_clock(5)  # the server was down for five weeks
    assert svc.run_scheduled() == {"checks": 1, "emails": 1}
    assert svc.run_scheduled() == {"checks": 0, "emails": 0}
    assert _period_emails(svc, d) == 1


def test_standalone_checkin_email_has_a_fresh_one_tap_link_each_period(svc: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811, E501
    from app.email import sender

    sent: list[dict[str, Any]] = []
    real = sender.send

    def spy(store: Any, to: str, template: str, lang: str, ctx: dict[str, Any], user_id: str | None = None) -> Any:  # noqa: E501
        if template == "checkin":
            sent.append(ctx)
        return real(store, to, template, lang, ctx, user_id)

    monkeypatch.setattr(sender, "send", spy)
    d = Driver(svc, host_mode="standalone")
    d.run(init=True)
    while d.state.step == "welcome" and d.state.pending is not None:
        d.reply(d.state.pending.options[0]["value"])
    while d.state.pending is not None and d.state.pending.skill == "profile":
        d.reply(d.state.pending.options[-1]["value"])
    d.event("confirm_card", "confirm", "profile")
    d.reply("near_customers")
    d.reply(d.state.pending.options[0]["value"])  # type: ignore[union-attr]
    d.reply(d.state.pending.options[0]["value"])  # type: ignore[union-attr]
    d.reply("looks_right")
    d.reply("looks_good")
    _approve(d)
    assert d.state.goal_id and not d.state.consent_feed
    _set_frequency(svc, d, "fortnightly")
    gid = d.state.goal_id
    for _ in range(4):
        svc.store.advance_clock(1)
        assert svc.run_scheduled()["checks"] == 0  # standalone: the check runs when the owner answers
        svc.run_scheduled()
    assert len(sent) == 2, "one check-in email per fortnight"
    links = {c["quick_url"] for c in sent}
    assert len(links) == 2, "each period has its own single-use link"
    from app import auth

    periods = [auth.verify_checkin(u.split("token=", 1)[1]) for u in links]
    assert all(p is not None and p[0] == gid for p in periods)
    assert svc.gk.quick_checkin(gid, periods[0][1])  # type: ignore[index]
    assert not svc.gk.quick_checkin(gid, periods[0][1])  # type: ignore[index]


def test_demo_clock_runs_the_same_job(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _goal(d)
    out = svc.advance(d.user, 2)
    assert out["checks"] == 1
    assert svc.run_scheduled() == {"checks": 0, "emails": 0}


def test_scheduler_setting_and_apscheduler_run(svc: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    from app import scheduler as weekly

    monkeypatch.delenv("WAYPOINT_SCHEDULER", raising=False)
    assert not weekly.enabled(demo=False), "off under tests"
    assert not weekly.enabled(demo=True)
    monkeypatch.setenv("WAYPOINT_SCHEDULER", "1")
    assert weekly.enabled(demo=True)
    monkeypatch.setenv("WAYPOINT_SCHEDULER", "0")
    assert not weekly.enabled(demo=False)

    d = Driver(svc)
    _goal(d)
    svc.store.advance_clock(1)
    sch = weekly.WeeklyScheduler(svc, minutes=60)
    sch.start()
    try:
        deadline = time.monotonic() + 20
        while sch.last_run is None and time.monotonic() < deadline:  # the first tick runs at start
            time.sleep(0.05)
        assert sch.last_run == {"checks": 1, "emails": 0}
        sch.last_run = None
        sch.run_now()  # triggered manually: nothing new is due
        deadline = time.monotonic() + 20
        while sch.last_run is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert sch.last_run == {"checks": 0, "emails": 0}
    finally:
        sch.shutdown()
    assert not sch.running


# ------------------------------------------------------------------ 2. marking milestones done


def _timeline() -> list[Any]:
    from tools import timeline as TL
    from tools.models import PlanResult

    weeks = {
        "lender_consent": 3, "odi_filing": 8, "bank_registration": 11, "incorporate": 18, "setup_transfer": 18,  # noqa: E501
        "first_transfer": 30, "sign_lease": 32, "hiring": 38, "fitout": 42, "licence": 45, "opening": 46,
    }
    res = PlanResult.model_construct(milestone_weeks=weeks, open_likely_week=46)
    return TL.build_timeline(res)


def test_only_a_real_milestone_in_legal_order_can_be_marked_done() -> None:
    from tools import timeline as TL

    ms = _timeline()
    on = date(2026, 11, 2)
    assert TL.can_mark_done(ms, "not_a_step") == (False, "unknown", [])
    assert TL.can_mark_done(ms, "odi_filing") == (False, "out_of_order", ["lender_consent"])
    with pytest.raises(ValueError):
        TL.mark_done(ms, "bank_registration", on)
    ms = TL.mark_done(ms, "lender_consent", on)
    assert next(m for m in ms if m.id == "lender_consent").done_at == on
    assert TL.can_mark_done(ms, "lender_consent")[1] == "already_done"
    for mid in ("odi_filing", "bank_registration", "incorporate", "setup_transfer", "first_transfer", "sign_lease"):  # noqa: E501
        ms = TL.mark_done(ms, mid, on)
    # hiring and the fit-out both follow the lease and run in parallel; opening needs both branches
    assert TL.can_mark_done(ms, "hiring")[0] and TL.can_mark_done(ms, "fitout")[0]
    ms = TL.mark_done(ms, "fitout", on)
    ms = TL.mark_done(ms, "licence", on)
    assert TL.can_mark_done(ms, "opening") == (False, "out_of_order", ["hiring"])
    ms = TL.mark_done(TL.mark_done(ms, "hiring", on), "opening", on)
    assert TL.next_open(ms) is None


def test_money_steps_are_flagged_and_a_rebuilt_timeline_keeps_done_steps() -> None:
    from tools import timeline as TL

    assert {m.id for m in _timeline() if TL.is_money_step(m.id)} == {"setup_transfer", "first_transfer", "opening"}  # noqa: E501
    done = TL.mark_done(_timeline(), "lender_consent", date(2026, 11, 2))
    rebuilt = TL.carry_done(done, _timeline())
    assert next(m for m in rebuilt if m.id == "lender_consent").done_at == date(2026, 11, 2)


def _timeline_widget(d: Driver) -> Any:
    return d.widgets("milestone_timeline")[-1]


def test_tap_marks_a_step_done_ticks_it_and_moves_the_next_step(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _goal(d)
    tl = _timeline_widget(d)
    assert tl.payload.step == "goal_keeper"
    can = {i.id: i.can_mark_done for i in tl.payload.items}
    assert can["lender_consent"] and not can["odi_filing"], "only the first step is markable at the start"
    d.event("milestone_timeline", "mark_milestone_done", "odi_filing")  # out of order
    goal = svc.gk.goal(d.state.goal_id)
    assert all(m.done_at is None for m in goal.milestones)
    assert any("out of order" in x for x in d.texts())
    d.event("milestone_timeline", "mark_milestone_done", "lender_consent")
    goal = svc.gk.goal(d.state.goal_id)
    assert next(m for m in goal.milestones if m.id == "lender_consent").done_at == svc.today()
    items = {i.id: i for i in _timeline_widget(d).payload.items}
    assert items["lender_consent"].status == "done" and items["lender_consent"].done_date
    assert items["odi_filing"].can_mark_done
    dash = svc.goal_dashboard(svc.load_state(d.user))
    assert dash["goal"]["next_step"]["id"] == "odi_filing"
    gtl = next(w for w in dash["widgets"] if w["payload"]["type"] == "milestone_timeline")["payload"]
    assert next(i for i in gtl["items"] if i["id"] == "lender_consent")["status"] == "done"
    assert not any(i["can_mark_done"] for i in gtl["items"]), "the Goal tab is read-only"
    d.event("milestone_timeline", "mark_milestone_done", "lender_consent")  # again
    assert any("already done" in x for x in d.texts())


def test_a_money_step_needs_the_owners_confirmation(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _goal(d)
    for mid in ("lender_consent", "odi_filing", "bank_registration", "incorporate"):
        d.event("milestone_timeline", "mark_milestone_done", mid)
    d.event("milestone_timeline", "mark_milestone_done", "setup_transfer")
    goal = svc.gk.goal(d.state.goal_id)
    assert next(m for m in goal.milestones if m.id == "setup_transfer").done_at is None, "not without a yes"
    assert d.state.pending is not None and d.state.pending.slot == "milestone_done"
    d.reply("no")
    goal = svc.gk.goal(d.state.goal_id)
    assert next(m for m in goal.milestones if m.id == "setup_transfer").done_at is None
    d.event("milestone_timeline", "mark_milestone_done", "setup_transfer")
    d.reply("yes")
    goal = svc.gk.goal(d.state.goal_id)
    assert next(m for m in goal.milestones if m.id == "setup_transfer").done_at is not None


def test_mark_done_only_from_a_timeline_widget(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _goal(d)
    status = max((k for k, v in d.state.widget_types.items() if v == "quick_replies"), key=lambda k: int(k[1:]), default=None)  # noqa: E501
    for wid in ("", "w999", status or "w1"):
        d.run(event=WidgetEvent(widget_id=wid, event="mark_milestone_done", value="lender_consent"))
    goal = svc.gk.goal(d.state.goal_id)
    assert all(m.done_at is None for m in goal.milestones)


def test_typed_done_goes_through_the_model_decision_validated_and_confirmed(svc: Any) -> None:  # noqa: F811
    from agent import llm

    d = Driver(svc)
    _goal(d)
    seen: dict[str, Any] = {}

    def decider(text: str, allowed: list[str], *_a: Any) -> llm.TurnDecision:
        seen["allowed"] = allowed
        mid = "bank_registration" if "registration" in text else "lender_consent"
        return llm.TurnDecision(action="mark_milestone_done", milestone_id=mid)

    llm.set_test_decider(decider)  # type: ignore[arg-type]
    d.run(text="the bank registration came through")  # out of order: refused by code
    assert "mark_milestone_done" in seen["allowed"]
    assert d.state.pending is None or d.state.pending.slot != "milestone_done"
    d.run(text="WeBank gave us their consent")
    assert d.state.pending is not None and d.state.pending.slot == "milestone_done", "typed: always confirmed"
    goal = svc.gk.goal(d.state.goal_id)
    assert all(m.done_at is None for m in goal.milestones)
    d.reply("yes")
    goal = svc.gk.goal(d.state.goal_id)
    assert next(m for m in goal.milestones if m.id == "lender_consent").done_at is not None

    llm.set_test_decider(lambda *_a: llm.TurnDecision(action="mark_milestone_done", milestone_id="pay_the_landlord"))  # type: ignore[arg-type]  # noqa: E501
    d.run(text="I paid the landlord")
    assert d.state.pending is None or d.state.pending.slot != "milestone_done", "an invented step is refused"


def test_typed_done_without_a_model_uses_code_reading(svc: Any) -> None:  # noqa: F811
    from agent import intent

    assert intent.milestone_done("WeBank's consent came through") == "lender_consent"
    assert intent.milestone_done("备案办好了") == "odi_filing"
    assert intent.milestone_done("营业执照和备案都办好了") is None, "two steps named"
    assert intent.milestone_done("the lease and the fit-out are done") is None, "two steps: ask, don't guess"
    assert intent.milestone_done("how is the consent going?") is None
    d = Driver(svc)
    _goal(d)
    d.run(text="WeBank's consent came through")
    assert d.state.pending is not None and d.state.pending.slot == "milestone_done"


def test_marking_done_is_audited_recomputes_status_and_a_revision_keeps_it(svc: Any) -> None:  # noqa: F811
    import json

    from agent.audit import verify
    from tools.models import GoalStatus

    d = Driver(svc)
    _goal(d)
    svc.gk._save(svc.gk.goal(d.state.goal_id).model_copy(update={"status": GoalStatus.OFF_TRACK}))  # stale status  # noqa: E501
    d.event("milestone_timeline", "mark_milestone_done", "lender_consent")
    goal = svc.gk.goal(d.state.goal_id)
    assert goal.status.value == "on_track", "recomputed from the latest check, not left stale"
    rows = [json.loads(x) for x in svc.audit.path.read_text(encoding="utf-8").splitlines()]
    done = [r for r in rows if r.get("kind") == "milestone_done" or r.get("event") == "milestone_done"]
    assert done, "marking a step done is in the audit log"
    assert verify(svc.audit.path)[0]
    st = svc.load_state(d.user)
    svc.gk.revise(st, "hash", "owner")
    goal = svc.gk.goal(st.goal_id)
    assert next(m for m in goal.milestones if m.id == "lender_consent").done_at is not None


def test_a_late_step_marked_done_no_longer_counts_against_the_status(svc: Any) -> None:  # noqa: F811
    from app.goalkeeper import _late

    d = Driver(svc)
    _goal(d)
    goal = svc.gk.goal(d.state.goal_id)
    first = next(m for m in goal.milestones if m.id == "lender_consent")
    assert "lender_consent" in _late(goal, first.latest_safe_week + 1)
    d.event("milestone_timeline", "mark_milestone_done", "lender_consent")
    goal = svc.gk.goal(d.state.goal_id)
    assert "lender_consent" not in _late(goal, first.latest_safe_week + 1)


# ------------------------------------------------------------------ 3. drafts


BARE = re.compile(r"[0-9０-９]")


def _letter_composer(numbers: bool) -> Any:
    from agent import voice

    def comp(beats: list[voice.Beat], lang: str) -> list[str]:
        out = []
        for b in beats:
            if b.key == "consent_letter":
                out.append(
                    "We plan one leased shop in Singapore, about {{fig:draft.invest_total}} in all"
                    + (", or 1.9 million yuan," if numbers else ",")
                    + " funded from our own profit, setting aside {{fig:draft.setaside_monthly}} a month."
                )
            else:
                out.append(" ".join([b.key.replace("_", " "), *b.must]))
        return out

    return comp


def test_consent_request_is_grounded_and_the_owner_sends_it(svc: Any) -> None:  # noqa: F811
    from agent import voice
    from agent.render import check_text

    voice.set_test_composer(_letter_composer(numbers=False))
    d = Driver(svc)
    _goal(d)
    d.event("milestone_timeline", "open_milestone", "lender_consent")
    card = d.widgets("draft_card")[-1]
    p = card.payload
    assert p.kind == "consent_request" and p.milestone_id == "lender_consent"
    # the model's prose went into the card, not into the chat, with every quantity filled from a Figure
    assert card.display["draft.invest_total"] in p.body and card.display["draft.setaside_monthly"] in p.body
    assert not any("leased shop" in x for x in d.texts())
    stripped = p.body
    for shown in card.display.values():
        stripped = stripped.replace(shown, " ")
    assert not BARE.search(stripped) and check_text(stripped).ok
    # every quantity the facts state is a Figure the card carries; the rest is plain words
    u = svc.gk.goal(d.state.goal_id).unit_id
    from agent import toolkit as tk

    unit = tk.unit(u)
    for f in p.facts:
        if f.figure is not None:
            assert f.figure in card.figures and card.figures[f.figure].source.ref == "drafts.consent_request"
        else:
            words = f.text.replace(unit.mall, " ").replace(unit.unit_no, " ")
            assert words and check_text(words).ok and not BARE.search(words), f.label
    goal = svc.gk.goal(d.state.goal_id)
    assert Decimal_eq(card.figures["draft.invest_total"].value, goal.cost_total_likely_sgd)
    assert Decimal_eq(card.figures["draft.setaside_monthly"].value, goal.setaside_monthly_cny)
    assert p.filename.endswith(".txt")
    # T1: nothing was sent
    assert "consent" not in " ".join(e["template"] for e in svc.store.emails_for(d.user["id"]))


def Decimal_eq(a: Any, b: Any) -> bool:  # noqa: N802
    from decimal import Decimal

    return Decimal(str(a)) == Decimal(str(b))


def test_a_letter_with_bare_numbers_is_rejected(svc: Any) -> None:  # noqa: F811
    from agent import voice

    voice.set_test_composer(_letter_composer(numbers=True))
    d = Driver(svc)
    _goal(d)
    d.event("milestone_timeline", "open_milestone", "lender_consent")
    card = d.widgets("draft_card")[-1]
    assert card.payload.body == "", "a body with a number outside placeholders never reaches the card"
    assert any(o.kind == "notice" for o in d.outs)
    assert card.payload.facts, "the code-built facts still show"


def test_checklists_come_from_data_with_sources_and_no_quantities(svc: Any) -> None:  # noqa: F811
    from agent import drafts
    from agent.render import check_text

    for lang in ("en", "zh"):
        for mid in ("odi_filing", "incorporate"):
            card = drafts.checklist(mid, lang)  # type: ignore[arg-type]
            assert card is not None and card.kind == "checklist" and card.items
            for it in card.items:
                assert it.source.label and it.source.as_of
                assert check_text(it.text).ok and not BARE.search(it.text), (mid, it.id)
            assert {s.label for s in card.sources} == {it.source.label for it in card.items}
    assert drafts.checklist("fitout", "en") is None
    d = Driver(svc)
    _goal(d)
    d.event("milestone_timeline", "open_milestone", "odi_filing")
    assert d.widgets("draft_card")[-1].payload.kind == "checklist"
    d.event("milestone_timeline", "open_milestone", "incorporate")
    assert d.widgets("draft_card")[-1].payload.milestone_id == "incorporate"
    d.event("milestone_timeline", "open_milestone", "no_such_step")
    assert not d.widgets("draft_card")


def test_milestone_detail_from_the_goal_tab_is_accepted(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _goal(d)
    d.run(event=WidgetEvent(widget_id="g3", event="open_milestone", value="lender_consent"))
    assert d.widgets("draft_card")
