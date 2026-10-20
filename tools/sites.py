"""Site tools (SPEC §6.2): rank planning areas, area profile, list units, break-even cups a day, compare.

Scores are 0-100: a weighted sum of factors normalised across the candidate areas (min-max). A factor
missing for an area is skipped and the remaining weights renormalised (missing != zero). Competition is
shown as information and weighted 0 unless the owner asks.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from decimal import Decimal
from typing import cast

from pydantic import BaseModel

from tools import params as P
from tools.costs import Level, ManagerPlan, crew_wage_base, quick_cost_likely
from tools.data import areas_by_id, load_units
from tools.figtools import derived, sourced
from tools.figures import Figure, Source, SourceKind, q0
from tools.models import Area, AreaScore, CustomerGroup, MoneyRange, Priority, Profile, Unit

FACTORS = ("customer_fit", "traffic", "affordability", "competition")


class AreaProfile(BaseModel):
    area_id: str
    name: str
    figures: list[Figure]
    age_bands: dict[str, float]


class UnitRowData(BaseModel):
    unit: Unit
    area_name: str
    rent_total: Figure
    breakeven: Figure
    early_cost: Figure
    best_shop: Figure | None = None
    avg_shop: Figure | None = None


# ------------------------------------------------------------------ band parsing


_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([kK]?)")


def band_range(band: str) -> tuple[float, float] | None:
    """'20-39' -> (20, 39); '65+' / '65 & over' -> (65, inf); 'below 1000' / '<1000' -> (0, 999);
    '4k-8k' -> (4000, 8000)."""
    nums = [float(n.replace(",", "")) * (1000 if k else 1) for n, k in _NUM.findall(band)]
    low = band.lower()
    if not nums:
        return None
    if len(nums) >= 2:
        return nums[0], nums[1]
    if "+" in band or "over" in low or "above" in low or "more" in low:
        return nums[0], math.inf
    if "<" in band or "below" in low or "under" in low or "less" in low:
        return 0.0, nums[0] - 1
    return nums[0], nums[0]


def _share_in(shares: dict[str, float], lo: float, hi: float) -> float | None:
    """Share of residents in [lo, hi], prorating bands that overlap partially."""
    total = 0.0
    seen = False
    for band, share in shares.items():
        r = band_range(band)
        if r is None:
            continue
        seen = True
        a, b = r
        if math.isinf(b):
            total += share if a >= lo and a <= hi else 0.0
            continue
        width = b - a + 1
        overlap = max(0.0, min(b, hi) - max(a, lo) + 1)
        total += share * overlap / width
    return total if seen else None


def _income_high(shares: dict[str, float]) -> float | None:
    thr = P.fnum("high_income_threshold_sgd")
    total = 0.0
    seen = False
    for band, share in shares.items():
        r = band_range(band)
        if r is None:
            continue
        seen = True
        if r[0] >= thr:
            total += share
    return total if seen else None


# ------------------------------------------------------------------ raw factors


def _groups(profile: Profile | None) -> list[str]:
    if profile is None or not profile.customers:
        return [CustomerGroup.YOUNG_ADULTS.value]
    return [g.value for g in profile.customers]


def customer_fit_raw(area: Area, profile: Profile | None) -> float | None:
    prof = P.table("customer_group_profiles")
    vals: list[float] = []
    for g in _groups(profile):
        cfg = prof[g]
        parts: list[tuple[float, float]] = []
        w_day, w_inc = float(cfg["daytime"]), float(cfg["income"])
        enough = (area.residents or 0) >= P.inum("min_residents_for_area")
        age = (
            _share_in(area.age_shares, float(cfg["age_low"]), float(cfg["age_high"]))
            if area.age_shares and enough
            else None
        )
        if age is not None:
            parts.append((1.0 - w_day - w_inc, age))
        if w_day > 0 and area.daytime_proxy is not None:
            parts.append((w_day, area.daytime_proxy))
        inc = _income_high(area.income_shares) if area.income_shares and enough else None
        if w_inc > 0 and inc is not None:
            parts.append((w_inc, inc))
        wsum = sum(w for w, _ in parts)
        if wsum > 0:
            vals.append(sum(w * v for w, v in parts) / wsum)
    return sum(vals) / len(vals) if vals else None


def _rent_line(profile: Profile | None) -> Decimal | None:
    if profile is None or profile.budget_sgd is None:
        return None
    return profile.budget_sgd.mid * P.num("rent_line_share_of_budget")


def area_rent_psf(area: Area) -> tuple[MoneyRange | None, Source | None]:
    """Typical rent per sq ft a month: public data if present, else the range of the (simulated) unit
    listings in the area, labelled simulated. None if neither exists (missing != zero)."""
    if area.rent_psf_month_sgd is not None:
        return area.rent_psf_month_sgd, _area_source(area, "rent_psf_month_sgd")
    psf = [
        (u.rent_monthly_sgd + u.service_charge_monthly_sgd) / u.size_sqft
        for u in load_units()
        if u.area_id.upper() == area.id.upper()
    ]
    if not psf:
        return None, None
    rng = MoneyRange(low=min(psf).quantize(Decimal("0.01")), high=max(psf).quantize(Decimal("0.01")))
    note = "range of simulated listings in this area (no public rent per area)"
    return rng, Source(kind=SourceKind.SIMULATED, ref="data/demo/units.yaml", note=note)


def typical_rent(area: Area, size_sqft: int) -> Decimal | None:
    rr, _ = area_rent_psf(area)
    return None if rr is None else q0(rr.mid * size_sqft)


def eligible(area: Area) -> bool:
    """Skip areas with almost no residents unless they have a big daytime population."""
    if (area.residents or 0) >= P.inum("min_residents_for_area"):
        return True
    return (area.daytime_proxy or 0.0) >= P.fnum("min_daytime_for_area")


def _raw(area: Area, profile: Profile | None, size: int) -> dict[str, float | None]:
    rent = typical_rent(area, size)
    traffic = None if area.station_traffic_monthly is None else math.log1p(area.station_traffic_monthly)
    return {
        "customer_fit": customer_fit_raw(area, profile),
        "traffic": traffic,
        "affordability": None if rent is None else -float(rent),
        "competition": None if area.food_outlets is None else float(area.food_outlets),
    }


def _normalise(values: dict[str, float | None]) -> dict[str, float | None]:
    present = [v for v in values.values() if v is not None]
    if not present:
        return {k: None for k in values}
    lo, hi = min(present), max(present)
    return {k: None if v is None else (0.5 if hi == lo else (v - lo) / (hi - lo)) for k, v in values.items()}


# ------------------------------------------------------------------ ranking


def _reasons(
    area: Area, norm: dict[str, float | None], contrib: dict[str, float], profile: Profile | None, size: int
) -> list[str]:
    thr = P.fnum("reason_threshold")
    cands: list[tuple[float, str]] = []
    if (norm["customer_fit"] or 0) >= thr:
        enough = (area.residents or 0) >= P.inum("min_residents_for_area")
        code = f"many_{_groups(profile)[0]}" if enough else "daytime_crowd"
        cands.append((contrib.get("customer_fit", 0), code))
        inc = _income_high(area.income_shares) if area.income_shares and enough else None
        if inc is not None and inc >= 0.3:
            cands.append((contrib.get("customer_fit", 0) * 0.5, "high_income"))
    if (norm["traffic"] or 0) >= thr:
        cands.append((contrib.get("traffic", 0), "busy_stations"))
    line = _rent_line(profile)
    rent = typical_rent(area, size)
    if line is not None and rent is not None and rent <= line:
        cands.append((contrib.get("affordability", 0) + 0.01, "rent_in_budget"))
    elif (norm["affordability"] or 0) >= thr:
        cands.append((contrib.get("affordability", 0), "low_rent"))
    if (norm["competition"] or 0) >= thr:
        cands.append((-1.0, "many_food_outlets"))  # information; listed last
    cands.sort(key=lambda c: -c[0])
    return [c for _, c in cands][: P.inum("reason_max")]


def rank_areas(
    areas: Sequence[Area],
    profile: Profile | None,
    priority: Priority | str,
    ruled_out: Sequence[str] = (),
    *,
    size_sqft: int | None = None,
    top: int | None = None,
) -> list[AreaScore]:
    """Score every area not ruled out (0-100), best first; `top` slices the list (SPEC: top 3 on the map)."""
    pri = Priority(priority).value
    weights = {k: float(v) for k, v in P.table("area_weights")[pri].items()}
    size = size_sqft or P.inum("typical_unit_sqft")
    excluded = {a.upper() for a in ruled_out}
    cand = [a for a in areas if a.id.upper() not in excluded and eligible(a)]
    raw = {a.id: _raw(a, profile, size) for a in cand}
    norm_by_factor = {f: _normalise({a: raw[a][f] for a in raw}) for f in FACTORS}
    out: list[AreaScore] = []
    for a in cand:
        norm = {f: norm_by_factor[f][a.id] for f in FACTORS}
        avail = {f: weights.get(f, 0.0) for f in FACTORS if norm[f] is not None and weights.get(f, 0.0) > 0}
        wsum = sum(avail.values())
        contrib = {f: 100.0 * w / wsum * (norm[f] or 0.0) for f, w in avail.items()} if wsum > 0 else {}
        if norm["competition"] is not None and "competition" not in contrib:
            contrib["competition"] = 0.0
        score = round(sum(contrib.values()), 1)
        out.append(
            AreaScore(
                area_id=a.id,
                score=score,
                contributions={k: round(v, 1) for k, v in contrib.items()},
                reasons=_reasons(a, norm, contrib, profile, size),
            )
        )
    out.sort(key=lambda s: (-s.score, s.area_id))
    return out[:top] if top else out


def _area_source(area: Area, fld: str) -> Source:
    kind = SourceKind.SIMULATED if fld in area.simulated_fields else SourceKind.PUBLIC_DATA
    return Source(kind=kind, ref=area.sources.get(fld, "data/public/areas.json"))


def area_profile(area: Area, profile: Profile | None = None, size_sqft: int | None = None) -> AreaProfile:
    """The figures behind `area_card`, each with its dataset and date (missing stays missing)."""
    size = size_sqft or P.inum("typical_unit_sqft")
    pid = f"area.{area.id}"
    figs: list[Figure] = [
        sourced(f"{pid}.residents", "Residents", "people", area.residents, _area_source(area, "residents")),
        sourced(
            f"{pid}.station_traffic",
            "Station traffic a month (not mall footfall)",
            "count",
            area.station_traffic_monthly,
            _area_source(area, "station_traffic_monthly"),
        ),
        sourced(
            f"{pid}.food_outlets",
            "Licensed food outlets",
            "count",
            area.food_outlets,
            _area_source(area, "food_outlets"),
        ),
    ]
    fit = customer_fit_raw(area, profile)
    figs.append(
        derived(
            f"{pid}.customer_share",
            "Share in your customer group",
            "pct",
            None if fit is None else round(fit, 4),
            tool="area_profile",
            assumptions=("customer_group_profiles",),
        )
    )
    rr, found_src = area_rent_psf(area)
    rent_src = found_src or _area_source(area, "rent_psf_month_sgd")
    psf = Figure(
        id=f"{pid}.rent_psf",
        label="Typical rent per sq ft a month",
        unit="SGD",
        value=None if rr is None else rr.mid,
        low=None if rr is None else rr.low,
        high=None if rr is None else rr.high,
        source=rent_src,
    )
    figs.append(psf)
    rent = typical_rent(area, size)
    figs.append(
        derived(
            f"{pid}.rent_typical",
            f"Typical monthly rent for {size} sq ft",
            "SGD",
            rent,
            tool="area_profile",
            inputs=[psf],
            assumptions=("typical_unit_sqft",),
            low=None if rr is None else q0(rr.low * size),
            high=None if rr is None else q0(rr.high * size),
        )
    )
    return AreaProfile(area_id=area.id, name=area.name, figures=figs, age_bands=dict(area.age_shares))


# ------------------------------------------------------------------ units


def list_units(
    area_ids: Sequence[str],
    size_range: tuple[int, int] | None = None,
    budget: MoneyRange | None = None,
    priority: Priority | str = Priority.NEAR_CUSTOMERS,
    *,
    units: Sequence[Unit] | None = None,
    fitout_level: str = "standard",
) -> list[Unit]:
    """Units in the chosen areas, within the size range and (if given) whose early likely cost fits the
    budget's upper end; sorted by the priority (low rent: cheapest first; otherwise area order, then rent)."""
    pool = load_units() if units is None else units
    order = {a.upper(): i for i, a in enumerate(area_ids)}
    out = []
    for u in pool:
        if u.area_id.upper() not in order:
            continue
        if size_range is not None and not size_range[0] <= u.size_sqft <= size_range[1]:
            continue
        if budget is not None and quick_cost_likely(u, _level(fitout_level)) > budget.high:
            continue
        out.append(u)
    if Priority(priority) == Priority.LOW_RENT:
        out.sort(key=lambda u: (_rent(u), u.id))
    else:
        out.sort(key=lambda u: (order[u.area_id.upper()], _rent(u), u.id))
    return out


