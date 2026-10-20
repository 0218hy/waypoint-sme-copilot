from __future__ import annotations

import time
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from sim.chen import generate_chen
from tools import params as P
from tools.costs import estimate_costs
from tools.data import load_units, unit_by_id
from tools.figures import Figure
from tools.funding import funding_gap, funding_mix, funding_options, safety_floor, spare_cash
from tools.models import FundingPlan, MoneyRange, Profile
from tools.plan import (
    _risk,
    build_inputs,
    find_wall,
    plan_figures,
    preview,
    risk_upper,
    simulate,
    simulate_plan,
)
from tools.repairs import find_repairs
from tools.timeline import build_timeline

SEED = 20261019


@pytest.fixture(scope="module")
def feed():  # type: ignore[no-untyped-def]
    return generate_chen()


@pytest.fixture(scope="module")
def unit():  # type: ignore[no-untyped-def]
    return unit_by_id("u-tm-01")


@pytest.fixture(scope="module")
def card(unit):  # type: ignore[no-untyped-def]
    return estimate_costs(unit)


@pytest.fixture(scope="module")
def inputs(feed, card, unit):  # type: ignore[no-untyped-def]
    return build_inputs(feed, card, FundingPlan(), unit_available_from=unit.available_from)


@pytest.fixture(scope="module")
def result(feed, card, unit):  # type: ignore[no-untyped-def]
    return simulate_plan(feed, card, FundingPlan(), unit_available_from=unit.available_from)


# ------------------------------------------------------------------ floor, spare, gap (§6.5, §6.4)


def test_floor_buffer_spare(feed) -> None:  # type: ignore[no-untyped-def]
    fl = safety_floor(feed)
    assert fl is not None
    wpm = Decimal("4.345")
    assert fl.floor_cny == (
        feed.monthly_payroll_cny / wpm * 8 + 2 * feed.monthly_loan_repayment_cny
    ).quantize(Decimal(1))
    assert fl.buffer_cny == (feed.monthly_payroll_cny / wpm * 4).quantize(Decimal(1))
    sp = spare_cash(feed)
    assert sp.value == feed.cash_balance_cny - fl.floor_cny - fl.buffer_cny


def test_missing_is_not_zero() -> None:
    prof = Profile(monthly_profit_cny=None)
    assert safety_floor(prof) is None
    assert spare_cash(prof).value is None


def test_profile_spare_from_owner_and_gap(card) -> None:  # type: ignore[no-untyped-def]
    prof = Profile(
        monthly_profit_cny=MoneyRange(low=Decimal(200000), high=Decimal(220000)),
        spare_cash_cny=Decimal(500000),
    )
    sp = spare_cash(prof)
    assert sp.value == Decimal(500000) and sp.source.kind == "owner"
    gap = funding_gap(card, sp)
    assert gap.value == (card.total_likely_sgd * card.fx_cny_per_sgd - 500000).quantize(Decimal(1))
    assert funding_gap(card, spare_cash(Profile())).value is None


def test_funding_options_and_mix(feed, card, result) -> None:  # type: ignore[no-untyped-def]
    opts = {o.option.id: o for o in funding_options(feed, card, FundingPlan())}
    assert "webank_loan" not in opts and "china_guarantee" not in opts
    assert opts["spare_cash"].amount is not None and opts["spare_cash"].amount.value == Decimal(500000)
    assert opts["setaside"].amount is not None and opts["setaside"].amount.value
    mix = funding_mix(FundingPlan(), card, result, feed)
    assert sum(p.amount.value or 0 for p in mix.parts) == mix.total.value
    assert mix.setaside_months is not None


# ------------------------------------------------------------------ the plan model (§6.6)


