# ruff: noqa: E501
"""E6: the Goal Keeper catches real problems, not noise (results/prereg.md, SPEC §7.2).

Pre-registered: synthetic chains (`sim.chen`, seeded) with injected shocks: -10/-20/-30% profit, the demo's
four-shop sales drop (two shops before the persona grew to 30), a channel shift only, missing feed weeks, an above-normal draw; 300 chains per class.
Pass marks: median detection delay <= 3 weeks at -20%; <= 2 false alerts a year on no-shock chains;
0 alerts from a channel shift alone; R2 pause raised on every above-normal draw.

How it is measured (the Goal Keeper's own detector, called directly):
- `tools.detect.baseline` on the feed at goal start (the product's 26-week feed), then
  `tools.detect.check_weeks` + `tools.detect.cusum` on the weekly series since the start. The weekly
  values are identical to the product feed's; only the window is longer (the persona's `weekly_weeks` is
  raised so a whole year since the start is visible; checked equal on overlapping weeks).
- Alarms are counted as CUSUM onsets: after an alarm the detector is re-armed from the next week (same
  baseline). This is the standard run-length view of a CUSUM; the product keeps the alarm raised instead.
- Chains: the same 300 chain seeds (drawn from seed 20261019, disjoint from the dev seeds 0-39 and 1414
  used to set h) are used in every class, so the channel-shift and missing-week classes are paired with
  the no-shock class.
- Shock onset: week 8 after the goal start (sim.shocks defaults) for profit drops, the demo dip and the
  channel shift; missing weeks at week 6 for 2 weeks; the above-normal draw on a seeded week 2-20 (so it
  falls in different calendar months; the normal borrowing level is seasonal).
- Detection delay = whole weeks from the shock's first week to the alarm week, within 26 weeks of the
  onset; an undetected chain counts as "not within 26 weeks" (infinite delay) in the median.
- False alerts per chain-year: onsets over 52 weeks on no-shock chains.
- Channel shift alone: a chain counts if, after the shift starts, the shifted chain alarms more often, or
  earlier, than the same chain without the shift.
- R2: `tools.funding.r2_paused` on the feed at the first weekly check after the draw (draw date + 7 days).
"""

from __future__ import annotations

import dataclasses
import time
from datetime import date, timedelta
from typing import Any

import numpy as np

from eval import common as C

START = date(2026, 10, 19)
DEV_SEEDS = set(range(40)) | {1414}
ONSET_WEEKS = 8
DELAY_WINDOW = 26
YEAR = 52


def chain_seeds(n: int, seed: int = C.SEED) -> list[int]:
    rng = np.random.default_rng(seed)
    out: list[int] = []
    while len(out) < n:
        s = int(rng.integers(100_000, 2**31 - 1))
        if s not in DEV_SEEDS and s not in out:
            out.append(s)
    return out


def _onsets(checks: list[Any]) -> list[date]:
    from tools import detect as DT

    out: list[date] = []
    i = 0
    while i < len(checks):
        d = DT.cusum(checks[i:])
        if not d.alarm or d.alarm_week is None:
            break
        out.append(d.alarm_week)
        j = next(k for k in range(i, len(checks)) if checks[k].week_start == d.alarm_week)
        i = j + 1
    return out


class Chains:
    def __init__(self) -> None:
        from sim.chen import Persona

        self.long = dataclasses.replace(Persona(), weekly_weeks=YEAR + 30)

    def checks(self, seed: int, shocks: tuple[Any, ...], weeks: int) -> list[Any]:
        from sim.chen import Scenario, generate_chen
        from tools import detect as DT

        at_start = generate_chen(START, Scenario(seed=seed, shocks=shocks))
        base = DT.baseline(at_start, START)
        now = generate_chen(
            START + timedelta(weeks=weeks), Scenario(seed=seed, shocks=shocks, persona=self.long)
        )
        return DT.check_weeks(now, base)

    def onsets(self, seed: int, shocks: tuple[Any, ...], weeks: int) -> list[date]:
        return _onsets(self.checks(seed, shocks, weeks))


def _delay(onsets: list[date], onset: date) -> float:
    after = [a for a in onsets if a >= onset]
    if not after:
        return float("inf")
    w = (after[0] - onset).days // 7
    return float(w) if w <= DELAY_WINDOW else float("inf")


