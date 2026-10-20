"""The plan model (SPEC §6.6): a seeded weekly Monte Carlo over runs x 156 weeks, vectorised over runs.

Each week, per run:
  1. home cash += profit − drawings − home commitments (profit: seasonal mean from his own history x a
     persistent monthly level x weekly noise, minus occasional jump shocks);
  2. the monthly set-aside runs as the instruction the owner signs: in the first week of each calendar
     month it moves the fixed amount (s x average monthly profit, the plan's monthly figure) unless R2 is
     tripped or the transfer would leave home cash below floor + buffer, checked again every month; a
     paused month is skipped, not made up later;
  3. transfers leave only at milestones, in legal order: lender consent → ODI filing → bank registration
     → incorporation + account → setup transfer → first main transfer → sign the lease → fit-out → licence
     (local hiring runs alongside the fit-out; the shop opens only when both are done)
     → opening;
  4. the first main transfer must cover the deposit, the whole fit-out and pre-opening rent (R6), and the
     lease is signed only after it;
  5. opening needs the full reserve in Singapore.
Uncertainty: profit noise and shocks, correlated cost overruns (Gaussian copula), FX, and triangular
durations. All draws come from one seeded generator and are shared across set-aside shares (common random
numbers), so the floor risk is comparable along the slider. A reduced run count (the slider preview) uses
the first runs of the full set, never a different draw. The wall is the largest share whose floor risk
is at most the limit with its Wilson 95% upper bound, so it is not decided inside Monte Carlo noise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

from tools import params as P
from tools.figtools import derived
from tools.figures import Figure, dec, q0
from tools.funding import average_monthly_profit, loan_excess_cny, plan_start, safety_floor, spare_cash
from tools.models import CostCard, FeedSnapshot, FundingPlan, PlanChart, PlanResult, Profile
from tools.params import Tri
from tools.stats import F64, copula_uniforms, tri_ppf, wilson_upper

I64 = NDArray[np.int64]
B_ = NDArray[np.bool_]
TOOL = "simulate_plan"
CHAIN = (
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
)
DURATION_KEYS = (
    "lender_consent_weeks",
    "odi_filing_weeks",
    "odi_bank_registration_weeks",
    "incorporation_weeks",
    "sg_account_weeks",
    "sign_lease_lag_weeks",
    "fitout_weeks",
    "licence_weeks",
)
NEVER = 10**6


@dataclass(frozen=True)
class LineSpec:
    transfer: str  # setup | first | opening
    low: float
    likely: float
    high: float
    overrun: bool


@dataclass(frozen=True)
class PlanInputs:
    """Everything the simulation depends on; hashable so draws and the wall can be cached."""

    start: date
    horizon: int
    season: tuple[float, ...]  # mean monthly profit by calendar month (CNY), Jan..Dec
    cv_monthly: float
    outflow_monthly: float  # drawings + home commitments
    floor: float
    buffer: float
    home_cash0: float
    spare: float
    own_savings: float
    pot0: float
    lines: tuple[LineSpec, ...]
    likely_total_sgd: float  # the card's likely (median) total, for the gap
    first_adjust_sgd: float  # rent-free difference vs the card (incl. GST)
    partner_share: float
    fx0: float
    loan_excess0: float
    r2_pause_weeks: int
    available_week: int
    durations: tuple[Tri, ...]
    params_version: int = field(default=0)

    @property
    def mean_monthly_profit(self) -> float:
        return float(np.mean(self.season))


@dataclass
class Draws:
    profit: F64  # runs x horizon (CNY per week)
    dur: I64  # runs x len(DURATION_KEYS)
    need: F64  # runs x 3 cumulative CNY needs: setup, setup+first, total


@dataclass
class SimOut:
    share: float
    weeks: dict[str, F64]  # milestone -> per-run week (inf = not reached)
    floor_breach: B_
    saved: F64  # runs x horizon, cumulative funds raised for Singapore
    home: F64  # runs x horizon
    setaside: F64  # runs x horizon
    need: F64
    paused: B_


# ------------------------------------------------------------------ inputs


def _season_and_cv(src: FeedSnapshot | Profile) -> tuple[tuple[float, ...], float]:
    """Seasonal mean profit by calendar month and the monthly noise CV, from his own history if 12+ months."""
    if isinstance(src, FeedSnapshot) and len(src.profit_history) >= 12:
        by_m: dict[int, list[float]] = {}
        for m in src.profit_history:
            by_m.setdefault(m.month.month, []).append(float(m.operating_profit_cny))
        overall = float(np.mean([v for vs in by_m.values() for v in vs]))
        season = tuple(float(np.mean(by_m[k])) if k in by_m else overall for k in range(1, 13))
        resid = [v / season[k - 1] - 1.0 for k, vs in by_m.items() for v in vs if season[k - 1] > 0]
        dof = max(len(resid) - 12, 1)
        cv = (
            math.sqrt(sum(r * r for r in resid) / dof)
            if len(resid) > 12
            else P.fnum("profit_noise_monthly_cv_default")
        )
        return season, cv
    prof = average_monthly_profit(src)
    base = 0.0 if prof is None else float(prof)
    shape = [float(x) for x in P.items("seasonal_profile_default")]
    return tuple(base * x for x in shape), P.fnum("profit_noise_monthly_cv_default")


def _lines(card: CostCard) -> tuple[LineSpec, ...]:
    from tools.costs import transfer_for

    out = []
    for ln in card.lines:
        # re-sample around the triangular mode (the line at every input's most likely value); a quoted line's
        # range is the quote plus its variation allowance, so it can still overrun
        mode = float(ln.mode_sgd) if ln.mode_sgd is not None else float(ln.likely_sgd)
        low = float(ln.low_sgd) if ln.low_sgd is not None else mode
        high = float(ln.high_sgd) if ln.high_sgd is not None else float(ln.bad_sgd)
        out.append(LineSpec(transfer_for(ln.due), min(low, mode), mode, max(high, mode), ln.overrun))
    return tuple(out)


def build_inputs(
    src: FeedSnapshot | Profile,
    card: CostCard,
    plan: FundingPlan,
    start_date: date | None = None,
    unit_available_from: date | None = None,
    r2_pause_weeks: int = 0,
) -> PlanInputs:
    start = plan_start(src, start_date)
    season, cv = _season_and_cv(src)
    fl = safety_floor(src)
    floor = 0.0 if fl is None else float(fl.floor_cny)
    buffer = 0.0 if fl is None else float(fl.buffer_cny)
    spare_v = spare_cash(src).value
    spare = 0.0 if spare_v is None else float(spare_v)
    cash = src.cash_balance_cny
    home0 = float(cash) - spare if cash is not None else floor + buffer
    drawings = src.owner_drawings_monthly_cny
    commitments = src.home_commitments_monthly_cny if isinstance(src, FeedSnapshot) else Decimal(0)
    outflow = float((drawings or Decimal(0)) + commitments)
    adj = 0.0
    if card.rent_free_months is not None and card.rent_monthly_sgd is not None:
        adj = float((card.rent_free_months - plan.rent_free_months) * card.rent_monthly_sgd) * (
            1 + P.fnum("gst_rate")
        )
    avail = 0
    if unit_available_from is not None:
        avail = max(0, (unit_available_from - start).days // 7)
    return PlanInputs(
        start=start,
        horizon=P.inum("horizon_weeks"),
        season=season,
        cv_monthly=cv,
        outflow_monthly=outflow,
        floor=floor,
        buffer=buffer,
        home_cash0=home0,
        spare=spare,
        own_savings=float(plan.own_savings_cny),
        pot0=float(src.pot_balance_cny or 0) if isinstance(src, FeedSnapshot) else 0.0,
        lines=_lines(card),
        likely_total_sgd=float(card.total_likely_sgd),
        first_adjust_sgd=adj,
        partner_share=float(plan.partner_equity_share),
        fx0=float(card.fx_cny_per_sgd),
        loan_excess0=float(loan_excess_cny(src)) if isinstance(src, FeedSnapshot) else 0.0,
        r2_pause_weeks=r2_pause_weeks,
        available_week=avail,
        durations=tuple(P.tri(k) for k in DURATION_KEYS),
        params_version=P.version(),
    )


# ------------------------------------------------------------------ draws (cached; independent of the share)


def _calendar(inp: PlanInputs) -> tuple[I64, I64]:
    """Calendar month (0..11) and month ordinal since start, for each week."""
    days = [inp.start + timedelta(days=7 * t) for t in range(inp.horizon)]
    cal = np.array([d.month - 1 for d in days], dtype=np.int64)
    ordn = np.array(
        [(d.year - inp.start.year) * 12 + d.month - inp.start.month for d in days], dtype=np.int64
    )
    return cal, ordn


def _profit_draws(inp: PlanInputs, rng: np.random.Generator, runs: int) -> F64:
    wpm = P.weeks_per_month()
    cal, ordn = _calendar(inp)
    mean_w = np.array(inp.season, dtype=np.float64)[cal] / wpm
    phi = P.fnum("profit_level_ar_phi")
    sd_i = inp.cv_monthly * math.sqrt(1 - phi * phi)
    months = int(ordn[-1]) + 1
    eps = rng.standard_normal((runs, months)) * sd_i
    level = np.zeros((runs, months))
    for k in range(1, months):
        level[:, k] = phi * level[:, k - 1] + eps[:, k]
    weekly = rng.standard_normal((runs, inp.horizon)) * P.fnum("profit_noise_weekly_sd")
    profit = mean_w[None, :] * (1.0 + level[:, ordn] + weekly)
    p_week = P.fnum("shock_annual_prob") / 52.0
    starts = rng.random((runs, inp.horizon)) < p_week
    sev = tri_ppf(P.tri("shock_severity"), rng.random((runs, inp.horizon)))
    d = P.inum("shock_duration_weeks")
    cs = np.cumsum(np.where(starts, sev, 0.0), axis=1)
    lagged = np.zeros_like(cs)
    lagged[:, d:] = cs[:, :-d]
    shock = (cs - lagged) * (inp.mean_monthly_profit / wpm)
    out: F64 = profit - shock
    return out


def _need_draws(inp: PlanInputs, rng: np.random.Generator, runs: int) -> F64:
    over = [i for i, ln in enumerate(inp.lines) if ln.overrun]
    u = rng.random((runs, len(inp.lines)))
    if over:
        u[:, over] = copula_uniforms(rng, runs, len(over), P.fnum("cost_overrun_rho"))
    need_sgd = np.zeros((runs, 3))
    col = {"setup": 0, "first": 1, "opening": 2}
    for i, ln in enumerate(inp.lines):
        need_sgd[:, col[ln.transfer]] += tri_ppf(Tri(low=ln.low, likely=ln.likely, high=ln.high), u[:, i])
    need_sgd[:, 1] += inp.first_adjust_sgd
    fx_move = np.exp(rng.standard_normal(runs) * P.fnum("fx_annual_vol"))
    need = np.cumsum(need_sgd, axis=1) * (inp.fx0 * fx_move)[:, None] * (1.0 - inp.partner_share)
    out: F64 = np.maximum(need, 0.0)
    return out


@lru_cache(maxsize=16)
def _draws(inp: PlanInputs, runs: int, seed: int) -> Draws:
    rng = np.random.default_rng(seed)
    profit = _profit_draws(inp, rng, runs)
    dur = np.column_stack(
        [np.maximum(np.ceil(tri_ppf(t, rng.random(runs))), 1.0) for t in inp.durations]
    ).astype(np.int64)
    need = _need_draws(inp, rng, runs)
    return Draws(profit=profit, dur=dur, need=need)


def _common_draws(inp: PlanInputs, runs: int, seed: int) -> tuple[Draws, int]:
    """The first `runs` of the full run set (at least `mc_runs`), so a preview is a subset of the wall's
    runs. Returns the draws and the size of the set they were cut from (for the other streams)."""
    n = max(runs, P.inum("mc_runs"))
    full = _draws(inp, n, seed)
    if n == runs:
        return full, n
    return Draws(profit=full.profit[:runs], dur=full.dur[:runs], need=full.need[:runs]), n


def _transfer_weeks(inp: PlanInputs) -> B_:
    """The week in which each calendar month's set-aside runs: the first plan week starting in a new month
    (the instruction starts on the 1st of the month after the plan starts)."""
    _, ordn = _calendar(inp)
    out: B_ = np.zeros(inp.horizon, dtype=bool)
    out[1:] = ordn[1:] != ordn[:-1]
    return out


def monthly_amount(inp: PlanInputs, share: float) -> float:
    """The fixed monthly set-aside for a share: s x average monthly profit, rounded as the plan shows it."""
    return float(q0(dec(share * inp.mean_monthly_profit)))


def _paused(inp: PlanInputs) -> B_:
    t = np.arange(inp.horizon, dtype=np.float64)
    excess = inp.loan_excess0 * np.power(0.5, t / P.fnum("loan_excess_halflife_weeks"))
    out: B_ = (excess > P.fnum("r2_tolerance_cny")) | (t < inp.r2_pause_weeks)
    return out


# ------------------------------------------------------------------ the weekly loop


def simulate(inp: PlanInputs, share: float, runs: int, seed: int) -> SimOut:
    """Run the Monte Carlo for one set-aside share. Pure given (inputs, share, runs, seed)."""
    dr, n = _common_draws(inp, runs, seed)
    h = inp.horizon
    paused = _paused(inp)
    due = _transfer_weeks(inp)
    amount = monthly_amount(inp, share)
    d = dr.dur
    consent = d[:, 0].astype(np.float64)
    filing = consent + d[:, 1]
    registration = filing + d[:, 2]
    account = registration + d[:, 3] + d[:, 4]
    lag, fit, lic = d[:, 5], d[:, 6], d[:, 7]
    # local hiring: its own stream, so adding it leaves every other draw unchanged
    hrng = np.random.default_rng([seed, 9])
    hire = np.maximum(np.ceil(tri_ppf(P.tri("hiring_weeks"), hrng.random(n)[:runs])), 1.0)
    need_setup, need_first, need_total = dr.need[:, 0], dr.need[:, 1], dr.need[:, 2]

    cash = np.full(runs, inp.home_cash0)
    saved = np.full(runs, inp.pot0 + inp.spare + inp.own_savings)
    setup_w = np.full(runs, np.inf)
    first_w = np.full(runs, np.inf)
    sign_w = np.full(runs, np.inf)
    lic_end = np.full(runs, np.inf)
    hire_end = np.full(runs, np.inf)
    open_w = np.full(runs, np.inf)
    breach = np.zeros(runs, dtype=bool)
    out_saved = np.empty((runs, h))
    out_home = np.empty((runs, h))
    out_sa = np.zeros((runs, h))
    wout = inp.outflow_monthly / P.weeks_per_month()
    fb = inp.floor + inp.buffer
    for t in range(h):
        p = dr.profit[:, t]
        cash += p - wout
        active = np.isinf(open_w)
        if not paused[t]:
            if due[t]:
                # the signed instruction: the fixed amount, or nothing this month if it would take home
                # cash below floor + buffer
                sa = np.where(active & (cash - amount >= fb), amount, 0.0)
                cash -= sa
                saved += sa
                out_sa[:, t] = sa
            m = np.isinf(setup_w) & (account <= t) & (saved >= need_setup)
            setup_w[m] = t
            m = np.isfinite(setup_w) & np.isinf(first_w) & (saved >= need_first)
            first_w[m] = t
            sign_w[m] = np.maximum(t + lag[m], inp.available_week)
            lic_end[m] = sign_w[m] + fit[m] + lic[m]
            hire_end[m] = sign_w[m] + hire[m]
            m = np.isfinite(first_w) & active & (lic_end <= t) & (hire_end <= t) & (saved >= need_total)
            open_w[m] = t
        breach |= active & (cash < inp.floor)
        out_saved[:, t] = saved
        out_home[:, t] = cash
    weeks = {
        "lender_consent": consent,
        "odi_filing": filing,
        "bank_registration": registration,
        "incorporate": account,
        "setup_transfer": setup_w,
        "first_transfer": first_w,
        "sign_lease": sign_w,
        "fitout": sign_w + fit,
        "licence": lic_end,
        "hiring": hire_end,
        "opening": open_w,
    }
    return SimOut(
        share=share,
        weeks=weeks,
        floor_breach=breach,
        saved=out_saved,
        home=out_home,
        setaside=out_sa,
        need=dr.need,
        paused=paused,
    )


# ------------------------------------------------------------------ wall and results


def _breaches(inp: PlanInputs, share: float, runs: int, seed: int) -> int:
    return int(np.sum(simulate(inp, share, runs, seed).floor_breach))


def _risk(inp: PlanInputs, share: float, runs: int, seed: int) -> float:
    return _breaches(inp, share, runs, seed) / runs


def risk_upper(inp: PlanInputs, share: float, runs: int, seed: int) -> float:
    """The Wilson 95% upper bound on the floor risk at a share (what the wall is decided on)."""
    return wilson_upper(_breaches(inp, share, runs, seed), runs)


@lru_cache(maxsize=64)
def _wall(inp: PlanInputs, runs: int, seed: int) -> float:
    step = P.fnum("wall_step")
    limit = P.fnum("floor_risk_limit")
    n = int(round(1.0 / step))
    wall = -1.0
    for i in range(n + 1):
        s = round(i * step, 6)
        if risk_upper(inp, s, runs, seed) > limit:
            break
        wall = s
    return max(wall, 0.0)


def find_wall(inp: PlanInputs, runs: int | None = None, seed: int | None = None) -> Decimal:
    """The largest share on the slider grid (from 0 up, contiguous) whose floor risk is at most the limit
    with its Wilson 95% upper bound, so the estimate's own noise can't open the wall."""
    return dec(_wall(inp, runs or P.inum("mc_runs"), P.default_seed() if seed is None else seed))


def _q(x: F64, q: float) -> float:
    """Quantile where 'never' (inf) sorts last; returns inf if the quantile falls on a 'never' run."""
    finite = np.where(np.isfinite(x), x, NEVER)
    v = float(np.quantile(finite, q, method="higher"))
    return math.inf if v >= NEVER else v


def _week_or_none(x: float) -> int | None:
    return None if not math.isfinite(x) else int(round(x))


def summarise(inp: PlanInputs, sim: SimOut, wall: float, runs: int, seed: int) -> PlanResult:
    open_w = sim.weeks["opening"]
    med = {k: _q(v, 0.5) for k, v in sim.weeks.items()}
    milestone_weeks = {k: int(round(v)) for k, v in med.items() if math.isfinite(v)}
    cuts = [
        (milestone_weeks[k], k)
        for k in ("setup_transfer", "first_transfer", "opening")
        if k in milestone_weeks
    ]
    need_med = np.median(sim.need, axis=0)
    need_line = []
    for t in range(inp.horizon):
        v = 0.0
        for (w, _), n in zip(cuts, need_med, strict=False):
            if t >= w:
                v = float(n)
        need_line.append(round(v))
    chart = PlanChart(
        weeks=list(range(inp.horizon)),
        pot_p10=[round(v) for v in np.quantile(sim.saved, 0.10, axis=0)],
        pot_p50=[round(v) for v in np.quantile(sim.saved, 0.50, axis=0)],
        pot_p90=[round(v) for v in np.quantile(sim.saved, 0.90, axis=0)],
        need=[float(v) for v in need_line],
        home_p05=[round(v) for v in np.quantile(sim.home, 0.05, axis=0)],
        home_p50=[round(v) for v in np.quantile(sim.home, 0.50, axis=0)],
        floor=[round(inp.floor)] * inp.horizon,
        milestones=sorted((w, k) for k, w in milestone_weeks.items()),
    )
    likely_total_cny = inp.likely_total_sgd * inp.fx0
    return PlanResult(
        setaside_share=dec(sim.share),
        open_likely_week=_week_or_none(med["opening"]),
        open_p95_week=_week_or_none(_q(open_w, 0.95)),
        floor_risk=dec(float(np.mean(sim.floor_breach))),
        opened_share=dec(float(np.mean(np.isfinite(open_w)))),
        wall_share=dec(wall),
        monthly_setaside_cny=dec(monthly_amount(inp, sim.share)),
        gap_cny=q0(dec(max(likely_total_cny - inp.spare, 0.0))),
        milestone_weeks=milestone_weeks,
        chart=chart,
        runs=runs,
        seed=seed,
    )


def simulate_plan(
    src: FeedSnapshot | Profile,
    card: CostCard,
    plan: FundingPlan,
    runs: int | None = None,
    seed: int | None = None,
    start_date: date | None = None,
    *,
    unit_available_from: date | None = None,
    r2_pause_weeks: int = 0,
    share: Decimal | None = None,
) -> PlanResult:
    """The full solve (default 1,000 runs): likely and P95 opening, floor risk, bands, milestones, wall."""
    runs = runs or P.inum("mc_runs")
    seed = P.default_seed() if seed is None else seed
    inp = build_inputs(src, card, plan, start_date, unit_available_from, r2_pause_weeks)
    s = float(plan.setaside_share if share is None else share)
    wall = _wall(inp, P.inum("mc_runs"), seed)
    return summarise(inp, simulate(inp, s, runs, seed), wall, runs, seed)


def preview(
    src: FeedSnapshot | Profile,
    card: CostCard,
    plan: FundingPlan,
    share: Decimal | float,
    seed: int | None = None,
    start_date: date | None = None,
    *,
    unit_available_from: date | None = None,
) -> PlanResult:
    """Slider preview: the chart and dates from the first `mc_runs_preview` of the full solve's runs; the
    floor risk from all of them (the same runs the cached wall was judged on), so the slider never shows
    a 200-run estimate beside a wall decided on the full set."""
    seed = P.default_seed() if seed is None else seed
    inp = build_inputs(src, card, plan, start_date, unit_available_from)
    runs, full = P.inum("mc_runs_preview"), P.inum("mc_runs")
    wall = _wall(inp, full, seed)
    res = summarise(inp, simulate(inp, float(share), runs, seed), wall, runs, seed)
    risk = dec(_risk(inp, float(share), full, seed))
    return res.model_copy(update={"floor_risk": risk, "floor_risk_runs": full})


# ------------------------------------------------------------------ figures


def week_to_date(start: date, week: int) -> date:
    return start + timedelta(days=7 * week)


def week_to_month(week: int) -> int:
    """Month number counted from the start (month 1 = the first 4.345 weeks)."""
    return max(1, math.ceil(week / P.weeks_per_month()))


def plan_figures(result: PlanResult) -> list[Figure]:
    assume = ("mc_runs", "default_seed", "horizon_weeks")
    note = f"seed {result.seed}, {result.runs} runs"
    risk_note = f"seed {result.seed}, {result.floor_risk_runs or result.runs} runs; an estimate"
    wall_note = f"seed {result.seed}, {P.inum('mc_runs')} runs; Wilson 95% upper bound of the floor risk"
    f: list[Figure] = [
        derived(
            "plan.open_likely",
            "Likely opening",
            "weeks",
            result.open_likely_week,
            tool=TOOL,
            assumptions=assume,
            note=note,
        ),
        derived(
            "plan.open_p95",
            "Opening if things go badly",
            "weeks",
            result.open_p95_week,
            tool=TOOL,
            assumptions=assume,
            note=note,
        ),
        derived(
            "plan.floor_risk",
            "Chance home cash dips below the floor",
            "pct",
            result.floor_risk,
            tool=TOOL,
            assumptions=("floor_risk_limit", *assume),
            note=risk_note,
        ),
        derived(
            "plan.opened_share",
            "Share of runs that open within 3 years",
            "pct",
            result.opened_share,
            tool=TOOL,
            note=note,
        ),
        derived(
            "plan.wall",
            "Highest safe set-aside share",
            "pct",
            result.wall_share,
            tool=TOOL,
            assumptions=("floor_risk_limit", "wall_step"),
            note=wall_note,
        ),
        derived("plan.setaside_monthly", "Monthly set-aside", "CNY", result.monthly_setaside_cny, tool=TOOL),
        derived("plan.setaside_share", "Set-aside share", "pct", result.setaside_share, tool=TOOL),
        derived("plan.gap", "Funding gap", "CNY", result.gap_cny, tool=TOOL, assumptions=("fx_cny_per_sgd",)),
    ]
    for wk_id, wk in (("open_likely", result.open_likely_week), ("open_p95", result.open_p95_week)):
        f.append(
            derived(
                f"plan.{wk_id}_month",
                "Opening month (from start)",
                "months",
                None if wk is None else week_to_month(wk),
                tool=TOOL,
                note=note,
            )
        )
    return f
