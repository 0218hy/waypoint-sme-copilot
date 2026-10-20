# ruff: noqa: E501
"""Freeze the Goal Keeper detector's parameters on dev seeds only (results/prereg.md addendum 2026-10-20 (7)).

    python -m eval.e6_freeze            # writes results/detect_freeze.json

Dev chains: seeds 0-299 (all < 100,000; E6's test chains and E6-heldout's chains are >= 100,000). E6's counting:
alarms are CUSUM onsets with re-arming; delay = whole weeks from the shock's first week to the first alarm at or
after it, undetected within 26 weeks = infinite. Dev classes: no shock (false alarms over 52 weeks); ProfitShock
-20% with onsets cycling over weeks 4-40 after the goal start (seed [20261020, 99]); channel shift (commission 0) at
share 0.25 and 0.35 on the same onsets, paired with the no-shock chain.

Rule (pre-registered): among settings with dev false alarms <= 1.7 a chain-year and 0 paired channel-shift extra
alarms, the smallest dev median delay at -20%; ties go to the larger share within 3 weeks, then fewer false alarms,
then larger h, then larger k, then shrink on. Every setting's dev numbers are written with the choice.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import time
from datetime import date, timedelta
from typing import Any

import numpy as np

from eval import common as C

START = date(2026, 10, 19)
DEV_SEEDS = list(range(300))
ONSET_SEED = [20261020, 99]
FIRST_ONSET, LAST_ONSET = 4, 40
DELAY_WINDOW = 26
YEAR = 52
FA_MAX = 1.7
GRID: dict[str, list[Any]] = {
    "k_sd": [0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
    "h_sd": [2, 3, 4, 5, 6, 8, 10],
    "lambda": [0.1, 0.2, 0.3, 0.5],
    "lag": [1, 2, 3, 4, 6],
    "shrink": [True, False],
}
OUT = C.ROOT / "results" / "detect_freeze.json"


def cycled_onsets(n: int, seed: list[int]) -> list[int]:
    """Onset weeks after the goal start: weeks 4-40 cycled over n chains (each week n/37 times), seeded order."""
    weeks = np.resize(np.arange(FIRST_ONSET, LAST_ONSET + 1), n)
    np.random.default_rng(seed).shuffle(weeks)
    return [int(w) for w in weeks]


def onsets(weeks: list[date], z: list[float], k: float, h: float) -> list[date]:
    """E6's onset counting (eval.e6_detection._onsets on tools.detect.cusum) in one pass: after an alarm the CUSUM
    restarts at 0 from the next week. `weeks`/`z` are the checked (non-missing) weeks only."""
    out: list[date] = []
    s = 0.0
    for w, zi in zip(weeks, z, strict=True):
        s = max(0.0, s + zi - k)
        if s > h:
            out.append(w)
            s = 0.0
    return out


def delay(ons: list[date], onset: date) -> float:
    after = [a for a in ons if a >= onset]
    if not after:
        return float("inf")
    w = (after[0] - onset).days // 7
    return float(w) if w <= DELAY_WINDOW else float("inf")


def paired_extra(o1: list[date], o0: list[date], frm: date, to: date) -> bool:
    """E6's rule: the shifted chain alarms more often, or earlier, than the same chain without the shift."""
    a = [x for x in o1 if frm <= x < to]
    b = [x for x in o0 if frm <= x < to]
    return len(a) > len(b) or bool(a and (not b or a[0] < b[0]))


class Feeds:
    """Feeds for one chain: at goal start, and `weeks` after it (a long weekly window so every week is visible)."""

    def __init__(self) -> None:
        from sim.chen import Persona

        self.long = dataclasses.replace(Persona(), weekly_weeks=LAST_ONSET + DELAY_WINDOW + 40)

    def at_start(self, seed: int) -> Any:
        from sim.chen import Scenario, generate_chen

        return generate_chen(START, Scenario(seed=seed))

    def now(self, seed: int, shocks: tuple[Any, ...], weeks: int) -> Any:
        from sim.chen import Scenario, generate_chen

        return generate_chen(START + timedelta(weeks=weeks), Scenario(seed=seed, shocks=shocks, persona=self.long))