def _median_ci(delays: list[float]) -> dict[str, Any]:
    finite_cap = 10_000.0  # stands for "not detected within the window" in the bootstrap
    vals = [d if np.isfinite(d) else finite_cap for d in delays]
    ci = C.bootstrap_ci(vals)
    for k in ("value", "lo", "hi"):
        if ci[k] is not None and ci[k] >= finite_cap:
            ci[k] = "not within 26 weeks"
    return ci


def evaluate(n: int = 300, seed: int = C.SEED) -> dict[str, Any]:
    from sim.shocks import (
        ChannelShift,
        MissingFeed,
        ProfitShock,
        SalesDrop,
        above_normal_draw,
    )
    from tools import funding as F

    t0 = time.time()
    ch = Chains()
    seeds = chain_seeds(n, seed)
    onset = START + timedelta(weeks=ONSET_WEEKS)
    horizon = ONSET_WEEKS + DELAY_WINDOW
    metrics: dict[str, Any] = {"chain_seed_source": seed, "n_chains_per_class": n}

    # no-shock chains: a year, plus the paired window used by the shift / missing classes
    base_year = [ch.onsets(s, (), YEAR) for s in seeds]
    base_h = [[a for a in o if a < START + timedelta(weeks=horizon)] for o in base_year]
    false_total = sum(len(o) for o in base_year)
    per_chain_year = [len(o) * 52 / YEAR for o in base_year]
    fa = C.bootstrap_ci(per_chain_year, stat=np.mean)
    metrics["no_shock"] = {
        "alarms_total_52w": false_total,
        "false_alerts_per_chain_year": round(false_total / n * 52 / YEAR, 4),
        "false_alerts_per_chain_year_ci": fa,
        "chains_with_any_alarm": C.wilson(sum(1 for o in base_year if o), n),
    }

    # profit drops and the demo dip
    classes: dict[str, tuple[Any, ...]] = {
        "profit_-10": (ProfitShock(start=onset, pct=0.10),),
        "profit_-20": (ProfitShock(start=onset, pct=0.20),),
        "profit_-30": (ProfitShock(start=onset, pct=0.30),),
        "demo_dip_four_shops_-20_sales": (SalesDrop(start=onset, shops=4, pct=0.20),),
    }
    delays_by: dict[str, list[float]] = {}
    for name, shocks in classes.items():
        ons = [ch.onsets(s, shocks, horizon) for s in seeds]
        delays = [_delay(o, onset) for o in ons]
        delays_by[name] = delays
        pre = sum(1 for o in ons if any(a < onset for a in o))
        within3 = sum(1 for d in delays if d <= 3)
        detected = sum(1 for d in delays if np.isfinite(d))
        metrics[name] = {
            "median_delay_weeks": _median_ci(delays),
            "detected_within_26w": C.wilson(detected, n),
            "detected_within_3w": C.wilson(within3, n),
            "chains_with_alarm_before_shock": C.wilson(pre, n),
            "delay_quartiles_finite": (
                [float(np.percentile([d for d in delays if np.isfinite(d)], q)) for q in (25, 50, 75)]
                if detected
                else None
            ),
        }

    # channel shift only, paired with the no-shock chain
    def paired_extra(shocks: tuple[Any, ...], from_date: date) -> tuple[int, list[int]]:
        extra, which = 0, []
        for i, s in enumerate(seeds):
            o1 = [a for a in ch.onsets(s, shocks, horizon) if a >= from_date]
            o0 = [a for a in base_h[i] if a >= from_date]
            if len(o1) > len(o0) or (o1 and (not o0 or o1[0] < o0[0])):
                extra += 1
                which.append(s)
        return extra, which

    shift = (ChannelShift(start=onset, share=0.25),)
    shift_extra, shift_seeds = paired_extra(shift, onset)
    shift35 = (ChannelShift(start=onset, share=0.35),)
    shift35_extra, _ = paired_extra(shift35, onset)
    metrics["channel_shift_only"] = {
        "chains_with_additional_alarm_share25": C.wilson(shift_extra, n),
        "chains_with_additional_alarm_share35": C.wilson(shift35_extra, n),
        "example_seeds": shift_seeds[:5],
    }
    miss_start = START + timedelta(weeks=6)
    missing = (MissingFeed(start=miss_start, end=miss_start + timedelta(weeks=2)),)
    miss_extra, _ = paired_extra(missing, miss_start)
    metrics["missing_weeks"] = {"chains_with_additional_alarm": C.wilson(miss_extra, n)}

    # above-normal draw: R2 at the first weekly check after it
    rng = np.random.default_rng([seed, 6])
    draw_weeks = rng.integers(2, 21, size=n)
    raised, base_raised = 0, 0
    from sim.chen import Scenario, generate_chen

    for s, w in zip(seeds, draw_weeks, strict=True):
        shocks = tuple(above_normal_draw(START, after_weeks=int(w)))
        check_on = START + timedelta(weeks=int(w)) + timedelta(days=7)
        if F.r2_paused(generate_chen(check_on, Scenario(seed=s, shocks=shocks))):
            raised += 1
        if F.r2_paused(generate_chen(check_on, Scenario(seed=s))):
            base_raised += 1
    metrics["above_normal_draw"] = {
        "r2_raised": C.wilson(raised, n),
        "r2_raised_same_date_without_draw": C.wilson(base_raised, n),
        "draw_weeks_range": [int(draw_weeks.min()), int(draw_weeks.max())],
    }

    d20 = metrics["profit_-20"]["median_delay_weeks"]["value"]
    d20_num = d20 if isinstance(d20, int | float) else float("inf")
    fapy = metrics["no_shock"]["false_alerts_per_chain_year"]
    pass_marks = {
        "median detection delay at -20% profit (weeks)": C.mark("<= 3", d20, d20_num <= 3),
        "false alerts per chain-year, no-shock chains": C.mark("<= 2", fapy, fapy <= 2),
        "chains where a channel shift alone adds an alarm": C.mark("0", shift_extra, shift_extra == 0),
        "R2 pause raised on above-normal draws": C.mark(f"{n}/{n}", f"{raised}/{n}", raised == n),
    }

    def dl(name: str) -> str:
        m = metrics[name]
        med = m["median_delay_weeks"]
        return (
            f"{name}: median delay {med['value']} weeks (95% CI {med['lo']}–{med['hi']}); "
            f"detected within 3 weeks {C.wfmt(m['detected_within_3w'])}; within 26 weeks "
            f"{C.wfmt(m['detected_within_26w'])}; alarm before the shock {C.wfmt(m['chains_with_alarm_before_shock'])}"
        )

    notes = [
        "Simulated chains (sim.chen persona, fictional). The detector is tools.detect (the Goal Keeper's), called "
        "directly; alarms are counted as CUSUM onsets with re-arming after each alarm.",
        *[dl(k) for k in classes],
        f"No-shock chains: {false_total} alarms over {n} chain-years "
        f"({fapy} per chain-year, bootstrap 95% CI {fa['lo']:.3g}–{fa['hi']:.3g}); chains with any alarm in a "
        f"year {C.wfmt(metrics['no_shock']['chains_with_any_alarm'])}.",
        f"Channel shift alone (25% of in-store sales to delivery, paired): additional alarm in "
        f"{C.wfmt(metrics['channel_shift_only']['chains_with_additional_alarm_share25'])}; at a 35% shift "
        f"{C.wfmt(metrics['channel_shift_only']['chains_with_additional_alarm_share35'])} (descriptive).",
        f"Missing feed weeks (2 weeks, paired): additional alarm in {C.wfmt(metrics['missing_weeks']['chains_with_additional_alarm'])} (descriptive).",
        f"Above-normal draw (RMB 400k on a seeded week 2-20): R2 pause raised {C.wfmt(metrics['above_normal_draw']['r2_raised'])}; "
        f"the same check without the draw raised it in {C.wfmt(metrics['above_normal_draw']['r2_raised_same_date_without_draw'])}.",
        "These test the detector, not the full alert rule: the Goal Keeper alerts only when the re-planned "
        "status worsens or the date moves >= 2 weeks (SPEC §7.2), so product alerts are at most this frequent.",
    ]
    return C.entry(
        "run",
        n=n * (len(classes) + 4),
        title="The Goal Keeper catches real problems, not noise",
        metrics=metrics,
        pass_marks=pass_marks,
        seed=seed,
        notes=notes,
        runtime_s=time.time() - t0,
    )


if __name__ == "__main__":
    import json

    print(json.dumps(evaluate(), indent=2, default=str))
