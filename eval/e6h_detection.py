# ruff: noqa: E501
"""E6-heldout: the Goal Keeper's detector on a new held-out shock set, measured once (results/prereg.md addendum
2026-10-20 (7)).

    python -m eval.model_arms run e6h     # stored in results/model_arms/E6-heldout.json, not re-run by make eval

The detector (tools.detect, parameters frozen on dev seeds 0-299 by eval/e6_freeze.py) is called exactly as E6
calls it: `baseline` on the product's 26-week feed at goal start, then `check_weeks` + `cusum` on the weekly series
since the start, with onsets counted with re-arming (eval.e6_detection._onsets).
- Chains: 300 new seeds drawn from numpy seed 20261020 in [100,000, 2^31 - 1), excluding the dev seeds and E6's
  300 test chains. Goal start 2026-10-19.
- Onsets: weeks 4-40 after the start cycled over the chains in a seeded order (seed [20261020, 1]); each chain keeps
  its onset in every class (paired). Jan-Feb onsets and onset weeks that contain the 1st of a month are reported as
  subgroups (descriptive).
- Classes: no shock (false alarms over 52 weeks); ProfitShock -20% (mark), -10% and -30%; a chain-wide SalesDrop of
  6.25% of sales at all 30 shops, i.e. -20% of average profit, which moves revenue too (mark); the demo's four-shop
  -20% dip; channel shift with commission 0 at share 0.25 and 0.35 (mark: 0 additional alarms, paired); channel
  shift with commission 0.05 and 0.15 at share 0.25 (descriptive); two missing feed weeks (descriptive).
- Counting: E6's. Delay = whole weeks from the shock's first week to the first alarm at or after it, undetected
  within 26 weeks = infinite; paired extra alarm from the onset to 26 weeks after it.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

import numpy as np

from eval import common as C
from eval import e6_detection as E6
from eval.e6_freeze import DEV_SEEDS, cycled_onsets, paired_extra

SEED = 20261020
ONSET_SEED = [SEED, 1]
START = E6.START
DELAY_WINDOW = E6.DELAY_WINDOW
YEAR = E6.YEAR
TITLE = "The Goal Keeper catches real problems, not noise: held-out shock set"


def chain_seeds(n: int, seed: int = SEED) -> list[int]:
    """New seeds >= 100,000, disjoint from the dev seeds and from E6's 300 test chains."""
    taken = set(DEV_SEEDS) | E6.DEV_SEEDS | set(E6.chain_seeds(300))
    rng = np.random.default_rng(seed)
    out: list[int] = []
    while len(out) < n:
        s = int(rng.integers(100_000, 2**31 - 1))
        if s not in taken and s not in out:
            out.append(s)
    return out


def jan_feb(onset: date) -> bool:
    return onset.month in (1, 2)


def month_boundary(onset: date) -> bool:
    """The onset week contains the 1st of a month."""
    return any((onset + timedelta(days=i)).day == 1 for i in range(7))


class Chains:
    def __init__(self) -> None:
        import dataclasses

        from sim.chen import Persona

        self.long = dataclasses.replace(Persona(), weekly_weeks=40 + DELAY_WINDOW + 40)
        self._base: dict[int, Any] = {}

    def checks(self, seed: int, shocks: tuple[Any, ...], weeks: int) -> list[Any]:
        from sim.chen import Scenario, generate_chen
        from tools import detect as DT

        if seed not in self._base:  # every shock starts >= 4 weeks after the start: the feed at start is the same
            self._base[seed] = DT.baseline(generate_chen(START, Scenario(seed=seed)), START)
        now = generate_chen(START + timedelta(weeks=weeks), Scenario(seed=seed, shocks=shocks, persona=self.long))
        return DT.check_weeks(now, self._base[seed])

    def onsets(self, seed: int, shocks: tuple[Any, ...], weeks: int) -> list[date]:
        return E6._onsets(self.checks(seed, shocks, weeks))


def _median_ci(delays: list[float]) -> dict[str, Any]:
    """E6's bootstrap median CI; a bound that falls between a finite delay and "not detected" (the bootstrap's
    stand-in value averaged with a finite one) is also "not within 26 weeks"."""
    ci = E6._median_ci(delays)
    for k in ("value", "lo", "hi"):
        if isinstance(ci[k], int | float) and ci[k] > DELAY_WINDOW:
            ci[k] = "not within 26 weeks"
    return ci