def series(checks: list[Any]) -> tuple[list[date], list[float]]:
    used = [c for c in checks if not c.missing and c.ratio is not None]
    return [c.week_start for c in used], [float(c.z or 0.0) for c in used]


def main() -> int:
    from sim.shocks import ChannelShift, ProfitShock
    from tools import detect as DT

    t0 = time.time()
    fd = Feeds()
    onset_w = cycled_onsets(len(DEV_SEEDS), ONSET_SEED)
    horizon_max = LAST_ONSET + DELAY_WINDOW
    # feeds once per chain and class (they don't depend on the detector's parameters)
    feeds: list[dict[str, Any]] = []
    for s, w in zip(DEV_SEEDS, onset_w, strict=True):
        on = START + timedelta(weeks=w)
        hz = w + DELAY_WINDOW
        feeds.append({
            "start": fd.at_start(s),
            "none": fd.now(s, (), max(YEAR, horizon_max)),
            "p20": fd.now(s, (ProfitShock(start=on, pct=0.20),), hz),
            "shift25": fd.now(s, (ChannelShift(start=on, share=0.25),), hz),
            "shift35": fd.now(s, (ChannelShift(start=on, share=0.35),), hz),
            "onset": on,
            "to": START + timedelta(weeks=hz),
        })
    print(f"feeds built in {time.time() - t0:.0f} s", flush=True)
    rows: list[dict[str, Any]] = []
    year_end = START + timedelta(weeks=YEAR)
    for shrink in GRID["shrink"]:
        bases = [DT.baseline(f["start"], START, shrink=shrink) for f in feeds]
        for lam, lag in itertools.product(GRID["lambda"], GRID["lag"]):
            ser = [
                {c: series(DT.check_weeks(f[c], b, lam=lam, lag=lag)) for c in ("none", "p20", "shift25", "shift35")}
                for f, b in zip(feeds, bases, strict=True)
            ]
            for k, h in itertools.product(GRID["k_sd"], GRID["h_sd"]):
                fa = 0
                delays: list[float] = []
                extra = {"shift25": 0, "shift35": 0}
                for f, sr in zip(feeds, ser, strict=True):
                    o0 = onsets(*sr["none"], k, h)
                    fa += sum(1 for a in o0 if a < year_end)
                    delays.append(delay(onsets(*sr["p20"], k, h), f["onset"]))
                    for c in extra:
                        extra[c] += paired_extra(onsets(*sr[c], k, h), o0, f["onset"], f["to"])
                d = np.array(delays)
                rows.append({
                    "k_sd": k, "h_sd": h, "lambda": lam, "lag": lag, "shrink": shrink,
                    "false_alarms_per_chain_year": round(fa / len(feeds), 4),
                    "median_delay_p20": float(np.median(d)),
                    "within3_p20": round(float(np.mean(d <= 3)), 4),
                    "detected26_p20": round(float(np.mean(np.isfinite(d))), 4),
                    "shift25_extra": extra["shift25"],
                    "shift35_extra": extra["shift35"],
                })
        print(f"shrink={shrink} done at {time.time() - t0:.0f} s", flush=True)
    ok = [r for r in rows if r["false_alarms_per_chain_year"] <= FA_MAX and r["shift25_extra"] == 0 and r["shift35_extra"] == 0]
    ok.sort(key=lambda r: (r["median_delay_p20"], -r["within3_p20"], r["false_alarms_per_chain_year"], -r["h_sd"], -r["k_sd"], not r["shrink"]))
    chosen = ok[0] if ok else None
    out = {
        "rule": "results/prereg.md addendum 2026-10-20 (7) (and its note before the freeze: shrink on/off)",
        "dev_seeds": [DEV_SEEDS[0], DEV_SEEDS[-1]],
        "onset_seed": ONSET_SEED,
        "onset_weeks": [FIRST_ONSET, LAST_ONSET],
        "goal_start": START.isoformat(),
        "grid": GRID,
        "false_alarm_max": FA_MAX,
        "settings": len(rows),
        "eligible": len(ok),
        "chosen": chosen,
        "runner_up": ok[1:6],
        "rows": rows,
        "git_commit": C.provenance().get("git_commit"),
        "runtime_s": round(time.time() - t0, 1),
        "simulated": True,
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print("eligible", len(ok), "chosen", json.dumps(chosen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