def _rent(u: Unit) -> Decimal:
    return u.rent_monthly_sgd + u.service_charge_monthly_sgd


def _level(level: str) -> Level:
    if level not in ("basic", "standard", "premium"):
        raise ValueError(f"unknown fit-out level {level!r}")
    return cast(Level, level)


def break_even_cups(unit: Unit, manager_plan: ManagerPlan = "hire_local") -> float:
    """Cups a day to cover rent (+ GTO), service charge, staff and other fixed costs, at the same contribution
    per cup as the unit-economics card (tools/unit_econ.py): not GST-registered, so the whole price is revenue
    and GST on rent, supplies, per-cup ingredients and delivery commissions is a cost."""
    from tools.unit_econ import break_even_cups as be

    return be(unit, manager_plan)


def break_even(
    unit: Unit, profile: Profile | None = None, manager_plan: ManagerPlan = "hire_local"
) -> Figure:
    return derived(
        f"unit.{unit.id}.breakeven",
        "Break-even cups a day",
        "cups_per_day",
        round(break_even_cups(unit, manager_plan)),
        tool="break_even",
        assumptions=(
            "cup_price_sgd",
            "variable_cost_per_cup_sgd",
            "delivery_share",
            "delivery_commission",
            "gst_rate",
            "opening_days_per_month",
            "staff_plan",
            "local_manager_wage_sgd",
            "pwm_counter_attendant_wage_sgd",
            "cpf_employer_rate",
            "utilities_monthly_sgd",
            "other_fixed_monthly_sgd",
        ),
        note=f"PWM wage {crew_wage_base(None):.0f} a month (latest scheduled)",
    )