def _delay_block(delays: list[float], n: int) -> dict[str, Any]:
    detected = sum(1 for d in delays if np.isfinite(d))
    return {
        "median_delay_weeks": _median_ci(delays),
        "detected_within_26w": C.wilson(detected, n),
        "detected_within_3w": C.wilson(sum(1 for d in delays if d <= 3), n),
        "delay_quartiles_finite": (
            [float(np.percentile([d for d in delays if np.isfinite(d)], q)) for q in (25, 50, 75)] if detected else None
        ),
    }


def _sub(delays: list[float], mask: list[bool]) -> dict[str, Any]:
    d = [x for x, m in zip(delays, mask, strict=True) if m]
    if not d:
        return {"n": 0}
    return {
        "n": len(d),
        "median_delay_weeks": float(np.median(d)) if np.isfinite(np.median(d)) else "not within 26 weeks",
        "detected_within_3w": C.wilson(sum(1 for x in d if x <= 3), len(d)),
    }


def evaluate(n: int = 300, seed: int = SEED, seeds: list[int] | None = None, title: str = TITLE, **_: Any) -> dict[str, Any]:
    from sim import shocks as SH

    t0 = time.time()
    ch = Chains()
    seeds = seeds if seeds is not None else chain_seeds(n, seed)
    n = len(seeds)
    weeks = cycled_onsets(n, ONSET_SEED)
    onsets_at = [START + timedelta(weeks=w) for w in weeks]
    jf = [jan_feb(o) for o in onsets_at]
    mb = [month_boundary(o) for o in onsets_at]
    metrics: dict[str, Any] = {
        "chain_seed_source": seed,
        "n_chains_per_class": n,
        "onset_weeks": [min(weeks), max(weeks)],
        "onsets_jan_feb": sum(jf),
        "onsets_month_boundary": sum(mb),
    }

    # no shock: 52 weeks for false alarms; run to the longest paired window (re-arming makes the first 52 the same)
    long_w = max(YEAR, max(weeks) + DELAY_WINDOW)
    base = [ch.onsets(s, (), long_w) for s in seeds]
    year_end = START + timedelta(weeks=YEAR)
    fa_per = [sum(1 for a in o if a < year_end) for o in base]
    fa_total = sum(fa_per)
    fapy = round(fa_total / n, 4)
    metrics["no_shock"] = {
        "alarms_total_52w": fa_total,
        "false_alerts_per_chain_year": fapy,
        "false_alerts_per_chain_year_ci": C.bootstrap_ci([float(x) for x in fa_per], stat=np.mean),
        "chains_with_any_alarm": C.wilson(sum(1 for x in fa_per if x), n),
    }

    drops: dict[str, Any] = {
        "profit_-20": lambda w: SH.profit_drop(START, w, 0.20),
        "sales_chainwide_-20": lambda w: SH.chainwide_sales_drop(START, w),
        "profit_-10": lambda w: SH.profit_drop(START, w, 0.10),
        "profit_-30": lambda w: SH.profit_drop(START, w, 0.30),
        "demo_dip_four_shops_-20_sales": lambda w: SH.demo_dip(START, after_weeks=w),
    }
    for name, build in drops.items():
        delays: list[float] = []
        pre = 0
        for s, w, on in zip(seeds, weeks, onsets_at, strict=True):
            o = ch.onsets(s, tuple(build(w)), w + DELAY_WINDOW)
            delays.append(E6._delay(o, on))
            pre += any(a < on for a in o)
        metrics[name] = {
            **_delay_block(delays, n),
            "chains_with_alarm_before_shock": C.wilson(pre, n),
            "onset_jan_feb": _sub(delays, jf),
            "onset_month_boundary": _sub(delays, mb),
            "onset_other": _sub(delays, [not (a or b) for a, b in zip(jf, mb, strict=True)]),
        }

    def paired(build: Any) -> tuple[int, list[int]]:
        extra, which = 0, []
        for i, (s, w, on) in enumerate(zip(seeds, weeks, onsets_at, strict=True)):
            to = START + timedelta(weeks=w + DELAY_WINDOW)
            o1 = ch.onsets(s, tuple(build(w)), w + DELAY_WINDOW)
            if paired_extra(o1, base[i], on, to):
                extra += 1
                which.append(s)
        return extra, which

    shifts = {
        "channel_shift_share25": lambda w: SH.channel_shift_only(START, after_weeks=w, share=0.25),
        "channel_shift_share35": lambda w: SH.channel_shift_only(START, after_weeks=w, share=0.35),
        "channel_shift_share25_commission05": lambda w: SH.channel_shift_with_commission(START, w, 0.25, 0.05),
        "channel_shift_share25_commission15": lambda w: SH.channel_shift_with_commission(START, w, 0.25, 0.15),
        "missing_two_weeks": lambda w: SH.missing_weeks(START, after_weeks=w, weeks=2),
    }
    for name, build in shifts.items():
        extra, which = paired(build)
        metrics[name] = {"chains_with_additional_alarm": C.wilson(extra, n), "example_seeds": which[:5]}

    def med(name: str) -> tuple[Any, float]:
        v = metrics[name]["median_delay_weeks"]["value"]
        return v, (v if isinstance(v, int | float) else float("inf"))

    p20, p20n = med("profit_-20")
    s20, s20n = med("sales_chainwide_-20")
    sh25 = metrics["channel_shift_share25"]["chains_with_additional_alarm"]["k"]
    sh35 = metrics["channel_shift_share35"]["chains_with_additional_alarm"]["k"]
    pass_marks = {
        "median detection delay at -20% profit, onsets weeks 4-40 (weeks)": C.mark("<= 3", p20, p20n <= 3),
        "median detection delay at -20% (chain-wide sales drop, 6.25% of sales) (weeks)": C.mark("<= 3", s20, s20n <= 3),
        "false alerts per chain-year, no-shock chains": C.mark("<= 2", fapy, fapy <= 2),
        "chains where a channel shift alone adds an alarm (share 0.25, commission 0)": C.mark("0", sh25, sh25 == 0),
        "chains where a channel shift alone adds an alarm (share 0.35, commission 0)": C.mark("0", sh35, sh35 == 0),
    }

    def dl(name: str) -> str:
        m = metrics[name]
        md = m["median_delay_weeks"]
        return (
            f"{name}: median delay {md['value']} weeks (95% CI {md['lo']}–{md['hi']}); within 3 weeks "
            f"{C.wfmt(m['detected_within_3w'])}; within 26 weeks {C.wfmt(m['detected_within_26w'])}; alarm before the "
            f"shock {C.wfmt(m['chains_with_alarm_before_shock'])}; Jan-Feb onsets ({m['onset_jan_feb']['n']}) median "
            f"{m['onset_jan_feb'].get('median_delay_weeks')}, month-boundary onsets ({m['onset_month_boundary']['n']}) "
            f"median {m['onset_month_boundary'].get('median_delay_weeks')}"
        )

    fa = metrics["no_shock"]["false_alerts_per_chain_year_ci"]
    notes = [
        "Held-out shock set (prereg addendum 2026-10-20 (7)), measured once. Simulated chains (sim.chen persona, "
        "fictional). The detector is tools.detect with k, h, lambda, lag and the shrink frozen on dev seeds 0-299 "
        "(results/detect_freeze.json) before this set existed; alarms are CUSUM onsets with re-arming, as E6.",
        f"Onsets weeks {min(weeks)}-{max(weeks)} after the goal start (2026-10-19), {sum(jf)} chains in Jan-Feb, "
        f"{sum(mb)} in a week that contains the 1st of a month.",
        *[dl(k) for k in drops],
        f"No-shock chains: {fa_total} alarms over {n} chain-years ({fapy} per chain-year, bootstrap 95% CI "
        f"{fa['lo']:.3g}–{fa['hi']:.3g}); chains with any alarm in a year {C.wfmt(metrics['no_shock']['chains_with_any_alarm'])}.",
        *[f"{k} (paired with the no-shock chain): additional alarm in {C.wfmt(metrics[k]['chains_with_additional_alarm'])}"
          + ("" if "commission" not in k else " (descriptive: a real profit fall of about "
             + ("6%" if k.endswith("05") else "19%") + ", which the guard treats as the plan's cost)")
          for k in shifts],
        "These test the detector, not the full alert rule (SPEC §7.2), so product alerts are at most this frequent.",
    ]
    return C.entry(
        "run",
        n=n * (len(drops) + len(shifts) + 1),
        title=title,
        metrics=metrics,
        pass_marks=pass_marks,
        seed=seed,
        notes=notes,
        runtime_s=time.time() - t0,
    )
