"""End-to-end journey through the orchestrator, scripted path (no model), SPEC §3, §4, §12.4."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agent.state import JourneyState
from agent.turn import Out
from agent.widgets import WidgetEvent


@pytest.fixture()
def svc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("WAYPOINT_VAR", str(tmp_path))
    monkeypatch.setenv("WAYPOINT_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("WAYPOINT_SMTP_PORT", "1")  # no mail server in unit tests
    monkeypatch.setenv("WAYPOINT_LLM_PROVIDER", "none")
    import importlib

    import app.store as store_mod

    importlib.reload(store_mod)
    from app.services import AppServices

    store = store_mod.Store(f"sqlite:///{tmp_path / 'db.sqlite3'}")
    s = AppServices(store, base_url="http://test", demo=True)
    return s


class Driver:
    def __init__(self, svc: Any, host_mode: str = "embedded") -> None:
        self.svc = svc
        self.user = svc.store.create_user(host_mode, email="chen@example.test", verified=True)
        self.state: JourneyState = svc.load_state(self.user)
        self.outs: list[Out] = []

    def run(self, text: str | None = None, event: WidgetEvent | None = None, init: bool = False) -> list[Out]:
        self.outs = asyncio.run(self.svc.orchestrator.run(self.state, text=text, event=event, init=init))
        self.svc.save_state(self.state)
        return self.outs

    def widgets(self, wtype: str | None = None) -> list[Any]:
        return [
            o.widget
            for o in self.outs
            if o.kind == "widget" and o.widget and (wtype is None or o.widget.payload.type == wtype)
        ]

    def texts(self) -> list[str]:
        return [o.text or "" for o in self.outs if o.kind == "text"]

    def reply(self, value: str) -> list[Out]:
        p = self.state.pending
        assert p is not None, "no pending question"
        return self.run(event=WidgetEvent(widget_id=p.widget_id or "", event="reply", value=value))

    def event(
        self, wtype: str, event: str, value: Any = None, data: dict[str, Any] | None = None
    ) -> list[Out]:
        wid = max((k for k, v in self.state.widget_types.items() if v == wtype), key=lambda k: int(k[1:]))
        return self.run(event=WidgetEvent(widget_id=wid, event=event, value=value, data=data or {}))  # type: ignore[arg-type]


def _profile(d: Driver) -> None:
    """Embedded owner: consent, then tap the first option until the profile confirm card."""
    d.run(init=True)
    d.event("consent_card", "consent", True)
    assert d.widgets("profile_card") or d.state.step == "profile"
    while d.state.pending is not None and d.state.pending.skill == "profile":
        d.reply(d.state.pending.options[0]["value"])
    d.event("confirm_card", "confirm", "profile")
    assert d.state.step == "site"


def _to_cost(d: Driver) -> None:
    _profile(d)
    d.reply("near_customers")
    assert d.widgets("area_map")
    d.reply(d.state.pending.options[0]["value"])  # type: ignore[union-attr]
    assert d.widgets("unit_compare")
    d.reply(d.state.pending.options[0]["value"])  # picking the unit is the confirmation  # type: ignore[union-attr]
    assert d.state.step == "cost"
    assert d.state.pending is not None and d.state.pending.slot == "adjust"


def _to_goal_plan(d: Driver) -> None:
    _to_cost(d)
    d.reply("looks_right")
    assert d.state.step == "funding"
    d.reply("looks_good")
    assert d.state.step == "goal_plan"


def _approve(d: Driver) -> None:
    card = d.widgets("approval_card")[-1]
    d.event("approval_card", "approve", data={"card_hash": card.payload.card_hash})


def test_full_journey_embedded_creates_goal_in_few_taps(svc: Any) -> None:
    d = Driver(svc)
    _to_cost(d)
    assert d.widgets("cost_breakdown") and any(w.payload.type == "topic_card" for w in d.widgets())
    d.reply("add_quote")
    d.reply("demo_quote")
    up = d.widgets("upload_prompt")[-1]
    assert up.payload.reader_mode == "replay" and up.payload.extracted
    d.event("upload_prompt", "accept_all", up.payload.doc_id)
    card = d.state.cost_card
    assert card is not None
    fit = next(ln for ln in card.lines if ln.key == "fitout")
    # the demo quote's lines each price part of the fit-out: the estimate stays until the owner says the
    # quote covers all of it
    assert not fit.from_quote and fit.flags == ["partial"] and fit.likely_sgd >= (fit.quote_sgd or 0)
    assert [c.key for c in up.payload.coverage] == ["fitout"] and not up.payload.coverage[0].whole
    cover = {"doc_id": up.payload.doc_id, "key": "fitout", "whole": True}
    d.event("upload_prompt", "set_coverage", "fitout", cover)
    assert d.state.cost_card is not None and any(ln.from_quote for ln in d.state.cost_card.lines)
    d.reply("looks_right")
    assert d.state.step == "funding"
    assert d.widgets("setaside_slider") and d.widgets("closed_options")
    d.reply("looks_good")
    assert d.state.step == "goal_plan"
    assert d.widgets("milestone_timeline") and d.widgets("goal_summary") and d.widgets("approval_card")
    _approve(d)
    assert d.state.goal_id is not None and d.state.step == "goal_keeper"
    dash = svc.goal_dashboard(d.state)
    types = [w["payload"]["type"] for w in dash["widgets"]]
    assert "plan_vs_actual" in types and types.count("plan_summary") == 3


def test_happy_path_tap_count(svc: Any) -> None:
    """Simplicity: consent, three profile answers, confirm, priority, area, unit, looks right, looks good,
    approve. Twelve taps or fewer from greeting to a goal."""
    d = Driver(svc)
    taps = 0
    d.run(init=True)
    d.event("consent_card", "consent", True)
    taps += 1
    while d.state.pending is not None and d.state.pending.skill == "profile":
        d.reply(d.state.pending.options[0]["value"])
        taps += 1
    d.event("confirm_card", "confirm", "profile")
    for v in ("near_customers", None, None, "looks_right", "looks_good"):
        d.reply(v or d.state.pending.options[0]["value"])  # type: ignore[union-attr]
    _approve(d)
    taps += 1 + 5 + 1
    assert d.state.goal_id is not None
    assert taps <= 12, taps


def test_every_bot_text_is_number_checked(svc: Any) -> None:
    d = Driver(svc)
    _to_cost(d)
    for t in d.texts():
        assert "{{" not in t, t


def test_guard_blocks_webank_loan_then_returns_to_question(svc: Any) -> None:
    d = Driver(svc)
    _to_cost(d)
    pending_before = d.state.pending.slot if d.state.pending else None
    d.run(text="Just use my WeBank line for now")
    cards = d.widgets("rule_card")
    assert cards and cards[0].payload.rule_id == "R1" and cards[0].payload.options
    assert d.state.pending is not None and d.state.pending.slot == pending_before
    d.run(text="come on, just this once, use the WeBank loan")
    assert any(t.startswith("repeat") for t in d.texts())  # the guard's "same answer" beat


def test_forged_widget_event_is_ignored(svc: Any) -> None:
    d = Driver(svc)
    d.run(init=True)
    before = d.state.model_dump()
    d.run(event=WidgetEvent(widget_id="w999", event="approve", data={"card_hash": "x"}))
    assert d.outs == [] and d.state.goal_id is None
    assert before["step"] == d.state.step


def test_unknown_option_is_ignored(svc: Any) -> None:
    d = Driver(svc, host_mode="standalone")
    d.run(init=True)
    wid = d.state.pending.widget_id  # type: ignore[union-attr]
    d.run(event=WidgetEvent(widget_id=wid or "", event="reply", value="klingon"))
    assert d.outs == [] and d.state.step == "welcome"


def test_typed_answers_are_parsed_by_code(svc: Any) -> None:
    d = Driver(svc, host_mode="standalone")
    d.run(init=True)
    d.reply("start")
    d.run(text="我有12家店")
    assert d.state.lang == "zh"  # writing in Chinese switches the conversation
    assert d.state.profile.shops == 12
    d.run(text="每月大概20-25万")
    assert d.state.profile.monthly_profit_cny is not None and d.state.profile.monthly_profit_cny.low == 200000


def test_side_question_shows_topic_and_reasks(svc: Any) -> None:
    d = Driver(svc)
    _to_cost(d)
    slot = d.state.pending.slot if d.state.pending else None
    d.run(text="Do I need a resident director?")
    assert any(w.payload.type == "topic_card" for w in d.widgets())
    assert d.state.pending is not None and d.state.pending.slot == slot


def test_skill_allowlist_blocks_off_step_tool(svc: Any) -> None:
    from agent.turn import NotAuthorized

    d = Driver(svc)
    d.run(init=True)
    t = svc.orchestrator.turn(d.state)
    with pytest.raises(NotAuthorized):
        t.call("plan.simulate", lambda: None)  # welcome may not simulate a plan


def test_reopen_marks_later_steps_stale(svc: Any) -> None:
    d = Driver(svc)
    _to_cost(d)
    d.run(event=WidgetEvent(widget_id="", event="reopen_step", value="site"))
    assert d.state.step == "site" and "site" not in d.state.done


def test_approval_refused_after_state_change(svc: Any) -> None:
    d = Driver(svc)
    _to_goal_plan(d)
    card = d.widgets("approval_card")[-1]
    assert d.state.funding is not None
    d.state.funding.own_savings_cny += 1  # state changes after the card was prepared
    d.event("approval_card", "approve", data={"card_hash": card.payload.card_hash})
    assert d.state.goal_id is None
    assert d.widgets("approval_card"), "a fresh card is offered"


def test_optional_goal_extras_reissue_the_card(svc: Any) -> None:
    d = Driver(svc)
    _to_goal_plan(d)
    first = d.widgets("approval_card")[-1].payload.card_hash
    d.reply("add_transfer")
    card = d.widgets("approval_card")[-1]
    assert card.payload.card_hash != first and d.state.goal_prefs["recurring_setaside"] is True
    _approve(d)
    assert d.state.goal_id is not None


# ------------------------------------------------------------------ regressions found by E3 (first eval run)


def test_cannot_jump_ahead_to_an_unreached_step(svc: Any) -> None:
    d = Driver(svc)
    d.run(init=True)
    d.run(event=WidgetEvent(widget_id="", event="reopen_step", value="funding"))
    assert d.state.step == "welcome"


def test_old_confirm_card_cannot_confirm_the_current_step(svc: Any) -> None:
    d = Driver(svc)
    _to_cost(d)
    profile_card = next(
        k for k, v in d.state.widget_types.items() if v == "confirm_card" and d.state.widget_steps[k] == "profile"  # noqa: E501
    )
    d.run(event=WidgetEvent(widget_id=profile_card, event="confirm", value="profile"))
    assert d.state.step == "cost" and not (d.state.cost_card and d.state.cost_card.confirmed)


def test_unit_not_offered_is_ignored(svc: Any) -> None:
    d = Driver(svc)
    _profile(d)
    d.reply("near_customers")
    d.reply(d.state.pending.options[0]["value"])  # type: ignore[union-attr]
    offered = set(d.state.shortlist.unit_ids)
    other = next(u.id for u in __import__("tools.data", fromlist=["x"]).load_units() if u.id not in offered)
    d.event("unit_compare", "select_unit", other)
    assert d.state.shortlist.chosen_unit_id is None


def test_consent_needs_a_literal_true(svc: Any) -> None:
    d = Driver(svc)
    d.run(init=True)
    for junk in ("false", "no", "maybe", 0):
        d.event("consent_card", "consent", junk)
        assert d.state.consent_feed is None and d.state.step == "welcome"


@pytest.mark.parametrize(
    "typed,granted", [("I agree", True), ("ok", True), ("同意", True), ("不要", False), ("no thanks", False)]
)
def test_typed_consent_is_read_by_code_without_a_model(svc: Any, typed: str, granted: bool) -> None:
    d = Driver(svc)
    d.run(init=True)
    d.run(text=typed)
    assert d.state.consent_feed is granted and d.state.step == "profile"
    assert bool(d.widgets("profile_card")) is granted


def test_consent_card_stays_usable_after_typing(svc: Any) -> None:
    d = Driver(svc)
    d.run(init=True)
    d.run(text="hmm, tell me more first")
    assert d.state.step == "welcome" and d.state.consent_feed is None
    assert d.widgets("consent_card"), "a fresh consent card follows the unclear reply"
    d.run(text="What is GST?")  # a side question also leads back to the card
    assert d.widgets("consent_card")
    d.event("consent_card", "consent", True)
    assert d.state.consent_feed is True and d.state.step == "profile"


def test_bad_slider_values_and_unknown_options_are_ignored(svc: Any) -> None:
    d = Driver(svc)
    _to_cost(d)
    d.reply("looks_right")
    assert d.state.funding is not None
    before = d.state.funding.setaside_share
    d.event("setaside_slider", "slider_commit", -0.2)
    d.event("setaside_slider", "slider_commit", "abc")
    assert d.state.funding.setaside_share == before
    d.event("funding_options", "toggle_option", True, data={"id": "webank_loan_for_singapore", "on": True})
    assert "webank_loan_for_singapore" not in d.state.funding.options_on


def test_unknown_area_and_unhandled_events_do_not_crash(svc: Any) -> None:
    d = Driver(svc)
    _profile(d)
    d.reply("near_customers")
    d.event("area_map", "select_area", "ATLANTIS")
    assert d.state.selected_area is None
    d.event("area_map", "upload", "d_nope")  # not handled in this step: ignored, no exception


def test_one_message_fills_several_profile_answers(svc: Any) -> None:
    """The model may propose several answers from one sentence; code validates each one."""
    from agent import llm

    def decider(text: str, actions: list[str], slot: str | None, options: list[str], topics: list[str],
                extra: dict[str, str] | None = None) -> llm.TurnDecision:
        assert extra and "shops" in extra and "customers" in extra
        return llm.TurnDecision(action="answer_slot", fills={
            "shops": "14", "monthly_profit": "200000|220000", "customers": "young_adults",
            "budget": "300000|450000", "window": "next_tuesday",  # invalid: code rejects it
        })

    llm.set_test_decider(decider)
    try:
        d = Driver(svc, host_mode="standalone")
        d.run(init=True)
        d.reply("start")
        d.run(text="14 tea shops, about 200 to 220k profit a month, mostly young people, budget S$300-450k")
        p = d.state.profile
        assert p.shops == 14 and p.customers and p.budget_sgd is not None
        assert p.monthly_profit_cny is not None and p.monthly_profit_cny.low == 200000
        assert p.opening_window_months is None  # the invalid value was not stored
        assert d.state.pending is not None and d.state.pending.slot in ("spare_cash", "window")
    finally:
        llm.set_test_decider(None)


def test_a_plan_later_than_the_owner_hoped_is_said_plainly(svc: Any) -> None:
    d = Driver(svc)
    _to_cost(d)
    d.reply("looks_right")
    assert d.state.step == "funding" and d.state.plan is not None
    hoped = d.state.profile.opening_window_months
    likely = d.state.plan.open_likely_week
    assert hoped is not None and likely is not None
    said = [o.beat.key for o in d.outs if o.beat is not None]
    opts = d.widgets("funding_options")[-1]
    amounts = [c.amount for c in opts.payload.options if c.amount]
    assert amounts and all(opts.display.get(a) for a in amounts), "every card amount resolves"
    assert all(opts.figures[a].value not in (None, 0) for a in amounts), "no RMB 0 on an option not taken"
    assert ("window_miss" in said) == (likely * 12 / 52 > hoped + 0.5)
    miss = next((o.beat for o in d.outs if o.beat is not None and o.beat.key == "window_miss"), None)
    if miss is not None:
        assert miss.facts["hoped_for"] and not any(ch.isdigit() for ch in miss.facts["hoped_for"])


def test_a_language_switched_in_the_chat_is_saved_to_the_account(svc: Any) -> None:
    d = Driver(svc)
    d.run(init=True)
    d.run(text="我们用中文聊吧，我想在新加坡开一家奶茶店")
    assert d.state.lang == "zh"
    assert svc.account_view(svc.store.user(d.user["id"]))["lang"] == "zh"


def test_only_areas_with_units_to_lease_are_recommended(svc: Any) -> None:
    from agent import toolkit as tk

    d = Driver(svc)
    _profile(d)
    d.reply("near_customers")
    amap = d.widgets("area_map")[-1].payload
    assert amap.top and all(tk.has_listings(a) for a in amap.top)
    assert len(amap.areas) > len(amap.top), "every area still has its shade on the map"


def test_the_approval_message_follows_the_reminders_the_owner_picked(svc: Any) -> None:
    d = Driver(svc)
    _to_goal_plan(d)
    d.reply("change_reminders")
    d.reply("fortnightly")
    intro = [o.beat for o in d.outs if o.beat is not None and o.beat.key == "approve_intro"]
    assert intro and intro[-1].facts["reminders"] == "Every fortnight"
    card = d.widgets("approval_card")[-1].payload
    assert any(ln.value == "Every fortnight" for ln in card.lines)


def _correcting(fills: dict[str, str]) -> Any:
    from agent import llm

    def decider(text: str, actions: list[str], slot: str | None, options: list[str], topics: list[str],
                extra: dict[str, str] | None = None) -> llm.TurnDecision:
        assert "correct_business" in actions and extra and "spare_cash" in extra
        return llm.TurnDecision(action="correct_business", fills=fills)

    return decider


def test_a_business_fact_corrected_at_funding_recomputes_the_funding(svc: Any) -> None:
    """Found by E1b: owners whose spare cash differed from the feed couldn't correct it at funding."""
    from agent import llm

    d = Driver(svc)
    _to_cost(d)
    d.reply("looks_right")
    assert d.state.step == "funding"
    gap_before = d.widgets("funding_options")[-1].figures["funding.gap"].value
    llm.set_test_decider(_correcting({"spare_cash": "300000|300000", "window": "someday"}))
    try:
        d.run(text="My spare cash is about RMB 300k, not 500k. Please redo the numbers.")
    finally:
        llm.set_test_decider(None)
    assert d.state.profile.spare_cash_cny == 300000 and d.state.profile.sources["spare_cash"] == "owner"
    assert d.state.step == "funding" and d.state.pending is not None and d.state.pending.slot == "lever"
    said = [o.beat.key for o in d.outs if o.beat is not None]
    assert said[0] == "corrected" and "gap_intro" in said
    gap_after = d.widgets("funding_options")[-1].figures["funding.gap"].value
    assert gap_after > gap_before, "less spare cash, a bigger gap"
    assert d.state.profile.opening_window_months != 0  # the invalid window was not stored


