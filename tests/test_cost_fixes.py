"""Cost-analysis fixes from the 2026-10-20 judge panel: partial quotes, the likely total, quoted-line overrun,
and the break-even comparison (chain-average shop, GST as not registered)."""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from agent import toolkit as tk
from tools import params as P
from tools.costs import estimate_costs, missing_items, quote_uses, simulated_totals
from tools.data import unit_by_id
from tools.figtools import sourced
from tools.figures import Source, SourceKind
from tools.funding import funding_gap
from tools.models import ExtractedLine, ExtractedQuote, Profile
from tools.plan import _lines
from tools.sites import break_even_cups, compare_units


@pytest.fixture(scope="module")
def unit():  # type: ignore[no-untyped-def]
    return unit_by_id("u-tm-01")


@pytest.fixture(scope="module")
def card(unit):  # type: ignore[no-untyped-def]
    return estimate_costs(unit)


def _doc(doc_id: str, *lines: tuple[str, str]) -> ExtractedQuote:
    """A read quote, matched by code, every line accepted."""
    q = ExtractedQuote(
        doc_id=doc_id,
        lines=[
            ExtractedLine(id=f"{doc_id}-{i}", label=lab, amount=Decimal(amt), confidence=0.9)
            for i, (lab, amt) in enumerate(lines)
        ],
    )
    q = tk.match_quote(q)
    return q.model_copy(update={"lines": [ln.model_copy(update={"status": "accepted"}) for ln in q.lines]})


def _line(card, key):  # type: ignore[no-untyped-def]
    return next(ln for ln in card.lines if ln.key == key)


# ------------------------------------------------------------------ 1. partial quotes


def test_matching_takes_the_longest_keyword_and_never_defaults() -> None:
    assert tk.match_line("Renovation works") == ("fitout", False)
    assert tk.match_line("Demolition") == ("fitout", True)
    assert tk.match_line("吧台及柜体 Counter + cabinets") == ("fitout", True)
    assert tk.match_line("冰柜 chiller") == ("equipment_pos", True)
    assert tk.match_line("Tea bar equipment") == ("equipment_pos", False)
    assert tk.match_line("Lucky cat figurine") == (None, False)  # unmatched: the owner assigns it


def test_one_line_demolition_quote_does_not_replace_the_fitout_estimate(unit, card) -> None:  # type: ignore[no-untyped-def]
    q = _doc("demo-1", ("Demolition", "3000"))
    after = estimate_costs(unit, quotes=[q])
    fit0, fit1 = _line(card, "fitout"), _line(after, "fitout")
    assert not fit1.from_quote and fit1.flags == ["partial"] and fit1.quote_sgd == Decimal("3000")
    assert fit1.likely_sgd == fit0.likely_sgd  # the estimate stays (the part is far below it)
    assert after.total_likely_sgd == card.total_likely_sgd
    assert "fitout" in after.missing  # still on the missing list
    kinds = {(m.key, m.kind) for m in missing_items(after, [q])}
    assert ("fitout", "partial") in kinds


def test_quoted_parts_set_a_floor_under_the_estimate(unit, card) -> None:  # type: ignore[no-untyped-def]
    big = str(int(_line(card, "fitout").high_sgd or 0) * 2)
    after = estimate_costs(unit, quotes=[_doc("parts", ("Carpentry", big))])
    assert _line(after, "fitout").likely_sgd >= Decimal(big)
    assert not _line(after, "fitout").from_quote


def test_unmatched_lines_stay_out_until_the_owner_assigns_them(unit, card) -> None:  # type: ignore[no-untyped-def]
    q = _doc("misc", ("Lucky cat figurine", "50000"))
    assert q.lines[0].matched_key is None
    assert estimate_costs(unit, quotes=[q]).total_likely_sgd == card.total_likely_sgd
    quotes = [q]
    assert tk.assign_line(quotes, "misc-0", "fitout")
    assert quotes[0].lines[0].matched_key == "fitout" and quotes[0].lines[0].part
    assert not tk.assign_line(quotes, "misc-0", "not_a_line")
    assert tk.set_coverage(quotes, "misc", "fitout", whole=True)
    after = estimate_costs(unit, quotes=quotes)
    assert _line(after, "fitout").from_quote and _line(after, "fitout").quote_sgd == Decimal("50000")


