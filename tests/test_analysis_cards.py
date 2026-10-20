"""Business-analysis cards: the business at a glance (tools/ratios.py), judge-response memo §3."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from agent.render import fmt_figure
from mock_webank.feed import get_feed
from tests.test_journey import Driver, svc  # noqa: F401  (fixture re-export)
from tools import ratios as R
from tools.figures import SourceKind
from tools.models import FeedSnapshot, ProfitMonth


def _by(fs: FeedSnapshot) -> dict[str, Any]:
    return {f.id: f for f in R.chain_ratios(fs)}


def test_ratios_are_worked_out_from_the_feed_alone() -> None:
    fs = get_feed("owner")
    figs = _by(fs)
    months = sorted(fs.profit_history, key=lambda m: m.month)
    ttm = months[-12:]
    rev = sum((m.revenue_cny for m in ttm), Decimal(0))
    prof = sum((m.operating_profit_cny for m in ttm), Decimal(0))
    assert figs["ratio.op_margin_ttm"].value == prof / rev
    assert figs["ratio.revenue_per_shop_month"].value == rev / 12 / fs.shops
    out = fs.monthly_payroll_cny + fs.monthly_loan_repayment_cny + fs.home_commitments_monthly_cny
    assert figs["ratio.cash_runway"].value == fs.cash_balance_cny / out
    assert figs["ratio.dscr"].value == prof / 12 / fs.monthly_loan_repayment_cny
    after = (prof / 12 - fs.owner_drawings_monthly_cny) / fs.monthly_loan_repayment_cny
    assert figs["ratio.dscr_after_drawings"].value == after
    # every ratio names its inputs, and every input is a feed figure (or a figure computed from them)
    for fid, f in figs.items():
        if fid.startswith("ratio."):
            assert f.inputs and all(i in figs for i in f.inputs), fid
        else:
            assert f.source.kind == SourceKind.FEED, fid
    assert "overstated" in (figs["ratio.cash_runway"].source.note or "")


def test_margin_trend_is_against_the_same_months_a_year_earlier() -> None:
    fs = get_feed("owner")
    months = sorted(fs.profit_history, key=lambda m: m.month)
    recent = months[-3:]
    ago = [m for m in months if m.month in {r.month.replace(year=r.month.year - 1) for r in recent}]
    assert len(ago) == 3
    figs = _by(fs)

    def margin(ms: list[ProfitMonth]) -> Decimal:
        return sum((m.operating_profit_cny for m in ms), Decimal(0)) / sum(
            (m.revenue_cny for m in ms), Decimal(0)
        )

    assert figs["ratio.margin_recent_3m"].value == margin(recent)
    assert figs["ratio.margin_year_ago_3m"].value == margin(ago)


def test_short_history_gives_missing_trend_not_a_month_on_month_one() -> None:
    fs = get_feed("owner")
    short = fs.model_copy(update={"profit_history": fs.profit_history[-6:]})
    figs = _by(short)
    assert figs["ratio.margin_recent_3m"].is_missing and figs["ratio.margin_year_ago_3m"].is_missing
    assert figs["ratio.op_margin_ttm"].is_missing


def test_times_unit_formats_in_both_languages() -> None:
    f = _by(get_feed("owner"))["ratio.dscr"]
    assert fmt_figure(f, "en").endswith("x") and fmt_figure(f, "zh").endswith("倍")


def test_singapore_ratios_use_fx_and_the_last_year_of_profit() -> None:
    from tools.figtools import derived

    fs = get_feed("owner")
    inv = derived("econ.investment_likely", "inv", "SGD", 200000, tool="t")
    bad = derived("econ.investment_bad", "inv", "SGD", 230000, tool="t")
    ebitda = derived("econ.ref.ebitda_month", "e", "SGD", 10000, tool="t")
    figs = {f.id: f for f in R.singapore_ratios(fs, inv, bad, ebitda)}
    prof = sum(
        (m.operating_profit_cny for m in sorted(fs.profit_history, key=lambda m: m.month)[-12:]), Decimal(0)
    )
    fx = Decimal("5.25")
    assert figs["ratio.sg_investment_share"].value == Decimal(200000) * fx / prof
    assert figs["ratio.sg_investment_share_bad"].value == Decimal(230000) * fx / prof
    assert figs["ratio.sg_vs_home_shops"].value == Decimal(10000) * fx / (prof / 12 / fs.shops)


def test_profile_step_shows_the_glance_card_with_the_feed(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    d.run(init=True)
    d.event("consent_card", "consent", True)
    cards = d.widgets("business_glance")
    assert cards, "the glance card follows the profile card when the feed is consented"
    w = cards[-1]
    keys = [r.key for r in w.payload.rows]
    assert keys == ["margin", "trend", "per_shop", "runway", "dscr"]
    assert all(r.figure in w.figures and r.figure in w.display for r in w.payload.rows)
    assert next(r for r in w.payload.rows if r.key == "runway").caveat


def test_no_glance_card_without_the_feed(svc: Any) -> None:  # noqa: F811
    d = Driver(svc, host_mode="standalone")
    d.run(init=True)
    assert not d.widgets("business_glance")


def test_runway_is_none_safe_with_zero_outflow() -> None:
    fs = get_feed("owner").model_copy(
        update={
            "monthly_payroll_cny": Decimal(0),
            "monthly_loan_repayment_cny": Decimal(0),
            "home_commitments_monthly_cny": Decimal(0),
            "profit_history": [
                ProfitMonth(
                    month=date(2025, m, 1), revenue_cny=Decimal(100), operating_profit_cny=Decimal(10)
                )
                for m in range(1, 13)
            ],
        }
    )
    figs = _by(fs)
    assert figs["ratio.cash_runway"].is_missing and figs["ratio.dscr"].is_missing


def test_goal_tab_shows_the_glance_card(svc: Any) -> None:  # noqa: F811
    from tests.test_journey import _approve, _to_goal_plan

    d = Driver(svc)
    _to_goal_plan(d)
    _approve(d)
    dash = svc.goal_dashboard(d.state)
    glance = [w for w in dash["widgets"] if w["payload"]["type"] == "business_glance"]
    assert len(glance) == 1
    w = glance[0]
    assert all(r["figure"] in w["display"] for r in w["payload"]["rows"])


# ------------------------------------------------------------------ unit economics (tools/unit_econ.py)


def _demo() -> tuple[Any, Any]:
    from agent import toolkit as tk
    from tools import costs as C

    u = tk.unit("u-t1-01")
    return u, C.estimate_costs(u)


def test_contribution_per_cup_counts_gst_and_the_delivery_commission() -> None:
    from tools import params as P
    from tools import unit_econ as UE

    u, _ = _demo()
    s = UE.shop(u)
    g = 1 + P.fnum("gst_rate")
    price = P.fnum("cup_price_sgd")
    expect = (
        price
        - P.fnum("variable_cost_per_cup_sgd") * g
        - price * P.fnum("delivery_share") * P.fnum("delivery_commission") * g
    )
    assert s.contribution == pytest.approx(expect)
    reg = UE.shop(u, registered=True)
    assert reg.net_price == pytest.approx(price / g) and reg.gst == 1.0
    # monthly fixed costs: GST on rent, service charge and running costs is a cost while unregistered
    assert s.fixed(0) - reg.fixed(0) == pytest.approx(
        (s.base_rent + s.service + s.utilities + s.other) * (g - 1)
    )


def test_gst_registration_switches_on_above_the_threshold() -> None:
    from tools import params as P
    from tools import unit_econ as UE

    u, _ = _demo()
    per_cup_year = P.fnum("cup_price_sgd") * P.fnum("opening_days_per_month") * 12
    edge = P.fnum("gst_registration_threshold_sgd") / per_cup_year
    assert not UE.registered_at(u, int(edge)) and UE.registered_at(u, int(edge) + 1)


def test_investment_is_the_card_less_the_running_reserve() -> None:
    from tools import params as P
    from tools import unit_econ as UE

    u, card = _demo()
    inv = UE.investment(card, "likely")
    reserve = next(ln for ln in card.lines if ln.key == "running_reserve")
    assert inv.total + inv.reserve == pytest.approx(float(card.total_likely_sgd))
    assert inv.reserve > float(reserve.likely_sgd)  # its GST share comes out too
    rent = float(card.rent_monthly_sgd or 0)
    supplies = P.tri("utilities_monthly_sgd").likely + P.fnum("other_fixed_monthly_sgd")
    assert inv.reserve - float(reserve.likely_sgd) == pytest.approx(
        P.fnum("gst_rate") * P.fnum("reserve_months") * (rent + supplies)
    )
    dep = next(ln for ln in card.lines if ln.key == "security_deposit")
    assert inv.refund_end == pytest.approx(float(dep.likely_sgd))
    assert UE.investment(card, "bad").total > inv.total


def test_tax_is_partial_exemption_only() -> None:
    from tools import unit_econ as UE

    assert UE.corporate_tax(-5000) == 0
    assert UE.corporate_tax(10000) == pytest.approx(0.17 * 2500)
    assert UE.corporate_tax(200000) == pytest.approx(0.17 * (200000 - 7500 - 95000))
    assert UE.corporate_tax(300000) == pytest.approx(0.17 * (300000 - 102500))


def test_ramp_curve_is_the_memo_formula() -> None:
    import math

    from tools import unit_econ as UE

    r = UE.ramp("likely", 12)
    assert r[0] == pytest.approx(0.6) and r[3] == pytest.approx(1 - 0.4 * math.exp(-1))
    assert all(a < b for a, b in zip(r, r[1:], strict=False)) and UE.ramp("bad", 1)[0] == pytest.approx(0.5)


def test_payback_is_the_first_month_cumulative_cash_reaches_the_investment() -> None:
    from tools import unit_econ as UE

    u, card = _demo()
    inv = UE.investment(card, "likely").total
    lease = UE.run_lease(u, card, 400, "likely")
    m = lease.payback_month
    assert m is not None
    assert sum(lease.cash[:m]) >= inv > sum(lease.cash[: m - 1])
    assert UE.run_lease(u, card, 250, "likely").payback_month is None  # below break-even: never


def test_cups_needed_is_the_smallest_level_that_pays_back_within_the_lease() -> None:
    from tools import unit_econ as UE

    u, card = _demo()
    for case in ("likely", "bad"):
        c = UE.cups_needed(u, card, case)  # type: ignore[arg-type]
        assert c is not None
        assert UE.run_lease(u, card, c, case).payback_month is not None  # type: ignore[arg-type]
        assert UE.run_lease(u, card, c - 1, case).payback_month is None  # type: ignore[arg-type]
    assert UE.cups_needed(u, card, "bad") > UE.cups_needed(u, card, "likely")  # type: ignore[operator]
    assert UE.cups_needed(u, card, "likely") > round(UE.break_even_cups(u))  # type: ignore[operator]


def test_npv_falls_with_the_discount_rate_and_in_the_bad_case() -> None:
    from tools import unit_econ as UE

    u, card = _demo()
    a, b, c = (UE.npv(u, card, 400, "likely", r) for r in (0.08, 0.12, 0.15))
    assert a > b > c
    assert UE.npv(u, card, 400, "bad", 0.12) < b


def test_unit_compare_break_even_is_the_card_s_break_even() -> None:
    from agent import toolkit as tk
    from tools import sites as S
    from tools import unit_econ as UE

    u, _ = _demo()
    assert S.break_even(u).value == round(UE.break_even_cups(u))
    figs, payload, _ = tk.unit_economics(u, _demo()[1], tk.Profile(), "en")
    by = {f.id: f for f in figs}
    assert by["econ.breakeven"].value == S.break_even(u).value


def test_every_card_figure_has_a_source_and_estimates_are_labelled() -> None:
    from agent import toolkit as tk
    from agent.turn import _fig_ids

    u, card = _demo()
    figs, payload, _ = tk.unit_economics(
        u, card, tk.Profile(expected_sg_cups_per_day=380), "en", fs=get_feed("owner")
    )
    by = {f.id: f for f in figs}
    referenced = [i for i in _fig_ids(payload) if "." in i and i in by]
    assert {"econ.breakeven", "econ.cups_needed_likely", "lvl.owner.payback_likely"} <= set(referenced)
    for i in referenced:
        assert by[i].source.kind and by[i].source.ref, i
    assert by["lvl.owner.cups"].source.kind == SourceKind.OWNER
    assert all(by[i].source.url for i in referenced if i.startswith("econ.bench."))
    assert any(ln.estimate for ln in payload.headline)
    assert [r.key for r in payload.chain] == ["sg_share", "sg_vs_home"]
    assert payload.rows[-1].owner and payload.rows[-1].key == "owner"


def test_not_within_the_lease_is_said_not_shown_as_missing() -> None:
    from agent import toolkit as tk

    u, card = _demo()
    figs, payload, _ = tk.unit_economics(u, card, tk.Profile(), "en")
    by = {f.id: f for f in figs}
    f = by[payload.rows[0].payback_likely]
    assert f.is_missing
    assert fmt_figure(f, "en") == "not within the lease" and fmt_figure(f, "zh") == "租约内收不回"


def test_cost_step_shows_the_card_and_the_owner_s_own_figure(svc: Any) -> None:  # noqa: F811
    from tests.test_journey import _to_cost

    d = Driver(svc)
    _to_cost(d)
    assert d.widgets("unit_economics"), "the card follows the cost card"
    types = [w.payload.type for w in d.widgets()]
    assert types.index("unit_economics") > types.index("cost_breakdown")
    d.event("unit_economics", "edit", 520, {"field": "owner_cups"})
    assert d.state.profile.expected_sg_cups_per_day == 520
    w = d.widgets("unit_economics")[-1]
    assert w.payload.rows[-1].owner and w.display[w.payload.rows[-1].cups].startswith("520")
    assert d.state.pending is not None and d.state.pending.slot == "adjust"
    d.event("unit_economics", "edit", "lots", {"field": "owner_cups"})  # not a number: ignored
    assert d.state.profile.expected_sg_cups_per_day == 520
    d.reply("looks_right")
    assert d.state.step == "funding"


def test_goal_tab_has_the_unit_economics_and_the_singapore_rows(svc: Any) -> None:  # noqa: F811
    from tests.test_journey import _approve, _to_goal_plan

    d = Driver(svc)
    _to_goal_plan(d)
    _approve(d)
    dash = svc.goal_dashboard(d.state)
    by_type = {w["payload"]["type"]: w for w in dash["widgets"]}
    econ = by_type["unit_economics"]
    assert econ["payload"]["editable"] is False and econ["payload"]["rows"]
    glance = by_type["business_glance"]
    assert [r["key"] for r in glance["payload"]["singapore"]] == ["sg_share", "sg_vs_home"]
    assert all(r["figure"] in glance["display"] for r in glance["payload"]["singapore"])
