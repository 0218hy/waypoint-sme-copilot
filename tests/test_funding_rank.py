"""Per-owner eligibility and an ordinal ranking of the funding routes (judge memo §1b, prereg addendum (11)).

A route is open to an owner only from what Waypoint already knows: spare cash above zero, a profit to set
aside from, savings they've put in, a partner they'd consider, a unit chosen. The open routes are ranked by
code on effective cost (the partner's profit share counted as a cost), weeks until the money is in hand,
ownership given up, then the change in floor risk, and shown as words, never as a score.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

import pytest

from sim.chen import generate_chen
from tests.test_journey import Driver, _to_cost, svc  # noqa: F401  (fixture re-export)
from tools import funding as F
from tools import params as P
from tools import plan as PL
from tools.costs import estimate_costs
from tools.data import load_catalogue, unit_by_id
from tools.models import FundingPlan, MoneyRange, Profile

WORDS = {
    "cheapest",
    "no_cost",
    "costs_profit_share",
    "fastest",
    "keeps_ownership",
    "gives_up_ownership",
    "lowers_floor_risk",
    "raises_floor_risk",
    "floor_risk_unchanged",
    "changes_timing",
}


@pytest.fixture(scope="module")
def feed():  # type: ignore[no-untyped-def]
    return generate_chen()


@pytest.fixture(scope="module")
def unit():  # type: ignore[no-untyped-def]
    return unit_by_id("u-tm-01")


@pytest.fixture(scope="module")
def card(unit):  # type: ignore[no-untyped-def]
    return estimate_costs(unit)


def _rank(feed: Any, card: Any, unit: Any, plan: FundingPlan) -> list[F.RankedRoute]:
    res = PL.simulate_plan(feed, card, plan, unit_available_from=unit.available_from)
    return F.rank_options(feed, card, plan, res, unit_available_from=unit.available_from)


def test_every_plan_route_has_ranking_fields() -> None:
    for e in load_catalogue().options:
        if not e.in_plan or e.status == "closed":
            continue
        assert e.cost_kind is not None, e.id
        if e.cost_kind != "timing":
            assert e.speed_weeks is not None and e.dilution is not None, e.id
            assert e.eligible_when_en and e.eligible_when_zh, e.id


def test_default_owner_sees_three_ranked_routes_and_two_not_yet(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    out = _rank(feed, card, unit, FundingPlan())
    ranked = [r.id for r in out if r.ranked]
    assert set(ranked) == {"spare_cash", "setaside", "landlord_terms"}
    assert [r.id for r in out if r.eligible and not r.ranked] == ["staged_contractor", "pre_investment"]
    not_yet = {r.id: r for r in out if not r.eligible}
    assert set(not_yet) == {"own_savings", "partner_equity"}
    assert "Add my savings" in (not_yet["own_savings"].why_not or "")
    assert "local partner" in (not_yet["partner_equity"].why_not or "")
    # order: ranked first, then timing-only routes, then those not open yet
    assert [r.ranked for r in out[:3]] == [True] * 3 and all(not r.eligible for r in out[-2:])
    by = {r.id: r for r in out}
    assert by["spare_cash"].weeks is not None and by["spare_cash"].weeks.value == 0
    assert "fastest" in by["spare_cash"].words
    assert all("keeps_ownership" in by[i].words and "no_cost" in by[i].words for i in ranked)
    assert by["staged_contractor"].words == ["changes_timing"]


def test_partner_profit_share_is_a_cost_and_ranks_after_own_cash(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    plan = FundingPlan(own_savings_cny=Decimal(400000), partner_equity_share=Decimal("0.30"))
    out = [r for r in _rank(feed, card, unit, plan) if r.ranked]
    ids = [r.id for r in out]
    assert ids[-1] == "partner_equity" and ids[0] == "own_savings"
    partner = out[-1]
    assert partner.cost is not None and partner.cost.value == Decimal("0.30")
    assert partner.dilution is not None and partner.dilution.value == Decimal("0.30")
    assert {"costs_profit_share", "gives_up_ownership"} <= set(partner.words)
    assert "cheapest" not in partner.words
    assert all("cheapest" in r.words and "keeps_ownership" in r.words for r in out[:-1])
    # partner money is in hand once the Singapore company exists (the incorporate milestone)
    res = PL.simulate_plan(feed, card, plan, unit_available_from=unit.available_from)
    assert partner.weeks is not None and partner.weeks.value == res.milestone_weeks["incorporate"]


def test_sort_keys_in_order(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    plan = FundingPlan(own_savings_cny=Decimal(400000), partner_equity_share=Decimal("0.30"))
    out = [r for r in _rank(feed, card, unit, plan) if r.ranked]

    def k(r: F.RankedRoute) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        def v(f: Any) -> Decimal:
            return Decimal("1e9") if f is None or f.value is None else Decimal(f.value)

        return (v(r.cost), v(r.weeks), v(r.dilution), v(r.floor_change))

    keys = [k(r) for r in out]
    assert keys == sorted(keys)


def test_floor_change_is_route_on_minus_off_on_the_same_runs(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    plan = FundingPlan()
    by = {r.id: r for r in _rank(feed, card, unit, plan)}
    inp = PL.build_inputs(feed, card, plan, unit_available_from=unit.available_from)
    runs, seed = P.inum("mc_runs"), P.default_seed()
    on = int(PL.simulate(inp, float(plan.setaside_share), runs, seed).floor_breach.sum())
    off = int(PL.simulate(inp, 0.0, runs, seed).floor_breach.sum())
    fc = by["setaside"].floor_change
    assert fc is not None and fc.value == (Decimal(on - off) / runs).quantize(Decimal("0.0001"))
    assert fc.source.ref == "rank_options" and fc.unit == "pct"
    word = "lowers_floor_risk" if on < off else "raises_floor_risk" if on > off else "floor_risk_unchanged"
    assert word in by["setaside"].words


def test_eligibility_from_owner_data(card) -> None:  # type: ignore[no-untyped-def]
    spare = F.spare_cash(Profile(spare_cash_cny=Decimal(0)))
    assert not F.route_eligible("spare_cash", Profile(), card, FundingPlan(), spare)
    some = F.spare_cash(Profile(spare_cash_cny=Decimal(1)))
    assert F.route_eligible("spare_cash", Profile(), card, FundingPlan(), some)
    loss = Profile(monthly_profit_cny=MoneyRange(low=Decimal(-10), high=Decimal(-5)))
    assert not F.route_eligible("setaside", loss, card, FundingPlan(), spare)
    assert not F.route_eligible("setaside", Profile(), card, FundingPlan(), spare)  # profit not known
    assert not F.route_eligible("own_savings", Profile(), card, FundingPlan(), spare)
    assert F.route_eligible("own_savings", Profile(), card, FundingPlan(own_savings_cny=Decimal(1)), spare)
    assert not F.route_eligible("partner_equity", Profile(), card, FundingPlan(), spare)
    open_to_one = FundingPlan(partner_equity_share=Decimal("0.3"))
    assert F.route_eligible("partner_equity", Profile(), card, open_to_one, spare)
    no_unit = card.model_copy(update={"rent_monthly_sgd": None, "rent_free_months": None})
    assert not F.route_eligible("landlord_terms", Profile(), no_unit, FundingPlan(), spare)
    assert F.route_eligible("landlord_terms", Profile(), card, FundingPlan(), spare)


def test_words_are_words_never_a_score(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    plan = FundingPlan(own_savings_cny=Decimal(200000), partner_equity_share=Decimal("0.30"))
    a = _rank(feed, card, unit, plan)
    for r in a:
        assert set(r.words) <= WORDS, r.words
        assert not any(re.search(r"\d", w) for w in r.words)
    assert a == _rank(feed, card, unit, plan)  # deterministic: same seed, same order and words
    zh = F.rank_options(
        feed, card, FundingPlan(), PL.simulate_plan(feed, card, FundingPlan()), lang="zh"
    )
    assert "积蓄" in (next(r for r in zh if r.id == "own_savings").why_not or "")


# ------------------------------------------------------------------ in the journey


def _to_funding(d: Driver) -> None:
    _to_cost(d)
    d.reply("looks_right")
    assert d.state.step == "funding"


def test_funding_card_ranked_with_words_and_reranked_when_savings_go_in(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_funding(d)
    w = d.widgets("funding_options")[-1]
    fo = w.payload
    assert {c.id for c in fo.not_yet} == {"own_savings", "partner_equity"}
    assert all(c.why_not and c.amount is None for c in fo.not_yet)
    assert not {c.id for c in fo.options} & {c.id for c in fo.not_yet}
    ranked = [c for c in fo.options if c.why is not None]
    assert ranked and ranked == fo.options[: len(ranked)]
    for c in ranked:
        assert c.words and set(c.words) <= WORDS
        assert c.why is not None
        for fid in (c.why.cost, c.why.weeks, c.why.dilution, c.why.floor_change):
            assert fid is None or fid in w.figures
    d.reply("add_savings")
    d.reply("v4")
    assert len(d.widgets("funding_options")) == 1  # this turn's outputs: the card again, re-ranked
    fo2 = d.widgets("funding_options")[-1].payload
    assert "own_savings" in {c.id for c in fo2.options}
    assert {c.id for c in fo2.not_yet} == {"partner_equity"}
    assert fo2.options[0].id == "own_savings" and "keeps_ownership" in fo2.options[0].words
    # picking the same amount again doesn't open or close a route: no new card
    d.reply("add_savings")
    d.reply("v2")
    assert d.widgets("funding_options") == []