def test_a_customer_correction_after_the_site_step_reopens_the_site(svc: Any) -> None:
    from agent import llm

    d = Driver(svc)
    _to_cost(d)
    llm.set_test_decider(_correcting({"customers": "students"}))
    try:
        d.run(text="Actually my main customers are students, not who I said.")
    finally:
        llm.set_test_decider(None)
    assert [c.value for c in d.state.profile.customers] == ["students"]
    assert d.state.step == "site" and d.state.pending is not None


def test_nothing_is_correctable_once_the_goal_exists(svc: Any) -> None:
    from agent import llm

    seen: list[list[str]] = []

    def decider(text: str, actions: list[str], *rest: Any) -> llm.TurnDecision:
        seen.append(list(actions))
        return llm.TurnDecision(action="unclear")

    d = Driver(svc)
    _to_goal_plan(d)
    _approve(d)
    assert d.state.goal_id is not None
    llm.set_test_decider(decider)
    try:
        d.run(text="my spare cash is actually lower")
    finally:
        llm.set_test_decider(None)
    assert seen and "correct_business" not in seen[-1], "after approval, changes go through a revision"


def test_the_answer_to_the_question_asked_counts_alongside_other_fills(svc: Any) -> None:
    """Seen live: the model put the pending answer in slot_value and only the other answers in fills."""
    from agent import llm

    def decider(text: str, actions: list[str], slot: str | None, options: list[str], topics: list[str],
                extra: dict[str, str] | None = None) -> llm.TurnDecision:
        return llm.TurnDecision(action="answer_slot", slot_value="office_workers",
                                fills={"budget": "300000|450000", "window": "6_12"})

    llm.set_test_decider(decider)
    try:
        d = Driver(svc)
        d.run(init=True)
        d.event("consent_card", "consent", True)
        assert d.state.pending is not None and d.state.pending.slot == "customers"
        d.run(text="Mostly office workers. Budget about S$300k to S$450k, open within a year.")
        p = d.state.profile
        assert [c.value for c in p.customers] == ["office_workers"]
        assert p.budget_sgd is not None and p.opening_window_months == 12
    finally:
        llm.set_test_decider(None)


