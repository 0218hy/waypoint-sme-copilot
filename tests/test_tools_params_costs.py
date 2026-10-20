from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import yaml

from tools import params as P
from tools.costs import cost_figures, due_totals_sgd, estimate_costs, missing_items, quick_cost_likely
from tools.data import unit_by_id
from tools.figures import FigureStore, Taint
from tools.models import ExtractedLine, ExtractedQuote


@pytest.fixture(scope="module")
def unit():  # type: ignore[no-untyped-def]
    return unit_by_id("u-tm-01")


@pytest.fixture(scope="module")
def card(unit):  # type: ignore[no-untyped-def]
    return estimate_costs(unit)


# ------------------------------------------------------------------ params


def test_every_param_has_value_unit_source_date() -> None:
    raw = yaml.safe_load(P.PARAMS_PATH.read_text(encoding="utf-8"))
    for key, entry in raw.items():
        for f in ("value", "unit", "source", "as_of", "note"):
            assert f in entry, f"{key} missing {f}"
        assert str(entry["source"]).strip(), key


def test_spec_13_defaults() -> None:
    assert P.fx() == Decimal("5.25")
    assert P.inum("floor_payroll_weeks") == 8 and P.inum("buffer_payroll_weeks") == 4
    assert P.num("floor_risk_limit") == Decimal("0.05")
    assert P.inum("deposit_months") == 3 and P.inum("reserve_months") == 3
    assert P.num("gst_rate") == Decimal("0.09") and P.num("cpf_employer_rate") == Decimal("0.17")
    assert P.inum("mc_runs") == 4000 and P.inum("mc_runs_preview") == 200
    assert P.tri("sg_account_weeks").model_dump() == {"low": 3.0, "likely": 6.0, "high": 12.0}
    assert P.num("pre_investment_cap_share") == Decimal("0.15")


def test_dated_param_and_overrides() -> None:
    assert P.dated("pwm_counter_attendant_wage_sgd", date(2026, 12, 1)) == 2295
    assert P.dated("pwm_counter_attendant_wage_sgd", date(2027, 8, 1)) == 2435
    v0 = P.version()
    with P.overrides({"fx_cny_per_sgd": 5.5}):
        assert P.fx() == Decimal("5.5") and P.version() != v0
    assert P.fx() == Decimal("5.25")


def test_rate_param_figures_are_fractions() -> None:
    for k in ("gst_rate", "cpf_employer_rate", "pre_investment_cap_share"):
        f = P.param_fig(k, k, "pct")
        assert f.value is not None and 0 <= f.value <= 1


# ------------------------------------------------------------------ cost card


def test_card_has_the_spec_lines_and_groups(card) -> None:  # type: ignore[no-untyped-def]
    keys = {ln.key for ln in card.lines}
    for k in (
        "security_deposit",
        "stamp_duty",
        "landlord_fitout_deposit",
        "aa_me_fees",
        "fitout",
        "equipment_pos",
        "opening_stock",
        "incorporation",
        "corp_secretary",
        "resident_director",
        "food_shop_licence",
        "pre_opening_wages",
        "recruitment",
        "running_reserve",
        "gst_fitout",
        "gst_services",
        "pre_opening_rent",
    ):
        assert k in keys
    assert set(card.by_group()) == {"lease", "fitout", "setup", "people", "reserve", "gst"}
    assert "work_pass_fees" not in keys  # hire_local


def test_totals_add_up_and_bad_is_a_quantile_not_worst_case(card) -> None:  # type: ignore[no-untyped-def]
    assert card.total_likely_sgd == sum(ln.likely_sgd for ln in card.lines)
    assert card.total_bad_sgd == sum(ln.bad_sgd for ln in card.lines)
    worst = sum(ln.high_sgd or ln.bad_sgd for ln in card.lines)
    assert card.total_likely_sgd < card.total_bad_sgd < worst
    for ln in card.lines:
        assert ln.low_sgd is not None and ln.high_sgd is not None
        assert ln.low_sgd <= ln.likely_sgd <= ln.bad_sgd <= ln.high_sgd + 1
    assert card.seed == P.default_seed() and card.bad_quantile == Decimal("0.90")


def test_deposit_is_three_months_gross_rent(card, unit) -> None:  # type: ignore[no-untyped-def]
    dep = next(ln for ln in card.lines if ln.key == "security_deposit")
    assert dep.likely_sgd == 3 * (unit.rent_monthly_sgd + unit.service_charge_monthly_sgd)
    assert dep.due == "sign_lease"


def test_seeded_reproducibility(unit) -> None:  # type: ignore[no-untyped-def]
    a, b = estimate_costs(unit, seed=7), estimate_costs(unit, seed=7)
    assert a.model_dump() == b.model_dump()
    c = estimate_costs(unit, seed=8)
    assert c.total_base_sgd == a.total_base_sgd  # the base estimate doesn't depend on the seed
    assert abs(c.total_likely_sgd - a.total_likely_sgd) < a.total_likely_sgd / 100  # the median barely does


def test_higher_rho_widens_the_bad_case(unit) -> None:  # type: ignore[no-untyped-def]
    with P.overrides({"cost_overrun_rho": 0.0}):
        lo = estimate_costs(unit).total_bad_sgd
    with P.overrides({"cost_overrun_rho": 0.9}):
        hi = estimate_costs(unit).total_bad_sgd
    assert hi > lo


def test_send_own_manager_adds_work_pass_and_ep_wage(unit, card) -> None:  # type: ignore[no-untyped-def]
    own = estimate_costs(unit, manager_plan="send_own")
    keys = {ln.key for ln in own.lines}
    assert "work_pass_fees" in keys
    wp = next(ln for ln in own.lines if ln.key == "work_pass_fees")
    assert wp.likely_sgd == P.num("work_pass_fee_sgd")