def test_owner_can_say_a_parts_quote_covers_the_whole_line(unit) -> None:  # type: ignore[no-untyped-def]
    quotes = [_doc("q", ("Partition + ceiling", "18000"), ("Flooring", "9500"), ("Signage", "3800"))]
    assert quote_uses(quotes)["fitout"].cover == "part"
    assert tk.set_coverage(quotes, "q", "fitout", whole=True)
    use = quote_uses(quotes)["fitout"]
    assert use.cover == "whole" and use.amount == 31300.0
    figs, payload = tk.upload_payload(quotes[0], None, "replay", "en")
    assert [(c.key, c.whole) for c in payload.coverage] == [("fitout", True)]
    assert any(o.value == "fitout" for o in payload.assignable)


def test_quote_below_the_estimates_low_end_is_flagged(unit, card) -> None:  # type: ignore[no-untyped-def]
    after = estimate_costs(unit, quotes=[_doc("cheap", ("Renovation", "3000"))])
    fit = _line(after, "fitout")
    assert fit.from_quote and "below_estimate" in fit.flags
    assert Decimal("3000") < (_line(card, "fitout").low_sgd or 0)
    shown = tk.missing(after, [], "en")
    assert shown[0].value == "fitout" and "low end" in (shown[0].detail or "")
    ok = estimate_costs(unit, quotes=[_doc("fair", ("Renovation", str(_line(card, "fitout").mode_sgd)))])
    assert _line(ok, "fitout").flags == []


def test_two_quotes_that_disagree_show_a_conflict_whatever_their_order(unit) -> None:  # type: ignore[no-untyped-def]
    a, b = _doc("a", ("Renovation", "70000")), _doc("b", ("Renovation", "90000"))
    ab, ba = estimate_costs(unit, quotes=[a, b]), estimate_costs(unit, quotes=[b, a])
    for c in (ab, ba):
        fit = _line(c, "fitout")
        assert "conflict" in fit.flags and fit.quote_sgd == Decimal("90000") and fit.source == "quote:b"
    assert ab.total_likely_sgd == ba.total_likely_sgd
    assert ("fitout", "conflict") in {(m.key, m.kind) for m in missing_items(ab, [a, b])}
    same = estimate_costs(unit, quotes=[a, _doc("c", ("Renovation", "70000"))])
    assert "conflict" not in _line(same, "fitout").flags


def test_owner_figure_settles_a_flagged_line(unit) -> None:  # type: ignore[no-untyped-def]
    a, b = _doc("a", ("Renovation", "70000")), _doc("b", ("Renovation", "90000"))
    c = tk.estimate(unit, Profile(), "standard", "hire_local", [a, b], {"fitout": Decimal("80000")})
    assert _line(c, "fitout").flags == [] and _line(c, "fitout").likely_sgd == Decimal("80000")
    assert all(o.value != "fitout" or "differ" not in (o.detail or "") for o in tk.missing(c, [a, b], "en"))


# ------------------------------------------------------------------ 2. the likely total


def test_likely_total_is_the_simulated_median_not_the_sum_of_modes(unit, card) -> None:  # type: ignore[no-untyped-def]
    totals = simulated_totals(unit, seed=card.seed)
    median = float(np.median(totals))
    likely, base = float(card.total_likely_sgd), float(card.total_base_sgd or 0)
    assert abs(likely - median) / median < 0.005  # the lines add up to the median, to rounding
    assert 0.45 < float(np.mean(totals > likely)) < 0.55
    assert base < likely and float(np.mean(totals > base)) > 0.6  # the mode sum is biased low
    assert card.total_likely_sgd == sum((ln.likely_sgd for ln in card.lines), Decimal(0))


def test_funding_gap_and_plan_gap_use_the_likely_total(unit, card) -> None:  # type: ignore[no-untyped-def]
    spare = sourced("spare", "Spare", "CNY", Decimal("500000"), Source(kind=SourceKind.FEED, ref="x"))
    gap = funding_gap(card, spare)
    assert gap.value == (card.total_likely_sgd * card.fx_cny_per_sgd - Decimal("500000")).quantize(Decimal(1))


