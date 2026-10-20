"""WeBank's "yes" at home (judge-response memo §1a): the bank cards on the funding screen, never in the plan.

WeBank 微业贷 for documented home needs is sized from the feed (the usual level for the month minus the
current balance) and shown only when the balance is below that level, with the R2 pause on the same card. It
never counts toward Singapore: R1 closes loan -> pot in code, and a plan that lists it is an R1 violation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from mock_webank import feed as mw
from rules.engine import blocking, check_plan, rule
from tests.test_journey import Driver, _to_cost, svc  # noqa: F401  (fixture re-export)
from tools import funding as F
from tools.costs import estimate_costs
from tools.data import load_catalogue, unit_by_id
from tools.models import FeedSnapshot, FundingPlan

BANK_IDS = {"webank_home_wc", "webank_pot_deposit", "partner_bank_fx"}


def _below_usual(fs: FeedSnapshot, by: str = "80000") -> FeedSnapshot:
    usual = fs.normal_loan_balance_by_month_cny[fs.as_of.month]
    return fs.model_copy(update={"loan_balance_cny": usual - Decimal(by)})


def _card() -> Any:
    return estimate_costs(unit_by_id("u-tm-01"))


def test_bank_cards_are_dated_subject_to_approval_and_not_plan_routes() -> None:
    for oid in BANK_IDS:
        e = load_catalogue().get(oid)
        assert e is not None and not e.in_plan and e.as_of is not None and e.subject_to_approval, oid
    plan_ids = {r.option.id for r in F.funding_options(_below_usual(mw.get_feed("x")), _card())}
    assert not plan_ids & BANK_IDS


def test_home_card_is_sized_from_the_feed_and_carries_the_r2_pause() -> None:
    fs = _below_usual(mw.get_feed("x"), "80000")
    cards = {r.option.id: r for r in F.bank_cards(fs)}
    home = cards["webank_home_wc"]
    assert home.amount is not None and home.amount.value == Decimal("80000")
    assert home.amount.id == "funding.webank.home_headroom" and home.amount.source.kind.value == "tool"
    assert home.option.note == rule("R2")["message_en"] and home.option.note_rule == "R2"
    assert home.option.card == "webank" and "webank.com" in (home.option.product_url or "")
    zh = {r.option.id: r for r in F.bank_cards(fs, "zh")}["webank_home_wc"]
    assert zh.option.note == rule("R2")["message_zh"] and "微业贷" in zh.option.label


@pytest.mark.parametrize("delta", ["0", "-50000"])
def test_home_card_hidden_at_or_above_the_usual_level(delta: str) -> None:
    fs = mw.get_feed("x")
    usual = fs.normal_loan_balance_by_month_cny[fs.as_of.month]
    fs = fs.model_copy(update={"loan_balance_cny": usual - Decimal(delta)})
    ids = {r.option.id for r in F.bank_cards(fs)}
    assert "webank_home_wc" not in ids and {"webank_pot_deposit", "partner_bank_fx"} <= ids


def test_home_card_needs_the_feed() -> None:
    from tools.models import Profile

    assert F.home_loan_headroom(Profile()) is None


def test_home_working_capital_never_counts_toward_singapore() -> None:
    """Code-enforced: not switchable, not in the mix, and a plan that lists it breaks R1."""
    from agent import toolkit as tk

    fs, card = _below_usual(mw.get_feed("x")), _card()
    plan = FundingPlan()
    for oid in BANK_IDS:
        tk.toggle_option(plan, oid, True)
    assert plan.options_on == []
    forged = FundingPlan(options_on=["webank_home_wc"])
    assert "R1" in {v.rule_id for v in blocking(check_plan(forged))}
    assert not blocking(check_plan(FundingPlan(options_on=["webank_pot_deposit", "partner_bank_fx"])))
    a = F.funding_mix(forged, card, None, fs)
    b = F.funding_mix(FundingPlan(), card, None, fs)
    assert [p.key for p in a.parts] == [p.key for p in b.parts]
    assert not {p.key for p in a.parts} & BANK_IDS
    assert [p.amount.value for p in a.parts] == [p.amount.value for p in b.parts]


def test_pot_card_is_never_pledged_and_fx_card_is_the_registering_bank() -> None:
    cards = {r.option.id: r.option for r in F.bank_cards(mw.get_feed("x"))}
    pot = cards["webank_pot_deposit"]
    assert "never pledged" in pot.conditions and "R3" in pot.rule_ids
    fx = cards["partner_bank_fx"]
    assert fx.card == "partner_bank" and "statements" in fx.conditions and "R4" in fx.rule_ids


# ------------------------------------------------------------------ in the journey


def _to_funding(d: Driver) -> None:
    _to_cost(d)
    d.reply("looks_right")
    assert d.state.step == "funding"


def test_funding_screen_shows_bank_cards_and_says_the_yes_beat(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_funding(d)
    fo = d.widgets("funding_options")[-1].payload
    # the demo feed sits at the usual level, so there's no home working-capital card
    assert {c.id for c in fo.bank_cards} == {"webank_pot_deposit", "partner_bank_fx"}
    assert all(c.variant in ("webank", "partner_bank") and c.as_of for c in fo.bank_cards)
    assert not {c.id for c in fo.options} & BANK_IDS
    said = [o.beat.key for o in d.outs if o.beat is not None]
    assert "webank_yes" in said and "webank_yes_home" not in said


def test_funding_screen_with_room_below_usual(svc: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    real = mw.get_feed
    monkeypatch.setattr(mw, "get_feed", lambda owner, as_of=mw.BASE_AS_OF: _below_usual(real(owner, as_of)))
    d = Driver(svc)
    _to_funding(d)
    w = d.widgets("funding_options")[-1]
    home = next(c for c in w.payload.bank_cards if c.id == "webank_home_wc")
    assert home.amount == "funding.webank.home_headroom" and home.amount in w.figures
    assert home.note_rule == "R2" and home.note
    beat = next(o.beat for o in d.outs if o.beat is not None and o.beat.key == "webank_yes_home")
    assert "{{fig:funding.webank.home_headroom}}" in beat.must
    # switching the home loan into the plan is refused with R1; the plan doesn't change
    before = d.state.funding.model_dump()  # type: ignore[union-attr]
    d.event("funding_options", "toggle_option", True, {"id": "webank_home_wc", "on": True})
    assert [c.payload.rule_id for c in d.widgets("rule_card")] == ["R1"]
    assert d.state.funding.model_dump() == before  # type: ignore[union-attr]
    d.event("funding_options", "toggle_option", True, {"id": "webank_pot_deposit", "on": True})
    assert not d.widgets("rule_card") and d.state.funding.options_on == []  # type: ignore[union-attr]
