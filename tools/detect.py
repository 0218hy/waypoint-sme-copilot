"""Goal Keeper change detection (SPEC §7.2): integrity checks first, then a one-sided CUSUM.

The baseline (level and seasonal shape) is fixed when the goal starts. Each week's operating profit is
compared with the baseline's expectation for that calendar month (`ratio`). Weeks with a missing feed are
skipped. The CUSUM runs on standardised drops below an adaptive reference: the log ratio's recent level (an
EWMA that lags a few weeks, so a step is compared with the level before it), in units of the owner's own
weekly noise. A week where sales moved to delivery while total revenue held is a channel shift and never
adds evidence of a drop. A slow week alone can't alarm: the CUSUM needs a run. (results/prereg.md addendum
2026-10-20 (7).)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from tools import params as P
from tools.models import FeedSnapshot, ProfitMonth, WeekProfit

_MIN_RATIO = 0.05  # log ratios are taken of max(ratio, this): a week at or below zero profit is a deep drop
_MIN_SIGMA = 0.03


@dataclass(frozen=True)
class Baseline:
    start: date
    level: float  # mean weekly operating profit in the history, deseasonalised
    shape: tuple[float, ...]  # Jan..Dec relative weekly profit (mean 1.0), by the month a week starts in
    revenue_level: float
    revenue_shape: tuple[float, ...] = (1.0,) * 12
    delivery_share: float = 0.0  # the owner's mean delivery share of revenue before the start
    pre_x: tuple[float, ...] = ()  # log actual/expected profit of each pre-start week, oldest first
    sigma: float = 0.1  # weekly noise of that log ratio (robust, from first differences)
    revenue_sigma: float = 0.1


@dataclass(frozen=True)
class WeekCheck:
    week_start: date
    ratio: float | None  # actual / expected profit; None if missing
    missing: bool
    channel_shift: bool
    z: float | None = None  # drop below the adaptive reference, in sigmas (never > 0 on a channel-shift week)


@dataclass(frozen=True)
class Detection:
    alarm: bool
    alarm_week: date | None
    weeks_checked: int
    recent_ratio: float | None  # mean ratio since the CUSUM started climbing (or over the last 4 weeks)
    channel_shift_weeks: int
    missing_weeks: int
    cusum: float


def _next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def weekly_rates(history: list[ProfitMonth], field: str = "operating_profit_cny") -> list[tuple[date, float]]:
    """Each history month's weekly rate, attributed the way the weekly checks attribute weeks: to the month a
    week starts in.

    A month's total in the feed pro-rates the weeks that touch it, and the first days of a month can belong
    to a week that started the month before (and runs at that month's level). Those carried days are taken
    out using the previous month's rate; the first month, with no previous one, is taken as it is."""
    out: list[tuple[date, float]] = []
    prev: tuple[date, float] | None = None
    for m in sorted(history, key=lambda x: x.month):
        first = m.month
        days = (_next_month(first) - first).days
        carried = (7 - first.weekday()) % 7  # days of this month in a week that started the month before
        total = float(getattr(m, field))
        if prev is not None and _next_month(prev[0]) == first and carried:
            rate = (total - carried / 7 * prev[1]) / ((days - carried) / 7)
        else:
            rate = total / (days / 7)
        out.append((first, rate))
        prev = (first, rate)
    return out


def _shape(
    feed: FeedSnapshot, field: str = "operating_profit_cny", shrink: bool = True
) -> tuple[float, ...]:
    """Jan..Dec relative weekly profit (or revenue), shrunk toward 1 by how noisy the owner's own history
    says it is.

    Fitted on `weekly_rates` (so it matches the weeks the checks compare). With two years of history each
    month's mean rests on two noisy values, and that noise would sit in every week's "expected" value.
    Empirical Bayes: the spread between years within a month estimates the noise; the spread of the monthly
    means is signal plus noise / n; shrink by the noise share. The shrink also pulls a large, real trough
    toward flat (Chen's January-February), so it is a parameter (`detect_shape_shrink`).
    """
    by_m: dict[int, list[float]] = {}
    for first, rate in weekly_rates(feed.profit_history, field):
        by_m.setdefault(first.month, []).append(rate)
    vals = {k: sum(v) / len(v) for k, v in by_m.items()}
    overall = sum(vals.values()) / len(vals) if vals else 1.0
    if overall <= 0:
        return tuple([1.0] * 12)
    raw = [vals.get(k, overall) / overall for k in range(1, 13)]
    w = _shrink_weight(by_m, overall, raw) if shrink else 1.0
    return tuple(1 + w * (r - 1) for r in raw)


def _shrink_weight(by_m: dict[int, list[float]], overall: float, raw: list[float]) -> float:
    within = [_var([v / overall for v in vs]) for vs in by_m.values() if len(vs) > 1]
    if not within or len(raw) < 2:
        return 1.0  # one year of history: nothing to estimate the noise from
    n = sum(len(vs) for vs in by_m.values()) / len(by_m)
    total = _var(raw)
    if total <= 0:
        return 0.0
    return max(0.0, 1 - (sum(within) / len(within) / n) / total)


def _var(xs: list[float]) -> float:
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def _log_ratio(actual: float, expected: float) -> float:
    return math.log(max(actual / expected, _MIN_RATIO))


def _robust_sigma(xs: list[float]) -> float:
    """Weekly noise sd from first differences (MAD x 1.4826 / sqrt 2): a step in level barely moves it."""
    d = sorted(b - a for a, b in zip(xs, xs[1:], strict=False))
    if len(d) <= 4:
        return 0.1
    med = d[len(d) // 2] if len(d) % 2 else (d[len(d) // 2 - 1] + d[len(d) // 2]) / 2
    dev = sorted(abs(x - med) for x in d)
    mad = dev[len(dev) // 2] if len(dev) % 2 else (dev[len(dev) // 2 - 1] + dev[len(dev) // 2]) / 2
    return max(_MIN_SIGMA, 1.4826 * mad / math.sqrt(2))


def baseline(feed_at_start: FeedSnapshot, start: date, shrink: bool | None = None) -> Baseline:
    """What the plan assumed: the level of the owner's whole monthly history (the same basis tools.plan
    uses) and its seasonal shape (shrunk for noise, see `_shape`), as a weekly level and shape. Revenue is
    based on the recent weekly series and its own seasonal shape; the weekly noise and the reference's warm-up
    come from the weeks before the start."""
    if shrink is None:
        shrink = bool(P.param("detect_shape_shrink").value)
    shape = _shape(feed_at_start, shrink=shrink)
    rshape = _shape(feed_at_start, "revenue_cny", shrink=shrink)
    hist = [float(m.operating_profit_cny) for m in feed_at_start.profit_history]
    monthly_mean = sum(hist) / len(hist) if hist else 0.0
    level = monthly_mean / P.fnum("weeks_per_month")
    weeks = [w for w in feed_at_start.weekly_profit if not w.feed_missing and w.week_start < start]
    rev = [float(w.revenue_cny) / max(rshape[w.week_start.month - 1], 1e-6) for w in weeks]
    rev_level = sum(rev) / len(rev) if rev else 0.0
    shares = [float(w.delivery_revenue_cny) / float(w.revenue_cny) for w in weeks if w.revenue_cny > 0]
    pre_x: list[float] = []
    pre_rx: list[float] = []
    for w in weeks:
        m = w.week_start.month - 1
        if level > 0 and shape[m] > 0:
            pre_x.append(_log_ratio(float(w.operating_profit_cny), level * shape[m]))
        if rev_level > 0 and w.revenue_cny > 0:
            pre_rx.append(_log_ratio(float(w.revenue_cny), rev_level * rshape[m]))
    return Baseline(
        start=start,
        level=level,
        shape=shape,
        revenue_level=rev_level,
        revenue_shape=rshape,
        delivery_share=sum(shares) / len(shares) if shares else 0.0,
        pre_x=tuple(pre_x),
        sigma=_robust_sigma(pre_x),
        revenue_sigma=_robust_sigma(pre_rx),
    )


def check_weeks(
    feed_now: FeedSnapshot, base: Baseline, lam: float | None = None, lag: int | None = None
) -> list[WeekCheck]:
    """Each week since the start: ratio to the fixed baseline, channel-shift flag, and the CUSUM's input z.

    z = (reference - log ratio) / sigma, where the reference is an EWMA (`detect_ref_lambda`) of the
    observed log ratios up to `detect_ref_lag` observed weeks before this one, warmed up on the pre-start
    weeks."""
    lam = P.fnum("detect_ref_lambda") if lam is None else lam
    lag = int(P.fnum("detect_ref_lag")) if lag is None else lag
    ewma: list[float] = []
    for x in base.pre_x:
        ewma.append(x if not ewma else (1 - lam) * ewma[-1] + lam * x)
    out: list[WeekCheck] = []
    for w in feed_now.weekly_profit:
        if w.week_start < base.start:
            continue
        if w.feed_missing:
            out.append(WeekCheck(w.week_start, None, True, False))
            continue
        expected = base.level * base.shape[w.week_start.month - 1]
        if expected <= 0:
            out.append(WeekCheck(w.week_start, None, False, False))
            continue
        actual = float(w.operating_profit_cny)
        x = _log_ratio(actual, expected)
        j = len(ewma) - lag - 1
        ref = ewma[j] if j >= 0 else 0.0
        shift = _channel_shift(w, base)
        z = (ref - x) / base.sigma
        if shift:
            z = min(z, 0.0)  # a channel-shift week can never add evidence of a drop
        ewma.append(x if not ewma else (1 - lam) * ewma[-1] + lam * x)
        out.append(WeekCheck(w.week_start, actual / expected, False, shift, z))
    return out


def _channel_shift(w: WeekProfit, base: Baseline) -> bool:
    """Sales moved to delivery: the delivery share is above the owner's own pre-start share by more than
    `detect_channel_shift_tolerance` while total revenue holds (no more than `detect_shift_revenue_sd` revenue
    sigmas below the revenue expected for that month)."""
    if base.revenue_level <= 0 or w.revenue_cny <= 0:
        return False
    share = float(w.delivery_revenue_cny) / float(w.revenue_cny)
    if share - base.delivery_share <= P.fnum("detect_channel_shift_tolerance"):
        return False
    expected = base.revenue_level * base.revenue_shape[w.week_start.month - 1]
    rz = _log_ratio(float(w.revenue_cny), expected) / base.revenue_sigma
    return rz >= -P.fnum("detect_shift_revenue_sd")


def cusum(checks: list[WeekCheck], k: float | None = None, h: float | None = None) -> Detection:
    """Page's one-sided CUSUM on z (in sigmas): S = max(0, S + z - k); alarm when S > h."""
    k = P.fnum("detect_k_sd") if k is None else k
    h = P.fnum("detect_h_sd") if h is None else h
    s, alarm_week, start_idx = 0.0, None, None
    used = [c for c in checks if not c.missing and c.ratio is not None]
    shift_weeks = sum(1 for c in checks if c.channel_shift)
    for i, c in enumerate(used):
        prev = s
        s = max(0.0, s + (c.z if c.z is not None else 0.0) - k)
        if prev == 0.0 and s > 0.0:
            start_idx = i
        if s == 0.0:
            start_idx = None
        if s > h and alarm_week is None:
            alarm_week = c.week_start
    window = used[start_idx:] if start_idx is not None else used[-4:]
    ratios = [1.0 if c.channel_shift else float(c.ratio or 1.0) for c in window]
    recent = sum(ratios) / len(ratios) if ratios else None
    return Detection(
        alarm=alarm_week is not None,
        alarm_week=alarm_week,
        weeks_checked=len(used),
        recent_ratio=recent,
        channel_shift_weeks=shift_weeks,
        missing_weeks=sum(1 for c in checks if c.missing),
        cusum=s,
    )


def detect(feed_at_start: FeedSnapshot, feed_now: FeedSnapshot, start: date) -> Detection:
    return cusum(check_weeks(feed_now, baseline(feed_at_start, start)))


def scaled_feed(feed: FeedSnapshot, ratio: float, before: date | None = None) -> FeedSnapshot:
    """The re-plan's assumption after a detected drop: the observed profit level persists.

    With `before`, only months before that date are scaled: months since the goal started are already in
    the history as they happened, and scaling them again would count the drop twice."""
    r = Decimal(str(round(max(0.0, min(ratio, 1.5)), 4)))
    hist = [
        m.model_copy(update={"operating_profit_cny": m.operating_profit_cny * r})
        if before is None or m.month < before
        else m
        for m in feed.profit_history
    ]
    return feed.model_copy(update={"profit_history": hist})


def mean_ratio(checks: list[WeekCheck]) -> float | None:
    """Actual over expected profit across every checked week (a channel-shift week counts as on plan).

    The re-plan uses this, not Detection.recent_ratio: the CUSUM's own window is the run of weak weeks that
    set off the alarm, so it is biased low by construction."""
    rs = [1.0 if c.channel_shift else float(c.ratio) for c in checks if not c.missing and c.ratio is not None]
    return sum(rs) / len(rs) if rs else None


def weeks_between(a: date, b: date) -> int:
    return max(0, (b - a).days // 7)


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())
