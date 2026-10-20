from __future__ import annotations

from decimal import Decimal

import pytest

from tools import params as P
from tools.data import load_units
from tools.figures import SourceKind
from tools.models import Area, CustomerGroup, MoneyRange, Priority, Profile, Unit
from tools.sites import (
    area_profile,
    band_range,
    break_even,
    break_even_cups,
    compare_units,
    list_units,
    rank_areas,
)


def _area(
    aid: str,
    young: float,
    traffic: int | None,
    rent: float | None,
    outlets: int | None = 100,
    daytime: float | None = 0.3,
) -> Area:
    return Area(
        id=aid,
        name=aid.title(),
        region="EAST",
        residents=200000,
        age_shares={"0-19": 0.2, "20-39": young, "40-64": 0.8 - young - 0.1, "65+": 0.1},
        income_shares={"below 5,000": 0.4, "5,000-9,999": 0.35, "10,000 & over": 0.25},
        daytime_proxy=daytime,
        station_traffic_monthly=traffic,
        food_outlets=outlets,
        rent_psf_month_sgd=None
        if rent is None
        else MoneyRange(low=Decimal(rent) - 2, high=Decimal(rent) + 2),
        sources={"residents": "singstat_census_2020"},
        simulated_fields=["food_outlets"],
    )


AREAS = [
    _area("TAMPINES", 0.30, 9_000_000, 20),
    _area("JURONG EAST", 0.26, 12_000_000, 22, outlets=300),
    _area("BEDOK", 0.22, 5_000_000, 18),
    _area("DOWNTOWN CORE", 0.35, 20_000_000, 40, daytime=0.95),
    _area("PUNGGOL", 0.33, None, 17),  # missing traffic
]
YOUNG = Profile(
    customers=[CustomerGroup.YOUNG_ADULTS], budget_sgd=MoneyRange(low=Decimal(280000), high=Decimal(340000))
)


def test_band_parsing() -> None:
    assert band_range("20-39") == (20, 39)
    assert band_range("65+") == (65, float("inf"))
    assert band_range("10,000 & over") == (10000, float("inf"))
    assert band_range("below 5,000") == (0, 4999)
    assert band_range("nonsense") is None


def test_scores_are_0_to_100_sorted_with_traceable_contributions() -> None:
    ranked = rank_areas(AREAS, YOUNG, Priority.NEAR_CUSTOMERS)
    assert [r.score for r in ranked] == sorted((r.score for r in ranked), reverse=True)
    for r in ranked:
        assert 0 <= r.score <= 100
        assert abs(sum(r.contributions.values()) - r.score) < 0.5
        assert len(r.reasons) <= 3


def test_null_factor_is_skipped_and_weights_renormalised() -> None:
    ranked = {r.area_id: r for r in rank_areas(AREAS, YOUNG, Priority.FOOT_TRAFFIC)}
    pg = ranked["PUNGGOL"]
    assert "traffic" not in pg.contributions
    assert pg.score > 0


def test_priority_changes_the_order() -> None:
    low = rank_areas(AREAS, YOUNG, Priority.LOW_RENT, top=1)[0].area_id
    traffic = rank_areas(AREAS, YOUNG, Priority.FOOT_TRAFFIC, top=1)[0].area_id
    assert low in ("PUNGGOL", "BEDOK")
    assert traffic == "DOWNTOWN CORE"


def test_ruled_out_areas_are_excluded_and_top_slices() -> None:
    ranked = rank_areas(AREAS, YOUNG, "near_customers", ruled_out=["downtown core"], top=3)
    assert len(ranked) == 3 and "DOWNTOWN CORE" not in {r.area_id for r in ranked}


def test_reason_codes() -> None:
    ranked = {r.area_id: r for r in rank_areas(AREAS, YOUNG, Priority.NEAR_CUSTOMERS)}
    assert "busy_stations" in ranked["DOWNTOWN CORE"].reasons
    assert "rent_in_budget" in ranked["PUNGGOL"].reasons
    assert "many_young_adults" in ranked["DOWNTOWN CORE"].reasons
    assert all(c != "many_food_outlets" for c in ranked["JURONG EAST"].reasons[:1])  # info, listed last


def test_competition_not_penalised_by_default() -> None:
    a = [_area("A", 0.3, 9_000_000, 20, outlets=10), _area("B", 0.3, 9_000_000, 20, outlets=900)]
    r = {x.area_id: x.score for x in rank_areas(a, YOUNG, Priority.NEAR_CUSTOMERS)}
    assert r["A"] == r["B"]


def test_area_profile_figures_carry_sources() -> None:
    prof = area_profile(AREAS[0], YOUNG)
    figs = {f.id: f for f in prof.figures}
    assert figs["area.TAMPINES.residents"].source.ref == "singstat_census_2020"
    assert figs["area.TAMPINES.food_outlets"].source.kind == SourceKind.SIMULATED
    share = figs["area.TAMPINES.customer_share"]
    assert share.unit == "pct" and share.value is not None and 0 <= share.value <= 1
    assert figs["area.TAMPINES.rent_typical"].value == Decimal(20 * P.inum("typical_unit_sqft"))
    missing = area_profile(_area("X", 0.3, None, None), YOUNG)
    assert {f.id: f for f in missing.figures}["area.X.station_traffic"].value is None


def test_units_are_simulated_and_plausible() -> None:
    units = load_units()
    assert 15 <= len(units) <= 25
    assert all(u.simulated for u in units)
    assert all(350 <= u.size_sqft <= 900 for u in units)
    assert len({u.area_id for u in units}) >= 6
    assert any(u.gto_pct for u in units)