def test_seeded_output_is_identical(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    a = simulate_plan(feed, card, FundingPlan(), seed=11, unit_available_from=unit.available_from)
    b = simulate_plan(feed, card, FundingPlan(), seed=11, unit_available_from=unit.available_from)
    assert a.model_dump() == b.model_dump()
    assert a.seed == 11 and a.runs == P.inum("mc_runs")
    c = simulate_plan(feed, card, FundingPlan(), seed=12, unit_available_from=unit.available_from)
    assert c.chart.home_p05 != a.chart.home_p05  # the pot moves in fixed monthly steps


def test_wall_matches_floor_risk_limit(inputs) -> None:  # type: ignore[no-untyped-def]
    """The wall is judged on the Wilson 95% upper bound of the floor risk, not the point estimate."""
    wall = float(find_wall(inputs))
    limit = P.fnum("floor_risk_limit")
    step = P.fnum("wall_step")
    runs = P.inum("mc_runs")
    s = 0.0
    while s <= wall + 1e-9:  # every share up to the wall is safe, with its upper bound
        assert risk_upper(inputs, round(s, 6), runs, SEED) <= limit
        assert _risk(inputs, round(s, 6), runs, SEED) < risk_upper(inputs, round(s, 6), runs, SEED)
        s += step
    if wall < 1.0:
        assert risk_upper(inputs, round(wall + step, 6), runs, SEED) > limit


def test_wall_is_safe_on_fresh_draws_at_every_seed(inputs) -> None:  # type: ignore[no-untyped-def]
    """The judge's probe (2026-10-20): at 1,000 runs and the point estimate, one seed in ten opened the
    wall to 100% where 20,000 runs put the risk near 6%. Now each seed's wall holds on 20,000 fresh runs."""
    limit = P.fnum("floor_risk_limit")
    for seed in range(SEED, SEED + 5):
        wall = float(find_wall(inputs, seed=seed))
        assert _risk(inputs, wall, 20_000, 7) <= limit, seed


def test_preview_is_a_subset_of_the_full_runs(feed, card, unit, inputs) -> None:  # type: ignore[no-untyped-def]
    """Common draws: the preview's runs are the first runs of the full solve, and its floor risk is the
    full solve's (the runs the wall was judged on), so the slider can't show a different risk at the wall."""
    full, few = P.inum("mc_runs"), P.inum("mc_runs_preview")
    a, b = simulate(inputs, 0.4, full, SEED), simulate(inputs, 0.4, few, SEED)
    assert np.array_equal(a.home[:few], b.home) and np.array_equal(a.setaside[:few], b.setaside)
    assert all(np.array_equal(a.weeks[k][:few], b.weeks[k]) for k in a.weeks)
    for share in (Decimal("0.4"), find_wall(inputs)):
        pv = preview(feed, card, FundingPlan(), share, unit_available_from=unit.available_from)
        solve = simulate_plan(
            feed, card, FundingPlan(setaside_share=share), unit_available_from=unit.available_from
        )
        assert pv.runs == few and pv.floor_risk_runs == full
        assert pv.floor_risk == solve.floor_risk and pv.wall_share == solve.wall_share
        assert pv.floor_risk <= P.num("floor_risk_limit")


def test_setaside_runs_as_the_signed_instruction(inputs) -> None:  # type: ignore[no-untyped-def]
    """The plan simulates the instruction the owner signs: a fixed monthly amount, in the first week of
    each month only, skipped that month if it would leave home cash below floor + buffer."""
    from tools.plan import _transfer_weeks, monthly_amount

    sim = simulate(inputs, 0.6, 2000, SEED)
    amount = monthly_amount(inputs, 0.6)
    due = _transfer_weeks(inputs)
    fb = inputs.floor + inputs.buffer
    assert np.all(sim.setaside[:, ~due] == 0)
    took = sim.setaside > 0
    assert np.all(sim.setaside[took] == amount)
    assert np.all(sim.home[took] >= fb - 1e-6)
    opened = sim.weeks["opening"]
    for t in np.flatnonzero(due):
        if sim.paused[t]:
            continue
        active = ~(opened < t)  # opened runs stop (the goal is done)
        skipped = active & ~took[:, t]
        before = sim.home[:, t] + sim.setaside[:, t]  # cash just before the transfer was decided
        assert np.all(before[skipped] - amount < fb + 1e-6)
    assert took.any() and (~took[:, due]).any(), "some months run, some are skipped"


def test_result_wall_and_r5_consistency(result) -> None:  # type: ignore[no-untyped-def]
    assert result.setaside_share <= result.wall_share
    assert result.floor_risk <= P.num("floor_risk_limit")


def test_lease_never_before_first_main_transfer(inputs) -> None:  # type: ignore[no-untyped-def]
    for s in (0.2, 0.4, 0.6, 1.0):
        sim = simulate(inputs, s, 1000, SEED)
        w = sim.weeks
        reached = np.isfinite(w["sign_lease"])
        assert np.all(w["sign_lease"][reached] > w["first_transfer"][reached])
        assert np.all(w["first_transfer"] >= w["setup_transfer"])
        assert np.all(w["setup_transfer"] >= w["incorporate"])
        assert np.all(w["incorporate"] > w["bank_registration"])
        assert np.all(w["bank_registration"] > w["odi_filing"])
        assert np.all(w["odi_filing"] > w["lender_consent"])
        opened = np.isfinite(w["opening"])
        assert np.all(w["opening"][opened] >= w["licence"][opened])


def test_opening_needs_full_reserve_and_first_transfer_needs_r6_money(inputs) -> None:  # type: ignore[no-untyped-def]
    sim = simulate(inputs, 0.4, 1000, SEED)
    runs = np.arange(sim.saved.shape[0])
    for key, col in (("first_transfer", 1), ("opening", 2)):
        wk = sim.weeks[key]
        ok = np.isfinite(wk)
        idx = wk[ok].astype(int)
        assert np.all(sim.saved[runs[ok], idx] >= sim.need[ok, col] - 1e-6)


def test_setasides_only_above_floor_plus_buffer(inputs) -> None:  # type: ignore[no-untyped-def]
    sim = simulate(inputs, 1.0, 500, SEED)
    after = sim.home  # cash after the set-aside each week
    took = sim.setaside > 0
    assert np.all(after[took] >= inputs.floor + inputs.buffer - 1e-6)


def test_r2_pause_stops_setasides_and_transfers(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    inp = build_inputs(feed, card, FundingPlan(), unit_available_from=unit.available_from, r2_pause_weeks=20)
    sim = simulate(inp, 0.4, 300, SEED)
    assert np.all(sim.setaside[:, :20] == 0)
    assert np.all(sim.weeks["setup_transfer"] >= 20)
    base = simulate(
        build_inputs(feed, card, FundingPlan(), unit_available_from=unit.available_from), 0.4, 300, SEED
    )
    assert np.median(sim.weeks["opening"]) > np.median(base.weeks["opening"])


def test_r2_pause_from_above_normal_feed(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    hot = feed.model_copy(update={"loan_balance_cny": feed.loan_balance_cny + Decimal(600000)})
    inp = build_inputs(hot, card, FundingPlan(), unit_available_from=unit.available_from)
    sim = simulate(inp, 0.4, 200, SEED)
    assert sim.paused[0] and not sim.paused[-1]
    assert np.all(sim.setaside[:, sim.paused] == 0)


def test_more_setaside_opens_no_later(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    weeks = [
        simulate_plan(
            feed, card, FundingPlan(setaside_share=Decimal(s)), unit_available_from=unit.available_from
        ).open_likely_week
        for s in ("0.3", "0.4", "0.5")
    ]
    assert all(w is not None for w in weeks)
    assert weeks[0] >= weeks[1] >= weeks[2]  # type: ignore[operator]


def test_savings_and_rent_free_bring_opening_forward(feed, card, unit, result) -> None:  # type: ignore[no-untyped-def]
    more = simulate_plan(
        feed, card, FundingPlan(own_savings_cny=Decimal(300000)), unit_available_from=unit.available_from
    )
    assert more.open_likely_week < result.open_likely_week  # type: ignore[operator]
    rf = simulate_plan(
        feed, card, FundingPlan(rent_free_months=Decimal(2)), unit_available_from=unit.available_from
    )
    assert rf.open_likely_week <= result.open_likely_week  # type: ignore[operator]


def test_chart_bands_are_ordered(result) -> None:  # type: ignore[no-untyped-def]
    c = result.chart
    assert len(c.weeks) == 156
    assert all(a <= b <= d for a, b, d in zip(c.pot_p10, c.pot_p50, c.pot_p90, strict=True))
    assert all(a <= b for a, b in zip(c.home_p05, c.home_p50, strict=True))
    assert set(c.floor) == {round(float(safety_floor(generate_chen()).floor_cny))}  # type: ignore[union-attr]
    assert [k for _, k in c.milestones][-1] == "opening"


def test_plan_from_profile_needs_start_and_runs(card) -> None:  # type: ignore[no-untyped-def]
    prof = Profile(
        monthly_profit_cny=MoneyRange(low=Decimal(200000), high=Decimal(220000)),
        monthly_payroll_cny=Decimal(280000),
        cash_balance_cny=Decimal(1400000),
        owner_drawings_monthly_cny=Decimal(78000),
        monthly_loan_repayment_cny=Decimal(45000),
    )
    with pytest.raises(ValueError):
        simulate_plan(prof, card, FundingPlan(), runs=200)
    r = simulate_plan(prof, card, FundingPlan(), runs=200, start_date=date(2026, 10, 19))
    assert r.open_likely_week is not None


def test_preview_is_fast(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    preview(feed, card, FundingPlan(), Decimal("0.4"), unit_available_from=unit.available_from)  # warm caches
    times = []
    for i in range(20):
        t = time.perf_counter()
        r = preview(
            feed,
            card,
            FundingPlan(),
            Decimal("0.30") + Decimal(i % 6) / 50,
            unit_available_from=unit.available_from,
        )
        times.append(time.perf_counter() - t)
        assert r.runs == 200
    assert sorted(times)[18] < 0.300  # p95 over 20 calls


def test_full_solve_under_five_seconds(feed, unit) -> None:  # type: ignore[no-untyped-def]
    card2 = estimate_costs(unit, seed=99)  # fresh inputs: no cached draws or wall
    t = time.perf_counter()
    simulate_plan(
        feed,
        card2,
        FundingPlan(setaside_share=Decimal("0.35")),
        seed=4242,
        unit_available_from=unit.available_from,
    )
    assert time.perf_counter() - t < 5.0


# ------------------------------------------------------------------ timeline (§6.7)


def test_timeline_legal_order_and_dates(result) -> None:  # type: ignore[no-untyped-def]
    tl = build_timeline(result)
    assert [m.id for m in tl] == [
        "lender_consent",
        "odi_filing",
        "bank_registration",
        "incorporate",
        "setup_transfer",
        "first_transfer",
        "sign_lease",
        "hiring",
        "fitout",
        "licence",
        "opening",
    ]
    hiring = next(m for m in tl if m.id == "hiring")
    assert hiring.latest_safe_week == result.open_likely_week, "hiring runs alongside: due by opening day"
    for a, b in zip(tl, tl[1:], strict=False):
        assert a.likely_week <= b.likely_week
    for m in tl:
        assert 0 <= m.act_by_week <= m.latest_safe_week
        assert m.likely_week <= m.latest_safe_week
    assert tl[-1].latest_safe_week == result.open_likely_week
    zh = build_timeline(result, lang="zh")
    assert zh[0].label.startswith("贷款行")


# ------------------------------------------------------------------ repairs (§6.8)


def test_repairs_pass_rules_and_are_sorted(feed, card, unit, inputs) -> None:  # type: ignore[no-untyped-def]
    alts = [estimate_costs(u) for u in load_units() if u.area_id == "TAMPINES" and u.id != unit.id]
    reps = find_repairs(
        feed,
        card,
        FundingPlan(setaside_share=Decimal("0.30")),
        alternatives=alts,
        unit_available_from=unit.available_from,
    )
    assert 2 <= len(reps) <= 3
    assert all(r.rules_ok for r in reps)
    assert all(r.new_floor_risk <= P.num("floor_risk_limit") for r in reps)
    weeks = [r.new_open_likely_week for r in reps]
    assert weeks == sorted(weeks)  # type: ignore[type-var]
    assert len({r.kind for r in reps}) == len(reps)
    for r in reps:
        if r.kind == "raise_share":
            assert Decimal(r.params["setaside_share"]) <= find_wall(inputs)


# ------------------------------------------------------------------ figure contract


def _pct_ok(figs: list[Figure]) -> None:
    for f in figs:
        if f.unit == "pct":
            for v in (f.value, f.low, f.high):
                assert v is None or Decimal(0) <= v <= Decimal(1), f.id


def test_every_pct_figure_is_a_fraction(feed, card, result) -> None:  # type: ignore[no-untyped-def]
    from tools.costs import cost_figures

    figs = plan_figures(result) + cost_figures(card) + (safety_floor(feed).figures)  # type: ignore[union-attr]
    for o in funding_options(feed, card, FundingPlan()):
        if o.amount is not None:
            figs.append(o.amount)
    _pct_ok(figs)
    assert {f.id for f in figs if f.unit == "pct"} >= {"plan.floor_risk", "plan.wall", "plan.setaside_share"}
