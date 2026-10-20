# ruff: noqa: E501
"""E8: fast and reproducible (results/prereg.md, SPEC §6.6).

Pre-registered: timing on the build machine; repeated seeded runs. 50 preview calls, 10 full solves, 5
repeated runs. Pass marks: slider preview p95 < 300 ms; full simulate < 5 s; identical outputs for the
same seed.

How it is measured:
- Inputs: the simulated owner's feed, the cost card for the demo unit (standard fit-out, local manager,
  no quotes) and the default funding plan, built with the same tools the journey uses.
- Preview: 50 calls of `tools.plan.preview` at 50 slider positions (0-100%). As in the product, the slider
  appears only after the full solve, so the full-run wall is already cached; the first (cold) preview is
  reported separately.
- Full solve: 10 calls of `tools.plan.simulate_plan`, each with the draw and wall caches cleared first
  (cold, the slowest case). "Full simulate < 5 s" is judged on the slowest of the 10.
- Reproducibility: 5 cold runs of `simulate_plan` with the default seed must give identical results, and
  5 runs of the preview at one share likewise.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any

import numpy as np

from eval import common as C


def inputs() -> tuple[Any, Any, Any, Any, Any]:
    from datetime import date

    from agent import toolkit as tk
    from mock_webank import feed as mw
    from tools import costs as CO
    from tools import data as D
    from tools.models import FundingPlan, Profile

    start = date(2026, 10, 19)
    feed = mw.get_feed("eval-e8", start)
    unit = D.unit_by_id("u-tm-01")
    profile = tk.profile_from_feed(feed)
    profile = tk.complete_profile(profile) if isinstance(profile, Profile) else profile
    card = tk.estimate(unit, profile, "standard", "hire_local", [], {})
    plan = FundingPlan()
    _ = CO  # imported for clarity: estimate wraps tools.costs
    return feed, card, plan, start, unit.available_from


def _clear() -> None:
    from tools import plan as PL

    PL._wall.cache_clear()
    PL._draws.cache_clear()


def _dump(res: Any) -> str:
    return json.dumps(res.model_dump(mode="json"), sort_keys=True, default=str)


def evaluate(n_preview: int = 50, n_full: int = 10, n_repeat: int = 5) -> dict[str, Any]:
    from tools import plan as PL

    t0 = time.time()
    feed, card, plan, start, avail = inputs()
    kw = {"start_date": start, "unit_available_from": avail}

    # full solves, cold
    full_s: list[float] = []
    for _ in range(n_full):
        _clear()
        a = time.perf_counter()
        PL.simulate_plan(feed, card, plan, **kw)
        full_s.append(time.perf_counter() - a)

    # previews: first one cold, then the 50 measured with the wall cached (product order)
    _clear()
    a = time.perf_counter()
    PL.preview(feed, card, plan, Decimal("0.40"), **kw)
    cold_preview = time.perf_counter() - a
    _clear()
    PL.simulate_plan(feed, card, plan, **kw)
    shares = [round(i / max(n_preview - 1, 1), 4) for i in range(n_preview)]
    prev_ms: list[float] = []
    for s in shares:
        a = time.perf_counter()
        PL.preview(feed, card, plan, Decimal(str(s)), **kw)
        prev_ms.append(1000 * (time.perf_counter() - a))

    # reproducibility
    runs = []
    for _ in range(n_repeat):
        _clear()
        runs.append(_dump(PL.simulate_plan(feed, card, plan, **kw)))
    prev_runs = [_dump(PL.preview(feed, card, plan, Decimal("0.35"), **kw)) for _ in range(n_repeat)]
    identical = len(set(runs)) == 1 and len(set(prev_runs)) == 1

    p95 = float(np.percentile(prev_ms, 95))
    p95_ci = C.bootstrap_ci(prev_ms, stat=lambda x: float(np.percentile(x, 95)))
    worst_full = max(full_s)
    metrics = {
        "preview_ms": {
            "p50": float(np.percentile(prev_ms, 50)),
            "p95": p95,
            "p95_bootstrap_ci": p95_ci,
            "max": max(prev_ms),
            "n": len(prev_ms),
        },
        "preview_cold_ms": 1000 * cold_preview,
        "full_solve_s": {
            "median": float(np.median(full_s)),
            "max": worst_full,
            "all": [round(x, 4) for x in full_s],
            "n": len(full_s),
        },
        "repeat_runs": {"n": n_repeat, "identical": identical, "distinct_full": len(set(runs))},
        "mc_runs": PL.P.inum("mc_runs"),
        "mc_runs_preview": PL.P.inum("mc_runs_preview"),
        "seed": PL.P.default_seed(),
    }
    notes = [
        f"Build machine timing. Preview p50 {metrics['preview_ms']['p50']:.1f} ms, p95 {p95:.1f} ms "
        f"(bootstrap 95% CI {p95_ci['lo']:.1f}–{p95_ci['hi']:.1f}), max {metrics['preview_ms']['max']:.1f} ms over "
        f"{len(prev_ms)} slider positions with the wall cached; the first, cold preview took "
        f"{metrics['preview_cold_ms']:.0f} ms.",
        f"Full solve ({metrics['mc_runs']} runs, caches cleared each time): median {metrics['full_solve_s']['median']:.2f} s, "
        f"slowest {worst_full:.2f} s over {len(full_s)} calls.",
        f"{n_repeat} repeated cold runs with seed {metrics['seed']}: "
        + ("identical." if identical else f"NOT identical ({len(set(runs))} distinct full results)."),
    ]
    return C.entry(
        "run",
        n=n_preview + n_full + n_repeat,
        title="Fast and reproducible",
        metrics=metrics,
        pass_marks={
            "slider preview p95 (ms)": C.mark("< 300", round(p95, 1), p95 < 300),
            "full simulate, slowest of 10 (s)": C.mark("< 5", round(worst_full, 3), worst_full < 5),
            "identical outputs for the same seed": C.mark("identical", identical, identical),
        },
        seed=int(metrics["seed"]),
        notes=notes,
        runtime_s=time.time() - t0,
    )


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2, default=str))
