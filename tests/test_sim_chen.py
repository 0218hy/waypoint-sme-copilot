from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from mock_webank import feed as mock
from sim import shocks
from sim.chen import BASE_AS_OF, Scenario, generate_chen, scenario
from tools import params as P
from tools.funding import r2_paused, spare_cash


def test_chen_shape() -> None:
    f = generate_chen()
    assert f.simulated and f.shops == 30
    assert len(f.profit_history) == 24
    year = f.profit_history[-12:]
    sales = sum(m.revenue_cny for m in year)
    # The feed's cups agree with its sales (addendum 2026-10-20 (14)): average shop x price x days x shops.
    assert f.avg_shop_cups_per_day is not None and f.best_shop_cups_per_day is not None
    implied = Decimal(f.avg_shop_cups_per_day) * P.num("home_cup_price_cny") * 365 * f.shops
    assert abs(implied - sales) / sales < Decimal("0.15")
    assert f.avg_shop_cups_per_day < f.best_shop_cups_per_day < 2 * f.avg_shop_cups_per_day
    assert Decimal(12_000_000) < sales < Decimal(14_000_000)
    avg = sum(m.operating_profit_cny for m in f.profit_history) / 24
    assert Decimal(180_000) < avg < Decimal(240_000)
    feb = [m for m in f.profit_history if m.month.month == 2]
    oct_ = [m for m in f.profit_history if m.month.month in (10, 11, 12)]
    assert max(m.operating_profit_cny for m in feb) < min(m.operating_profit_cny for m in oct_)
    assert f.owner_drawings_monthly_cny == Decimal(78000)
    assert f.loan_limit_cny == Decimal(2_000_000)
    assert min(f.normal_loan_balance_by_month_cny.values()) >= Decimal(100000)
    assert max(f.normal_loan_balance_by_month_cny.values()) <= Decimal(550000)
    assert max(f.normal_loan_balance_by_month_cny, key=lambda k: f.normal_loan_balance_by_month_cny[k]) in (
        6,
        7,
        8,
    )
    assert spare_cash(f).value == Decimal(500000)
    assert not r2_paused(f)
    assert len(f.weekly_profit) == 26


def test_seeded_and_consistent_across_dates() -> None:
    a, b = generate_chen(), generate_chen()
    assert a.model_dump() == b.model_dump()
    later = generate_chen(BASE_AS_OF + timedelta(weeks=9))
    common = {m.month: m for m in a.profit_history}
    for m in later.profit_history:
        if m.month in common:
            assert m == common[m.month]
    assert generate_chen(scenario=Scenario(seed=2)).profit_history != a.profit_history


def test_sales_drop_reduces_profit_from_its_start() -> None:
    start = BASE_AS_OF + timedelta(weeks=8)
    as_of = BASE_AS_OF + timedelta(weeks=16)
    base = generate_chen(as_of)
    hit = generate_chen(as_of, scenario(shocks=shocks.demo_dip(BASE_AS_OF)))
    for w0, w1 in zip(base.weekly_profit, hit.weekly_profit, strict=True):
        if w0.week_start >= start:
            assert w1.operating_profit_cny < w0.operating_profit_cny
            assert w1.revenue_cny < w0.revenue_cny
        else:
            assert w1 == w0
    assert hit.cash_balance_cny < base.cash_balance_cny


def test_channel_shift_keeps_total_revenue() -> None:
    as_of = BASE_AS_OF + timedelta(weeks=16)
    base = generate_chen(as_of)
    sh = generate_chen(as_of, scenario(shocks=shocks.channel_shift_only(BASE_AS_OF)))
    last0, last1 = base.weekly_profit[-1], sh.weekly_profit[-1]
    assert last1.revenue_cny == last0.revenue_cny
    assert last1.instore_revenue_cny < last0.instore_revenue_cny
    assert last1.delivery_revenue_cny > last0.delivery_revenue_cny
    assert last1.operating_profit_cny == last0.operating_profit_cny
    costly = generate_chen(as_of, scenario(shocks=[shocks.ChannelShift(start=BASE_AS_OF, commission=0.05)]))
    assert costly.weekly_profit[-1].operating_profit_cny < last0.operating_profit_cny


def test_above_normal_draw_trips_r2_then_clears() -> None:
    sc = scenario(shocks=shocks.above_normal_draw(BASE_AS_OF, after_weeks=4, repay_weeks=12))
    assert r2_paused(generate_chen(BASE_AS_OF + timedelta(weeks=5), sc))
    assert not r2_paused(generate_chen(BASE_AS_OF + timedelta(weeks=20), sc))


def test_missing_feed_weeks_flagged() -> None:
    sc = scenario(shocks=shocks.missing_weeks(BASE_AS_OF, after_weeks=6, weeks=2))
    f = generate_chen(BASE_AS_OF + timedelta(weeks=12), sc)
    assert sum(w.feed_missing for w in f.weekly_profit) == 2