def test_quick_cost_matches_the_card_median(unit, card) -> None:  # type: ignore[no-untyped-def]
    from tools.costs import quick_cost_likely

    assert quick_cost_likely(unit) == card.total_likely_sgd


# ------------------------------------------------------------------ 3. quoted lines can overrun


def test_accepted_quote_keeps_a_variation_allowance(unit) -> None:  # type: ignore[no-untyped-def]
    c = estimate_costs(unit, quotes=[_doc("q", ("Renovation", "70000"))])
    fit = _line(c, "fitout")
    assert fit.bad_sgd > fit.likely_sgd >= Decimal("70000")
    spec = _lines(c)[[ln.key for ln in c.lines].index("fitout")]
    a = P.tri("quote_variation_allowance")
    assert spec.low == 70000 and spec.high == pytest.approx(70000 * (1 + a.high)) and spec.high > spec.low
    with P.overrides({"quote_variation_allowance": {"low": 0.0, "likely": 0.0, "high": 0.0}}):
        flat = _line(estimate_costs(unit, quotes=[_doc("q", ("Renovation", "70000"))]), "fitout")
    assert flat.likely_sgd == flat.bad_sgd == Decimal("70000")


# ------------------------------------------------------------------ 4. break-even


def test_break_even_counts_gst_as_a_cost_when_not_registered(unit) -> None:  # type: ignore[no-untyped-def]
    with_gst = break_even_cups(unit)
    with P.overrides({"gst_rate": 0.0}):
        without = break_even_cups(unit)
    assert with_gst > without
    gst = 1 + P.fnum("gst_rate")
    import numpy as np

    from tools.costs import monthly_wages

    price = P.fnum("cup_price_sgd")
    # per cup: ingredients and the delivery commission (on delivered cups) both carry GST the shop can't claim
    margin = price - (P.fnum("variable_cost_per_cup_sgd") + price * P.fnum("delivery_share")
                      * P.fnum("delivery_commission")) * gst
    days = P.fnum("opening_days_per_month")
    wages = float(monthly_wages("hire_local", lambda t: np.array([t.likely]), 1, None)[0])
    supplies = float(unit.service_charge_monthly_sgd) + P.tri("utilities_monthly_sgd").likely + P.fnum(
        "other_fixed_monthly_sgd"
    )
    if not unit.gto_pct:
        expect = (wages + (supplies + float(unit.rent_monthly_sgd)) * gst) / (margin * days)
        assert with_gst == pytest.approx(expect)


def test_unit_card_compares_with_the_chain_average_shop() -> None:
    p = Profile(best_shop_cups_per_day=600, avg_shop_cups_per_day=420)
    p.sources = {"best_shop_cups_per_day": "feed", "avg_shop_cups_per_day": "feed"}
    row = compare_units(["u-tm-01"], p)[0]
    assert row.best_shop is not None and row.best_shop.value == 600
    assert row.avg_shop is not None and row.avg_shop.value == 420 and row.avg_shop.source.kind == "feed"
    _, ui = tk.unit_row(unit_by_id("u-tm-01"), p, "en")
    assert ui.avg_shop_cups == "profile.avg_shop_cups" and ui.best_shop_cups == "profile.best_shop_cups"


def test_feed_carries_the_chain_average() -> None:
    from sim.chen import generate_chen

    fs = generate_chen()
    assert fs.avg_shop_cups_per_day is not None
    assert fs.avg_shop_cups_per_day < (fs.best_shop_cups_per_day or 0)
    assert tk.profile_from_feed(fs).avg_shop_cups_per_day == fs.avg_shop_cups_per_day


def test_reserve_running_costs_carry_gst(unit, card) -> None:  # type: ignore[no-untyped-def]
    gst = _line(card, "gst_services").mode_sgd or Decimal(0)
    services = sum(
        (_line(card, k).mode_sgd or Decimal(0))
        for k in ("incorporation", "corp_secretary", "resident_director", "insurance", "recruitment")
    )
    rent = P.num("reserve_months") * (unit.rent_monthly_sgd + unit.service_charge_monthly_sgd)
    supplies = P.num("reserve_months") * (
        Decimal(str(P.tri("utilities_monthly_sgd").likely)) + P.num("other_fixed_monthly_sgd")
    )
    assert abs(gst - (services + rent + supplies) * P.num("gst_rate")) <= 2
