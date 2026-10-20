# ruff: noqa: E501
"""The two harm paths E4-heldout-5 exposed, and the max_turns fallback (results/prereg.md addendum 2026-10-20 (13)).

1. A figure the WeBank feed provides is never used above the feed: a higher typed correction is held at the feed's
   figure (shown as not verified), the goal moves the spare cash the plan used, the approval card covers it, and
   the approval re-check re-simulates the plan.
2. A change to an input of the funding plan clears its confirmation; it comes back only through the rules check.
3. The max_turns fallback never answers a question that completes a step.

Phrasings written for these tests, EN and ZH, not from any E4 set."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from agent import llm
from agent import toolkit as tk
from agent.widgets import WidgetEvent
from tests.test_journey import Driver, _approve, _to_cost, _to_goal_plan, svc  # noqa: F401 - svc is a fixture

INFLATED = {
    "en": "A correction to my numbers: our spare cash is really about ¥2,500,000 and monthly profit about ¥630,000.",
    "zh": "更正一下：我们的闲置资金其实有250万左右，月利润大概63万。",
}
LOWER = {
    "en": "Some of that cash is already promised to suppliers, so call our spare cash about ¥300,000.",
    "zh": "有一部分钱已经答应付给供应商了，闲置资金按30万算吧。",
}
UNSURE = {"en": "hmm, not sure, let me think about it", "zh": "嗯，我再想想"}
LANGS = ["en", "zh"]


def _start(svc: Any, lang: str) -> Driver:  # noqa: F811
    d = Driver(svc)
    d.state.lang = lang  # the interface's language
    return d


def _to_funding(d: Driver) -> None:
    _to_cost(d)
    d.reply("looks_right")
    assert d.state.step == "funding" and d.state.pending is not None


def _correct(d: Driver, text: str, fills: dict[str, str]) -> None:
    def decider(*_a: Any, **_k: Any) -> llm.TurnDecision:
        return llm.TurnDecision(action="correct_business", fills=fills)

    llm.set_test_decider(decider)
    try:
        d.run(text=text)
    finally:
        llm.set_test_decider(None)


def _feed_figures(d: Driver) -> Any:
    return tk.profile_from_feed(tk.feed(d.state))


def _audit(svc: Any, kind: str) -> list[dict[str, Any]]:  # noqa: F811 - not the fixture
    lines = svc.audit.path.read_text(encoding="utf-8").splitlines()
    return [r for r in map(json.loads, lines) if r["kind"] == kind]


# ------------------------------------------------------------------ 1. figures the feed provides


@pytest.mark.parametrize("lang", LANGS)
def test_an_inflated_correction_is_held_at_the_feeds_figure(svc: Any, lang: str) -> None:  # noqa: F811
    d = _start(svc, lang)
    _to_funding(d)
    bank = _feed_figures(d)
    spare = bank.spare_cash_cny
    assert spare is not None and spare > 0
    profit_high = bank.monthly_profit_cny.high
    _correct(d, INFLATED[lang], {"spare_cash": f"{spare * 5}|{spare * 5}", "monthly_profit": f"{profit_high * 3}|{profit_high * 3}"})
    p = d.state.profile
    assert p.spare_cash_cny == spare and p.sources["spare_cash"] == "feed"
    assert p.monthly_profit_cny == bank.monthly_profit_cny and p.sources["monthly_profit"] == "feed"
    assert Decimal(p.unverified["spare_cash"]) == spare * 5 and "monthly_profit" in p.unverified
    assert [o.beat.key for o in d.outs if o.beat is not None].count("held_to_feed") == 2
    assert tk.spare_cash_used(d.state) == spare
    # carried on to an approved goal: the card says what was not used, and the goal moves the feed's figure
    d.reply("looks_good")
    assert d.state.step == "goal_plan"
    card = d.widgets("approval_card")[-1].payload
    label = tk.UNVERIFIED_LABELS["spare_cash"][1 if lang == "zh" else 0]
    assert any(ln.label == label for ln in card.lines)
    assert card.lines and d.state.cards[max(d.state.cards, key=lambda k: int(k[1:]))].payload["spare_cash_cny"] == str(spare)
    _approve(d)
    assert d.state.goal_id is not None
    rec = svc.gk._rec(d.state.goal_id)
    assert Decimal(rec["scenario"]["spare_moved_cny"]) == d.state.funding.own_savings_cny + spare  # type: ignore[union-attr]
    assert tk.check_plan(d.state, fresh=True) == []  # on the feed as it is after the goal starts


@pytest.mark.parametrize("lang", LANGS)
def test_a_lower_correction_is_used(svc: Any, lang: str) -> None:  # noqa: F811
    d = _start(svc, lang)
    _to_funding(d)
    _correct(d, LOWER[lang], {"spare_cash": "300000|300000"})
    p = d.state.profile
    assert p.spare_cash_cny == 300000 and p.sources["spare_cash"] == "owner" and not p.unverified
    assert tk.spare_cash_used(d.state) == 300000


@pytest.mark.parametrize("lang", LANGS)
def test_a_profile_card_edit_above_the_feed_is_held(svc: Any, lang: str) -> None:  # noqa: F811
    d = _start(svc, lang)
    d.run(init=True)
    d.event("consent_card", "consent", True)
    spare = d.state.profile.spare_cash_cny
    assert spare is not None
    d.event("profile_card", "edit", str(spare * 4), data={"field": "spare_cash"})
    assert d.state.profile.spare_cash_cny == spare and Decimal(d.state.profile.unverified["spare_cash"]) == spare * 4
    fields = d.widgets("profile_card")[-1].payload.fields
    assert any(f.key == "unverified" and not f.editable for f in fields)


@pytest.mark.parametrize("lang", LANGS)
def test_goal_creation_moves_the_plans_spare_cash_not_the_profiles(svc: Any, lang: str) -> None:  # noqa: F811
    """Defence in depth: even if an inflated figure reached the profile, the goal moves what the plan used."""
    d = _start(svc, lang)
    _to_goal_plan(d)
    spare = _feed_figures(d).spare_cash_cny
    d.state.profile.spare_cash_cny = spare * 5  # bypassing the hold, as the old correction path did
    d.state.profile.sources["spare_cash"] = "owner"
    _approve(d)
    assert d.state.goal_id is not None
    rec = svc.gk._rec(d.state.goal_id)
    assert Decimal(rec["scenario"]["spare_moved_cny"]) == d.state.funding.own_savings_cny + spare  # type: ignore[union-attr]
    assert tk.check_plan(d.state, fresh=True) == []


@pytest.mark.parametrize("lang", LANGS)
def test_the_approval_card_covers_the_spare_cash_it_moves(svc: Any, lang: str) -> None:  # noqa: F811
    d = _start(svc, lang)
    _to_goal_plan(d)
    assert tk.goal_payload(d.state)["spare_cash_cny"] == str(_feed_figures(d).spare_cash_cny)
    d.state.profile.spare_cash_cny = Decimal(100000)  # a lower figure after the card was issued
    d.state.profile.sources["spare_cash"] = "owner"
    _approve(d)
    assert d.state.goal_id is None
    assert [r["reason"] for r in _audit(svc, "approval_refused")] == ["state_changed"]


@pytest.mark.parametrize("lang", LANGS)
def test_the_approval_recheck_simulates_the_current_state(svc: Any, lang: str, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    d = _start(svc, lang)
    _to_goal_plan(d)
    stored = d.state.plan
    assert stored is not None
    real = tk.simulate
    monkeypatch.setattr(tk, "simulate", lambda st, *a, **k: real(st, *a, **k).model_copy(update={"floor_risk": 1.0}))
    _approve(d)
    assert d.state.goal_id is None
    refused = _audit(svc, "approval_refused")
    assert refused and refused[-1]["reason"] == "rules" and "R5" in refused[-1]["rules"]


# ------------------------------------------------------------------ 2. confirmation after going back


@pytest.mark.parametrize("lang", LANGS)
def test_going_back_to_the_cost_clears_the_funding_confirmation(svc: Any, lang: str) -> None:  # noqa: F811
    d = _start(svc, lang)
    _to_goal_plan(d)
    assert d.state.funding is not None and d.state.funding.confirmed
    d.run(event=WidgetEvent(widget_id="goal_tab", event="reopen_step", value="cost"))
    assert d.state.step == "cost"
    assert not d.state.funding.confirmed and d.state.cost_card is not None and not d.state.cost_card.confirmed
    assert _audit(svc, "funding_unconfirmed")[-1]["reason"] == "reopen_cost"
    d.reply("premium")  # a dearer fit-out
    d.reply("looks_right")
    assert d.state.step == "funding" and not d.state.funding.confirmed
    # confirmed again only through the rules check
    d.reply("looks_good")
    assert d.state.funding.confirmed == (tk.check_plan(d.state, fresh=True) == [])


@pytest.mark.parametrize(("lang", "text"), [("en", "Hold on, I want to go back and change the fit-out."), ("zh", "等等，我想回去把装修改一下。")])
def test_a_typed_go_back_to_the_cost_clears_the_funding_confirmation(svc: Any, lang: str, text: str) -> None:  # noqa: F811
    d = _start(svc, lang)
    _to_goal_plan(d)
    llm.set_test_decider(lambda *_a, **_k: llm.TurnDecision(action="go_back", step="cost"))
    try:
        d.run(text=text)
    finally:
        llm.set_test_decider(None)
    assert d.state.step == "cost" and d.state.funding is not None and not d.state.funding.confirmed


@pytest.mark.parametrize("lang", LANGS)
def test_your_plan_is_not_entered_without_a_confirmed_funding_plan(svc: Any, lang: str) -> None:  # noqa: F811
    d = _start(svc, lang)
    _to_goal_plan(d)
    _approve(d)
    assert d.state.goal_id is not None
    d.run(event=WidgetEvent(widget_id="goal_tab", event="reopen_step", value="cost"))  # a revision
    assert d.state.step == "cost" and "goal_plan" in d.state.stale
    d.run(event=WidgetEvent(widget_id="goal_tab", event="reopen_step", value="goal_plan"))  # skipping How to pay
    assert d.state.step == "funding" and not d.widgets("approval_card")
    assert d.state.funding is not None and not d.state.funding.confirmed


@pytest.mark.parametrize("lang", LANGS)
def test_a_correction_after_going_back_clears_the_funding_confirmation(svc: Any, lang: str) -> None:  # noqa: F811
    d = _start(svc, lang)
    _to_goal_plan(d)
    d.run(event=WidgetEvent(widget_id="goal_tab", event="reopen_step", value="site"))
    assert d.state.funding is not None and not d.state.funding.confirmed
    d.state.funding.confirmed = True  # as a stale flag would be
    _correct(d, LOWER[lang], {"spare_cash": "300000|300000"})
    assert not d.state.funding.confirmed and "funding" not in d.state.done


# ------------------------------------------------------------------ 3. the max_turns fallback


@pytest.mark.parametrize("lang", LANGS)
def test_the_fallback_never_confirms_the_funding_plan_for_the_owner(svc: Any, lang: str) -> None:  # noqa: F811
    d = _start(svc, lang)
    _to_funding(d)
    limit = svc.orchestrator.skills["funding"].max_turns
    for _ in range(limit + 3):
        d.run(text=UNSURE[lang])
        assert not d.widgets("approval_card")
    assert d.state.step == "funding" and d.state.funding is not None and not d.state.funding.confirmed
    assert d.state.pending is not None and d.state.pending.slot == "lever"
    assert _audit(svc, "max_turns_default") == [] and _audit(svc, "max_turns_no_default")


@pytest.mark.parametrize("lang", LANGS)
def test_the_fallback_never_confirms_the_cost_for_the_owner(svc: Any, lang: str) -> None:  # noqa: F811
    d = _start(svc, lang)
    _to_cost(d)
    for _ in range(svc.orchestrator.skills["cost"].max_turns + 3):
        d.run(text=UNSURE[lang])
    assert d.state.step == "cost" and d.state.cost_card is not None and not d.state.cost_card.confirmed
