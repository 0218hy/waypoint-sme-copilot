"""TulBrew [fictional], Joon Rui's 30 tea shops in Shenzhen, as the mock WeBank feed shows them (SPEC §10).

Seeded and deterministic: the same seed and `as_of` always give the same snapshot, and a later `as_of`
extends the same history. Every number here is a persona fact for the demo, labelled simulated.

Shape of the business:
- about RMB 13m sales a year and about RMB 210k operating profit a month on average, seasonal:
  a trough in Jan-Feb (year-end bonuses paid before Chinese New Year, then the holiday closure),
  a dip in June (the summer stock build, partly paid from cash), and a strong autumn and December;
- the 微业贷 line (limit RMB 2.0m) is normally drawn RMB 0.10-0.55m, highest in the summer build
  (Jun-Aug); its normal balance by calendar month is part of the feed (R2 compares against it);
- owner drawings about RMB 78k a month, home commitments (shop refits, tax) about RMB 30k a month;
- payroll sized so the floor makes sense; cash such that spare cash (above floor + 4-week buffer) is
  about RMB 500k at the base date; the cups a day of the average and the best shop are derived from the
  sales (`home_cup_price_cny`, `best_shop_vs_average`; results/prereg.md addendum 2026-10-20 (14)), about
  100 and 180.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from sim.shocks import AboveNormalDraw, ChannelShift, MissingFeed, ProfitShock, SalesDrop, Shock
from tools import params as P
from tools.figures import q0
from tools.models import FeedSnapshot, ProfitMonth, WeekProfit

BASE_AS_OF = date(2026, 10, 19)
# Chosen by the rule in results/prereg.md addendum 2026-10-20 (6) (sim/demo_seed.py; every seed tried is in
# results/demo/seed_search.json), re-run with the detector of addendum (7). It was 1414 (its no-shock run
# alerted by itself in the demo's window), then 1423 (chosen with the old detector).
DEFAULT_SEED = 1422


@dataclass(frozen=True)
class Persona:
    company_name: str = "深圳图鲁茶饮连锁有限公司 TulBrew (fictional)"
    shops: int = 30
    business_type: str = "tea"
    annual_sales_cny: float = 13_000_000
    profit_monthly_cny: float = 210_000
    # operating profit by calendar month (Jan..Dec), mean 1.0
    profit_season: tuple[float, ...] = (
        0.55,
        0.45,
        0.90,
        1.00,
        1.05,
        0.85,
        1.10,
        1.20,
        1.15,
        1.20,
        1.20,
        1.35,
    )
    sales_season: tuple[float, ...] = (0.95, 0.70, 0.90, 0.95, 1.00, 1.10, 1.20, 1.20, 1.05, 1.00, 0.95, 1.00)
    profit_cv: float = 0.15  # stationary sd of the monthly profit level
    profit_phi: float = 0.6
    weekly_sd: float = 0.08
    contribution_margin: float = 0.62  # profit lost per yuan of sales lost (ingredients and packaging vary)
    payroll_monthly_cny: Decimal = Decimal("280000")
    loan_repayment_monthly_cny: Decimal = Decimal("45000")
    loan_limit_cny: Decimal = Decimal("2000000")
    normal_loan_by_month: tuple[int, ...] = (
        200_000,
        250_000,
        150_000,
        100_000,
        250_000,
        450_000,
        550_000,
        500_000,
        350_000,
        200_000,
        120_000,
        150_000,
    )
    drawings_monthly_cny: Decimal = Decimal("78000")
    commitments_monthly_cny: Decimal = Decimal("30000")
    spare_target_cny: Decimal = Decimal("500000")
    history_months: int = 24
    weekly_weeks: int = 26

    @property
    def avg_shop_cups_per_day(self) -> int:
        """The chain-average shop's cups a day, derived from the sales so the feed's cups and sales agree."""
        return round(self.annual_sales_cny / self.shops / 365 / P.fnum("home_cup_price_cny"))

    @property
    def best_shop_cups_per_day(self) -> int:
        return round(self.avg_shop_cups_per_day * P.fnum("best_shop_vs_average"))


CHEN = Persona()


@dataclass(frozen=True)
class GoalTransfers:
    """What the feed sees once a goal is active: spare cash moved to the pot, then the monthly set-aside,
    run as the bank runs the signed instruction: the fixed amount in the first week of each month, skipped
    that month while R2 holds (borrowing above normal) or if it would leave cash below floor + buffer."""

    start: date
    spare_moved_cny: Decimal
    monthly_cny: Decimal


@dataclass(frozen=True)
class Scenario:
    seed: int = DEFAULT_SEED
    shocks: tuple[Shock, ...] = ()
    goal: GoalTransfers | None = None
    persona: Persona = field(default_factory=Persona)


# ------------------------------------------------------------------ deterministic draws


def _ordinal(d: date) -> int:
    return d.year * 12 + d.month - 1


_FIRST = 2020 * 12  # month ordinals covered by the level path
_LAST = 2035 * 12


def _levels(seed: int, persona: Persona) -> np.ndarray:
    rng = np.random.default_rng([seed, 1])
    n = _LAST - _FIRST
    sd_i = persona.profit_cv * float(np.sqrt(1 - persona.profit_phi**2))
    eps = rng.standard_normal(n) * sd_i
    lev = np.zeros(n)
    lev[0] = rng.standard_normal() * persona.profit_cv
    for k in range(1, n):
        lev[k] = persona.profit_phi * lev[k - 1] + eps[k]
    return lev


def _level(seed: int, persona: Persona, d: date) -> float:
    return float(_levels_cached(seed, persona)[_ordinal(d) - _FIRST])


_LEVEL_CACHE: dict[tuple[int, Persona], np.ndarray] = {}


def _levels_cached(seed: int, persona: Persona) -> np.ndarray:
    key = (seed, persona)
    if key not in _LEVEL_CACHE:
        _LEVEL_CACHE[key] = _levels(seed, persona)
    return _LEVEL_CACHE[key]


def _week_noise(seed: int, week_start: date) -> float:
    return float(np.random.default_rng([seed, 2, week_start.toordinal()]).standard_normal())


# ------------------------------------------------------------------ one week / one month


@dataclass(frozen=True)
class WeekValues:
    revenue: float
    instore: float
    delivery: float
    profit: float
    missing: bool


def _base_month(persona: Persona, seed: int, d: date) -> tuple[float, float]:
    m = d.month - 1
    lev = _level(seed, persona, d)
    revenue = persona.annual_sales_cny / 12 * persona.sales_season[m] * (1 + 0.3 * lev)
    profit = persona.profit_monthly_cny * persona.profit_season[m] * (1 + lev)
    return revenue, profit


def week_values(sc: Scenario, week_start: date) -> WeekValues:
    persona = sc.persona
    wpm = P.weeks_per_month()
    rev_m, prof_m = _base_month(persona, sc.seed, week_start)
    k = 1 + persona.weekly_sd * _week_noise(sc.seed, week_start)
    revenue = rev_m / wpm * k
    profit = prof_m / wpm * k
    delivery_share = 0.10  # Chen's normal delivery share
    missing = False
    for s in sc.shocks:
        if isinstance(s, SalesDrop) and week_start >= s.start:
            lost = revenue * s.pct * s.shops / persona.shops
            revenue -= lost
            profit -= lost * persona.contribution_margin
        elif isinstance(s, ProfitShock) and week_start >= s.start:
            profit -= abs(profit) * s.pct
        elif isinstance(s, ChannelShift) and week_start >= s.start:
            moved = revenue * s.share
            delivery_share += s.share
            profit -= moved * s.commission
        elif isinstance(s, MissingFeed) and s.start <= week_start < s.end:
            missing = True
    delivery = revenue * min(delivery_share, 1.0)
    return WeekValues(
        revenue=revenue, instore=revenue - delivery, delivery=delivery, profit=profit, missing=missing
    )


def _weeks_in_month(first: date) -> list[date]:
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    d = first - timedelta(days=first.weekday())
    out = []
    while d < nxt:
        out.append(d)
        d += timedelta(days=7)
    return out


def month_values(sc: Scenario, first: date) -> tuple[float, float]:
    """Revenue and operating profit for a calendar month (pro-rata over the weeks that touch it)."""
    rev = prof = 0.0
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    for w in _weeks_in_month(first):
        days = sum(1 for i in range(7) if first <= w + timedelta(days=i) < nxt)
        wv = week_values(sc, w)
        rev += wv.revenue * days / 7
        prof += wv.profit * days / 7
    return rev, prof


# ------------------------------------------------------------------ the snapshot


def _floor_and_buffer(persona: Persona) -> tuple[Decimal, Decimal]:
    wpm = P.num("weeks_per_month")
    floor = persona.payroll_monthly_cny / wpm * P.num("floor_payroll_weeks") + (
        persona.loan_repayment_monthly_cny * P.num("floor_loan_repayments")
    )
    buffer = persona.payroll_monthly_cny / wpm * P.num("buffer_payroll_weeks")
    return q0(floor), q0(buffer)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _extra_loan(sc: Scenario, d: date) -> float:
    """Above-normal borrowing still outstanding on `d` (extra draws, repaid evenly)."""
    extra = 0.0
    for s in sc.shocks:
        if isinstance(s, AboveNormalDraw) and s.on <= d:
            done = min(max((d - s.on).days // 7, 0), s.repay_weeks)
            extra += float(s.amount_cny) * (1 - done / s.repay_weeks)
    return extra


def _cash_and_loan(sc: Scenario, as_of: date) -> tuple[Decimal, Decimal, Decimal | None]:
    persona = sc.persona
    floor, buffer = _floor_and_buffer(persona)
    cash = float(floor + buffer + persona.spare_target_cny)
    normal = Decimal(persona.normal_loan_by_month[as_of.month - 1])
    pot: float | None = None
    keep = float(floor + buffer)
    r2_tol = P.fnum("r2_tolerance_cny")
    wpm = P.weeks_per_month()
    outflow = float(persona.drawings_monthly_cny + persona.commitments_monthly_cny) / wpm
    w = _monday(BASE_AS_OF)
    goal = sc.goal
    if goal is not None and goal.start <= as_of:
        pot = float(goal.spare_moved_cny)
        cash -= float(goal.spare_moved_cny)
    while w + timedelta(days=7) <= as_of:
        cash += week_values(sc, w).profit - outflow
        month_start = w.month != (w - timedelta(days=7)).month
        if goal is not None and goal.start < w and month_start:
            # the signed instruction, re-checked every month: R2 and floor + buffer pause it
            sa = float(goal.monthly_cny)
            if _extra_loan(sc, w) <= r2_tol and cash - sa >= keep:
                cash -= sa
                pot = (pot or 0.0) + sa
        for s in sc.shocks:
            if isinstance(s, AboveNormalDraw):
                if s.on <= w < s.on + timedelta(weeks=s.repay_weeks):
                    cash -= float(s.amount_cny) / s.repay_weeks
                if _monday(s.on) == w:
                    cash += float(s.amount_cny)
        w += timedelta(days=7)
    extra = _extra_loan(sc, as_of)
    return (
        q0(Decimal(repr(cash))),
        q0(normal + Decimal(repr(extra))),
        (None if pot is None else q0(Decimal(repr(pot)))),
    )


def generate_chen(as_of: date = BASE_AS_OF, scenario: Scenario | None = None) -> FeedSnapshot:
    """Chen's feed on `as_of` (history to the last full month; weekly series to the last full week)."""
    sc = scenario or Scenario()
    persona = sc.persona
    first_this = date(as_of.year, as_of.month, 1)
    months: list[ProfitMonth] = []
    m = first_this
    for _ in range(persona.history_months):
        m = date(m.year - (m.month == 1), (m.month - 2) % 12 + 1, 1)
        rev, prof = month_values(sc, m)
        months.append(
            ProfitMonth(
                month=m, revenue_cny=q0(Decimal(repr(rev))), operating_profit_cny=q0(Decimal(repr(prof)))
            )
        )
    months.reverse()
    weeks: list[WeekProfit] = []
    w = _monday(as_of) - timedelta(weeks=persona.weekly_weeks)
    while w + timedelta(days=7) <= as_of:
        v = week_values(sc, w)
        weeks.append(
            WeekProfit(
                week_start=w,
                revenue_cny=q0(Decimal(repr(v.revenue))),
                instore_revenue_cny=q0(Decimal(repr(v.instore))),
                delivery_revenue_cny=q0(Decimal(repr(v.delivery))),
                operating_profit_cny=q0(Decimal(repr(v.profit))),
                feed_missing=v.missing,
            )
        )
        w += timedelta(days=7)
    cash, loan, pot = _cash_and_loan(sc, as_of)
    return FeedSnapshot(
        as_of=as_of,
        company_name=persona.company_name,
        shops=persona.shops,
        business_type=persona.business_type,
        profit_history=months,
        cash_balance_cny=cash,
        monthly_payroll_cny=persona.payroll_monthly_cny,
        monthly_loan_repayment_cny=persona.loan_repayment_monthly_cny,
        loan_balance_cny=loan,
        loan_limit_cny=persona.loan_limit_cny,
        normal_loan_balance_by_month_cny={
            i + 1: Decimal(v) for i, v in enumerate(persona.normal_loan_by_month)
        },
        owner_drawings_monthly_cny=persona.drawings_monthly_cny,
        home_commitments_monthly_cny=persona.commitments_monthly_cny,
        best_shop_cups_per_day=persona.best_shop_cups_per_day,
        avg_shop_cups_per_day=persona.avg_shop_cups_per_day,
        simulated=True,
        weekly_profit=weeks,
        pot_balance_cny=pot,
    )


def scenario(
    seed: int = DEFAULT_SEED, shocks: Sequence[Shock] = (), goal: GoalTransfers | None = None
) -> Scenario:
    return Scenario(seed=seed, shocks=tuple(shocks), goal=goal)
