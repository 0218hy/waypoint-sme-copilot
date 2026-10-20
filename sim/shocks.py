"""Scripted shocks for the Goal Keeper demo and E6 (SPEC §7.2, §11): profit drops, channel shifts,
above-normal loan draws and missing feed weeks. Pure data; `sim.chen` applies them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class SalesDrop:
    """Sales fall by `pct` at `shops` of the chain's shops from `start` (the demo: −20% at four of 30)."""

    start: date
    shops: int = 4
    pct: float = 0.20


@dataclass(frozen=True)
class ProfitShock:
    """Chain-wide operating profit falls by `pct` from `start` (E6: −10 / −20 / −30%)."""

    start: date
    pct: float = 0.20


@dataclass(frozen=True)
class ChannelShift:
    """`share` of in-store sales moves to delivery platforms from `start`. Total sales are unchanged; profit
    falls only by any extra commission on the moved sales (default 0: what the bank sees is the settlement
    channel moving). Must never raise an alert on its own."""

    start: date
    share: float = 0.25
    commission: float = 0.0


@dataclass(frozen=True)
class AboveNormalDraw:
    """An extra WeBank draw of `amount_cny` on `on`, repaid evenly over `repay_weeks` (trips R2)."""

    on: date
    amount_cny: Decimal = Decimal("400000")
    repay_weeks: int = 12


@dataclass(frozen=True)
class MissingFeed:
    """The feed returns nothing for weeks starting in [start, end)."""

    start: date
    end: date


Shock = SalesDrop | ProfitShock | ChannelShift | AboveNormalDraw | MissingFeed


def demo_dip(plan_start: date, after_weeks: int = 8, shops: int = 4, pct: float = 0.20) -> list[Shock]:
    """The pitch's moment 6: eight weeks into the goal, sales dip at four shops."""
    return [SalesDrop(start=plan_start + timedelta(weeks=after_weeks), shops=shops, pct=pct)]


def e6_profit_drops(plan_start: date, after_weeks: int = 8) -> dict[str, list[Shock]]:
    s = plan_start + timedelta(weeks=after_weeks)
    return {f"profit_-{int(p * 100)}": [ProfitShock(start=s, pct=p)] for p in (0.10, 0.20, 0.30)}


def channel_shift_only(plan_start: date, after_weeks: int = 8, share: float = 0.25) -> list[Shock]:
    return [ChannelShift(start=plan_start + timedelta(weeks=after_weeks), share=share)]


def above_normal_draw(
    plan_start: date, after_weeks: int = 4, amount_cny: Decimal = Decimal("400000"), repay_weeks: int = 12
) -> list[Shock]:
    return [
        AboveNormalDraw(
            on=plan_start + timedelta(weeks=after_weeks), amount_cny=amount_cny, repay_weeks=repay_weeks
        )
    ]


def missing_weeks(plan_start: date, after_weeks: int = 6, weeks: int = 2) -> list[Shock]:
    s = plan_start + timedelta(weeks=after_weeks)
    return [MissingFeed(start=s, end=s + timedelta(weeks=weeks))]


# ------------------------------------------------------------- E6-heldout (prereg addendum 2026-10-20 (7))


def profit_drop(plan_start: date, after_weeks: int, pct: float = 0.20) -> list[Shock]:
    """A chain-wide profit drop of `pct` from `after_weeks` after the start (revenue unchanged)."""
    return [ProfitShock(start=plan_start + timedelta(weeks=after_weeks), pct=pct)]


def chainwide_sales_drop(
    plan_start: date, after_weeks: int, pct: float = 0.0625, shops: int = 30
) -> list[Shock]:
    """Sales fall by `pct` at every shop, so revenue moves too. 6.25% of Chen's sales is -20% of the average
    profit at the 62% contribution margin (0.20 x RMB 2.52m / (0.62 x RMB 13m))."""
    return [SalesDrop(start=plan_start + timedelta(weeks=after_weeks), shops=shops, pct=pct)]


def channel_shift_with_commission(
    plan_start: date, after_weeks: int, share: float = 0.25, commission: float = 0.05
) -> list[Shock]:
    """`share` of in-store sales moves to delivery and each moved yuan costs `commission` more: a real profit
    fall of about share x commission x sales / profit (-6% of Chen's profit at 0.25 and 0.05)."""
    return [ChannelShift(start=plan_start + timedelta(weeks=after_weeks), share=share, commission=commission)]