def test_list_units_filters_and_sorts() -> None:
    us = list_units(["TAMPINES", "BEDOK"], (350, 600), None, Priority.NEAR_CUSTOMERS)
    assert us and all(u.area_id in ("TAMPINES", "BEDOK") for u in us)
    assert us[0].area_id == "TAMPINES"
    cheap = list_units(["TAMPINES", "BEDOK"], None, None, Priority.LOW_RENT)
    rents = [u.rent_monthly_sgd + u.service_charge_monthly_sgd for u in cheap]
    assert rents == sorted(rents)
    tight = list_units(["TAMPINES"], None, MoneyRange(low=Decimal(1), high=Decimal(300000)))
    assert all(u.id != "u-tm-01" for u in tight)


def _unit(gto: str | None, rent: int = 9600) -> Unit:
    return Unit(
        id="t",
        mall="M",
        unit_no="#1",
        area_id="TAMPINES",
        size_sqft=480,
        rent_monthly_sgd=Decimal(rent),
        service_charge_monthly_sgd=Decimal(960),
        gto_pct=None if gto is None else Decimal(gto),
    )


def test_break_even_formula_without_gto() -> None:
    u = _unit(None)
    cups = break_even_cups(u)
    margin = P.fnum("cup_price_sgd") - P.fnum("variable_cost_per_cup_sgd")
    days = P.fnum("opening_days_per_month")
    implied_fixed = cups * margin * days
    assert implied_fixed > 9600 + 960
    assert 100 < cups < 600


def test_break_even_gto_fixed_point() -> None:
    low_gto = break_even_cups(_unit("0.05"))
    assert low_gto == pytest.approx(break_even_cups(_unit(None)))  # base rent binds
    high = _unit("0.25", rent=2000)
    c = break_even_cups(high)
    price, days = P.fnum("cup_price_sgd"), P.fnum("opening_days_per_month")
    margin = price - P.fnum("variable_cost_per_cup_sgd")
    rent = max(2000.0, 0.25 * c * price * days)
    assert rent > 2000  # GTO binds at break-even
    fixed_wo_rent = c * margin * days - rent
    assert c == pytest.approx((fixed_wo_rent + rent) / (margin * days))
    assert c > break_even_cups(_unit(None, rent=2000))


def test_break_even_figure_and_compare_units() -> None:
    f = break_even(_unit(None))
    assert f.unit == "cups_per_day" and f.value is not None
    rows = compare_units(
        ["u-tm-01", "u-tm-02"],
        Profile(best_shop_cups_per_day=600, sources={"best_shop_cups_per_day": "feed"}),
    )
    assert [r.unit.id for r in rows] == ["u-tm-01", "u-tm-02"]
    for r in rows:
        assert r.rent_total.source.kind == SourceKind.SIMULATED
        assert r.early_cost.value is not None and r.early_cost.value > 200000
        assert r.best_shop is not None and r.best_shop.value == 600
        assert r.breakeven.inputs == (r.rent_total.id,)


def test_k_suffix_income_bands() -> None:
    assert band_range("4k-8k") == (4000, 8000)
    assert band_range("12k+") == (12000, float("inf"))
    assert band_range("<4k") == (0, 3999)


def test_tiny_areas_are_not_ranked_on_resident_shares() -> None:
    tiny = _area("MANDAI", 0.9, None, None, daytime=0.1).model_copy(update={"residents": 2000})
    cbd = _area("DOWNTOWN CORE", 0.35, None, None, daytime=1.0).model_copy(update={"residents": 6000})
    ids = {r.area_id for r in rank_areas([*AREAS[:3], tiny, cbd], YOUNG, Priority.NEAR_CUSTOMERS)}
    assert "MANDAI" not in ids and "DOWNTOWN CORE" in ids
    r = {x.area_id: x for x in rank_areas([*AREAS[:3], cbd], YOUNG, Priority.NEAR_CUSTOMERS)}
    assert "daytime_crowd" in r["DOWNTOWN CORE"].reasons


def test_constant_factor_gives_no_reason() -> None:
    same = [a.model_copy(update={"food_outlets": 0}) for a in AREAS]
    assert all("many_food_outlets" not in r.reasons for r in rank_areas(same, YOUNG, Priority.NEAR_CUSTOMERS))


def test_rent_falls_back_to_simulated_listings_when_public_rent_missing() -> None:
    a = _area("TAMPINES", 0.3, None, None)
    prof = {f.id: f for f in area_profile(a, YOUNG).figures}
    assert prof["area.TAMPINES.rent_psf"].source.kind == SourceKind.SIMULATED
    assert prof["area.TAMPINES.rent_typical"].value is not None
    nothing = _area("SELETAR", 0.3, None, None)
    assert {f.id: f for f in area_profile(nothing, YOUNG).figures}["area.SELETAR.rent_typical"].value is None


def test_real_public_areas_if_present() -> None:
    from tools.data import load_areas

    areas = load_areas()
    if not areas:
        pytest.skip("data/public/areas.json not built yet")
    ranked = rank_areas(areas, YOUNG, Priority.NEAR_CUSTOMERS)
    assert ranked and all(0 <= r.score <= 100 for r in ranked)
    assert not {"WESTERN WATER CATCHMENT", "CENTRAL WATER CATCHMENT", "MANDAI"} & {r.area_id for r in ranked}