def test_fitout_level_orders_costs(unit) -> None:  # type: ignore[no-untyped-def]
    assert (
        quick_cost_likely(unit, "basic")
        < quick_cost_likely(unit, "standard")
        < quick_cost_likely(unit, "premium")
    )


def test_quick_cost_matches_card(card, unit) -> None:  # type: ignore[no-untyped-def]
    assert quick_cost_likely(unit) == card.total_likely_sgd


def _quote(
    amount: str, key: str = "fitout", status: str = "accepted", currency: str = "SGD"
) -> ExtractedQuote:
    return ExtractedQuote(
        doc_id="doc-1",
        lines=[
            ExtractedLine(
                id="l1",
                label="装修",
                amount=Decimal(amount),
                currency=currency,
                matched_key=key,
                status=status,
                confidence=0.9,
            )
        ],  # type: ignore[arg-type]
        exclusions=["拆除另计 (demolition extra)"],
    )


def test_accepted_quote_replaces_estimate_and_recomputes_gst(unit, card) -> None:  # type: ignore[no-untyped-def]
    q = estimate_costs(unit, quotes=[_quote("70000")])
    fit = next(ln for ln in q.lines if ln.key == "fitout")
    assert fit.from_quote and fit.source == "quote:doc-1" and fit.quote_sgd == Decimal("70000")
    a = P.tri("quote_variation_allowance")
    # a quoted line keeps its variation allowance: it can still overrun
    assert fit.mode_sgd == Decimal(str(round(70000 * (1 + a.likely))))
    assert Decimal("70000") <= fit.likely_sgd < fit.bad_sgd <= Decimal(str(70000 * (1 + a.high)))
    assert fit.low_sgd == Decimal("70000") and fit.high_sgd == Decimal(str(round(70000 * (1 + a.high))))
    g0 = next(ln for ln in card.lines if ln.key == "gst_fitout").likely_sgd
    g1 = next(ln for ln in q.lines if ln.key == "gst_fitout").likely_sgd
    assert g1 < g0  # 70k < 76.8k estimate


def test_pending_or_rejected_quote_is_ignored(unit, card) -> None:  # type: ignore[no-untyped-def]
    for st in ("pending", "rejected", "check"):
        q = estimate_costs(unit, quotes=[_quote("1", status=st)])
        assert q.total_likely_sgd == card.total_likely_sgd


def test_cny_quote_converted_at_fx(unit) -> None:  # type: ignore[no-untyped-def]
    q = estimate_costs(unit, quotes=[_quote("367500", currency="CNY")])
    assert next(ln for ln in q.lines if ln.key == "fitout").quote_sgd == Decimal("70000")


def test_missing_items_lists_uncovered_and_excluded(unit) -> None:  # type: ignore[no-untyped-def]
    quote = _quote("70000")
    q = estimate_costs(unit, quotes=[quote])
    items = missing_items(q, [quote])
    kinds = {(m.key, m.kind) for m in items}
    assert ("equipment_pos", "no_quote") in kinds
    assert ("fitout", "no_quote") not in kinds
    assert ("fitout", "excluded") in kinds
    assert "equipment_pos" in q.missing


def test_cost_figures_cny_and_taint_propagation(unit, card) -> None:  # type: ignore[no-untyped-def]
    figs = {f.id: f for f in cost_figures(card)}
    assert figs["cost.total.likely_cny"].value == (card.total_likely_sgd * card.fx_cny_per_sgd).quantize(
        Decimal(1)
    )
    assert all(f.taint == Taint.TRUSTED for f in figs.values())
    quote = _quote("70000")
    qfigs = {f.id: f for f in cost_figures(estimate_costs(unit, quotes=[quote]))}
    assert qfigs["cost.fitout.likely"].taint == Taint.UNTRUSTED
    assert qfigs["cost.fitout.likely"].source.kind == "document"
    assert qfigs["cost.group.fitout.likely"].taint == Taint.UNTRUSTED
    assert qfigs["cost.total.likely_sgd"].taint == Taint.UNTRUSTED
    assert qfigs["cost.total.likely_cny"].taint == Taint.UNTRUSTED
    assert qfigs["cost.group.setup.likely"].taint == Taint.TRUSTED
    # and the FigureStore propagates it on its own, through the inputs chain
    store = FigureStore()
    for f in cost_figures(estimate_costs(unit, quotes=[quote])):
        store.add(f.model_copy(update={"taint": Taint.TRUSTED}) if f.id != "cost.fitout.likely" else f)
    assert store.get("cost.group.fitout.likely").taint == Taint.UNTRUSTED  # type: ignore[union-attr]


def test_due_totals_split_by_transfer(card) -> None:  # type: ignore[no-untyped-def]
    d = due_totals_sgd(card)
    assert sum(d.values()) == card.total_likely_sgd
    assert d["first"] > d["setup"] > 0


def test_owner_sees_only_what_the_quote_s_contractor_can_answer(unit) -> None:  # type: ignore[no-untyped-def]
    from agent.toolkit import missing

    assert missing(estimate_costs(unit), [], "en") == [], "no quote, no checklist (the cost card has it all)"
    quote = _quote("70000")
    q = estimate_costs(unit, quotes=[quote])
    shown = missing(q, [quote], "en")
    groups = {ln.key: ln.group for ln in q.lines}
    fitout_group = groups["fitout"]
    assert shown and shown[0].value == "fitout", "the quote's own exclusions come first"
    assert all(groups[o.value] == fitout_group for o in shown)
    assert len(shown) < len(q.missing)