def test_e6_profit_drops() -> None:
    sets = shocks.e6_profit_drops(BASE_AS_OF)
    assert set(sets) == {"profit_-10", "profit_-20", "profit_-30"}
    as_of = BASE_AS_OF + timedelta(weeks=14)
    base = generate_chen(as_of).weekly_profit[-1].operating_profit_cny
    hit = generate_chen(as_of, scenario(shocks=sets["profit_-20"])).weekly_profit[-1].operating_profit_cny
    assert abs(hit / base - Decimal("0.8")) < Decimal("0.001")


def test_mock_feed_registry_and_goal_transfers() -> None:
    mock.reset()
    owner = "o-test"
    f0 = mock.get_feed(owner)
    assert f0 == generate_chen() and f0.pot_balance_cny is None
    mock.register_goal(owner, BASE_AS_OF, Decimal(500000), Decimal(84000))
    later = mock.get_feed(owner, BASE_AS_OF + timedelta(weeks=9))
    assert later.pot_balance_cny is not None and later.pot_balance_cny > Decimal(500000)
    mock.apply_demo_dip(owner)
    dipped = mock.get_feed(owner, BASE_AS_OF + timedelta(weeks=12))
    plain = generate_chen(BASE_AS_OF + timedelta(weeks=12))
    assert dipped.weekly_profit[-1].operating_profit_cny < plain.weekly_profit[-1].operating_profit_cny
    assert mock.get_feed("someone-else", date(2026, 10, 19)) == generate_chen()
    mock.reset()


# ------------------------------------------------------------------ the signed set-aside, as the bank runs it


def _pot_path(sc: Scenario, weeks: int) -> list[tuple[date, Decimal, Decimal]]:
    """(as_of, cash, pot) at each Monday after the base date."""
    out = []
    for k in range(1, weeks + 1):
        f = generate_chen(BASE_AS_OF + timedelta(weeks=k), sc)
        out.append((f.as_of, f.cash_balance_cny, f.pot_balance_cny or Decimal(0)))
    return out


def test_setaside_moves_the_fixed_amount_once_a_month() -> None:
    from sim.chen import GoalTransfers

    monthly = Decimal(80000)
    sc = Scenario(goal=GoalTransfers(start=BASE_AS_OF, spare_moved_cny=Decimal(500000), monthly_cny=monthly))
    path = _pot_path(sc, 20)
    prev = Decimal(500000)
    moved = 0
    for as_of, _cash, pot in path:
        step = pot - prev
        week = as_of - timedelta(days=7)  # the week that just ended
        if (week - timedelta(days=7)).month == week.month:
            assert abs(step) <= 1, f"no transfer mid-month ({week})"
        else:
            assert abs(step - monthly) <= 1 or abs(step) <= 1
            moved += abs(step - monthly) <= 1
        prev = pot
    assert moved >= 3


def test_setaside_pauses_below_floor_plus_buffer_and_under_r2() -> None:
    """The bank honours the pause, re-checked every month: a month whose transfer would leave cash below
    floor + buffer is skipped, and so is any month while borrowing is above normal (R2)."""
    from sim.chen import CHEN, GoalTransfers, _floor_and_buffer

    floor, buffer = _floor_and_buffer(CHEN)
    goal = GoalTransfers(start=BASE_AS_OF, spare_moved_cny=Decimal(500000), monthly_cny=Decimal(150000))
    path = _pot_path(Scenario(goal=goal), 30)
    prev_cash, prev = None, Decimal(500000)
    for _as_of, cash, pot in path:
        if pot > prev:  # a transfer ran: it never took cash below floor + buffer
            assert cash >= floor + buffer - 1
        prev_cash, prev = cash, pot
    assert prev_cash is not None
    # a transfer bigger than anything above floor + buffer never runs
    huge = GoalTransfers(start=BASE_AS_OF, spare_moved_cny=Decimal(500000), monthly_cny=Decimal(5_000_000))
    assert all(pot == Decimal(500000) for _, _, pot in _pot_path(Scenario(goal=huge), 12))
    # R2: an above-normal draw in week 2, repaid over 12 weeks, pauses the months it covers
    draw = shocks.above_normal_draw(BASE_AS_OF, after_weeks=2, repay_weeks=12)
    hot = Scenario(goal=goal, shocks=tuple(draw))
    calm = _pot_path(Scenario(goal=goal), 12)
    paused = _pot_path(hot, 12)
    assert paused[-1][2] < calm[-1][2]
    prev, held = Decimal(500000), 0
    for as_of, _c, pot in paused:
        if r2_paused(generate_chen(as_of - timedelta(days=7), hot)):  # R2 held when the week began
            assert pot == prev
            held += 1
        prev = pot
    assert held >= 8