def test_approval_card_shows_cost_savings_mix_and_floor_risk(svc: Any) -> None:
    from decimal import Decimal

    from agent import toolkit as tk

    d = Driver(svc)
    _to_goal_plan(d)
    lines = {ln.label: ln.value for ln in d.widgets("approval_card")[-1].payload.lines}
    total = lines["Total likely cost"]
    assert total.startswith("S$") and "(" in total and any(c in total for c in ("¥", "RMB")), total
    assert "Spare cash" in lines["Funding mix"] and any(ch.isdigit() for ch in lines["Funding mix"])
    assert lines["Chance home cash dips below the floor"].endswith("%")
    assert "Own savings committed" not in lines, "no savings line when none are committed"
    # with savings committed, the card says how much, and the mix includes it
    assert d.state.funding is not None
    d.state.funding.own_savings_cny = Decimal("80000")
    t = svc.orchestrator.turn(d.state)
    lines = {ln["label"]: ln["value"] for ln in tk.approval_lines(d.state, t)}
    assert "80" in lines["Own savings committed"] and "Own savings" in lines["Funding mix"]
    d.state.lang = "zh"
    zh = {ln["label"]: ln["value"] for ln in tk.approval_lines(d.state, svc.orchestrator.turn(d.state))}
    assert "预计总成本" in zh and "资金来源" in zh and "国内现金跌破底线的概率" in zh