def _unit_source(u: Unit) -> Source:
    return Source(
        kind=SourceKind.SIMULATED if u.simulated else SourceKind.PUBLIC_DATA,
        ref=f"units:{u.id}",
        note="simulated listing" if u.simulated else None,
    )


def compare_units(
    unit_ids: Sequence[str],
    profile: Profile | None = None,
    *,
    units: Sequence[Unit] | None = None,
    fitout_level: str = "standard",
    manager_plan: ManagerPlan = "hire_local",
) -> list[UnitRowData]:
    """The `unit_compare` rows: rent + service charge, break-even cups vs his best and his chain-average shop,
    early likely cost."""
    pool = {u.id: u for u in (load_units() if units is None else units)}
    names = {k: a.name for k, a in areas_by_id().items()}
    rows: list[UnitRowData] = []
    best = None
    if profile is not None and profile.best_shop_cups_per_day is not None:
        best = sourced(
            "profile.best_shop_cups",
            "Your best shop",
            "cups_per_day",
            profile.best_shop_cups_per_day,
            Source(
                kind=SourceKind.FEED
                if profile.sources.get("best_shop_cups_per_day") == "feed"
                else SourceKind.OWNER,
                ref="best_shop_cups_per_day",
            ),
        )
    avg = None
    if profile is not None and profile.avg_shop_cups_per_day is not None:
        avg = sourced(
            "profile.avg_shop_cups",
            "Your average shop",
            "cups_per_day",
            profile.avg_shop_cups_per_day,
            Source(
                kind=SourceKind.FEED
                if profile.sources.get("avg_shop_cups_per_day") == "feed"
                else SourceKind.OWNER,
                ref="avg_shop_cups_per_day",
            ),
        )
    for uid in unit_ids:
        u = pool[uid]
        src = _unit_source(u)
        rent = sourced(
            f"unit.{u.id}.rent_total",
            "Rent + service charge a month",
            "SGD",
            u.rent_monthly_sgd + u.service_charge_monthly_sgd,
            src,
        )
        be = break_even(u, profile, manager_plan).model_copy(update={"inputs": (rent.id,)})
        cost = derived(
            f"unit.{u.id}.early_cost",
            "Early cost estimate (likely)",
            "SGD",
            quick_cost_likely(u, _level(fitout_level), manager_plan),
            tool="estimate_costs",
            inputs=[rent],
            assumptions=("fitout_psf_sgd", "reserve_months", "deposit_months", "likely_quantile"),
        )
        rows.append(
            UnitRowData(
                unit=u,
                area_name=names.get(u.area_id, u.area_id.title()),
                rent_total=rent,
                breakeven=be,
                early_cost=cost,
                best_shop=best,
                avg_shop=avg,
            )
        )
    return rows
