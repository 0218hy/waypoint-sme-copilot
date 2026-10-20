"""Choose the demo persona's seed by the rule in results/prereg.md addendum 2026-10-20 (6).

The first seed in order from 1415 for which
  (0) Chen's history has the persona's documented shape (the checks in tests/test_sim_chen.py
      test_chen_shape: a year's sales 12-14m, mean monthly profit 180-240k, every February below every
      October-December month);
  (a) the paired no-shock control (the demo journey, no scenario) raises no alert and the detector no
      alarm over the demo's window (4 checks, 16 weeks);
  (b) the run with the four-shop sales dip raises an alert within the window.
Every seed tried is written to results/demo/seed_search.json with its outcome. This is a selection for
illustration, not evidence about the detector (E6 is). Scripted, no model.

    python -m sim.demo_seed [--first 1415] [--max 200]
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from sim.demo import CHECK_WEEKS, CHECKS, OUT, Demo

FIRST = 1415


def shape_ok(seed: int) -> bool:
    from sim.chen import BASE_AS_OF, Scenario, generate_chen

    f = generate_chen(BASE_AS_OF, Scenario(seed=seed))
    sales = sum(m.revenue_cny for m in f.profit_history[-12:])
    avg = sum(m.operating_profit_cny for m in f.profit_history) / len(f.profit_history)
    feb = [m.operating_profit_cny for m in f.profit_history if m.month.month == 2]
    autumn = [m.operating_profit_cny for m in f.profit_history if m.month.month in (10, 11, 12)]
    return (
        Decimal(12_000_000) < sales < Decimal(14_000_000)
        and Decimal(180_000) < avg < Decimal(240_000)
        and max(feb) < min(autumn)
    )


def _run(seed: int, scenario: str) -> dict[str, Any]:
    from mock_webank import feed as mw

    mw.use_seed(seed)
    demo = Demo(Path(tempfile.mkdtemp(prefix=f"waypoint-seed-{seed}-")))
    goal = demo.journey()["goal"]
    checks = demo.weeks_later(scenario, stop_at_alert=scenario != "none")
    return {"goal": goal, "checks": checks}


def trial(seed: int) -> dict[str, Any]:
    row: dict[str, Any] = {"seed": seed, "shape_ok": shape_ok(seed)}
    if not row["shape_ok"]:
        row["chosen"] = False
        return row
    control = _run(seed, "none")
    c = control["checks"]
    row["control"] = {
        "alerts": c[-1]["alerts"],
        "detector_alarm": any(x["detector_alarm"] for x in c),
        "status": [x["status"] for x in c],
        "likely_week": [x["likely_week"] for x in c],
        "target_week": control["goal"]["open_likely_week"],
    }
    quiet = row["control"]["alerts"] == 0 and not row["control"]["detector_alarm"]
    dip = _run(seed, "sales_dip")
    d = dip["checks"]
    alerted = d[-1]["alerts"] > 0
    row["dip"] = {
        "alert_after_weeks": d[-1]["week"] if alerted else None,
        "detector_alarm": any(x["detector_alarm"] for x in d),
        "status": [x["status"] for x in d],
    }
    row["chosen"] = quiet and alerted
    return row


def main() -> None:
    from agent import voice

    ap = argparse.ArgumentParser()
    ap.add_argument("--first", type=int, default=FIRST)
    ap.add_argument("--max", type=int, default=200)
    args = ap.parse_args()
    voice.set_test_composer(voice.echo_composer)
    os.environ["WAYPOINT_LLM_PROVIDER"] = "none"
    os.environ["WAYPOINT_READER_REPLAY"] = "1"
    tried: list[dict[str, Any]] = []
    chosen = None
    for seed in range(args.first, args.first + args.max):
        row = trial(seed)
        tried.append(row)
        print(json.dumps(row), flush=True)
        if row["chosen"]:
            chosen = seed
            break
    shaped = [r for r in tried if r["shape_ok"]]
    out = {
        "rule": "results/prereg.md addendum 2026-10-20 (6)",
        "window": {"checks": CHECKS, "weeks_apart": CHECK_WEEKS},
        "chosen": chosen,
        "summary": {
            "tried": len(tried),
            "shape_ok": len(shaped),
            "control_alerted": sum(1 for r in shaped if r["control"]["alerts"] > 0),
            "control_detector_alarm": sum(1 for r in shaped if r["control"]["detector_alarm"]),
            "dip_no_alert_in_window": sum(1 for r in shaped if r["dip"]["alert_after_weeks"] is None),
        },
        "tried": tried,
        "simulated": True,
        "model": "none (scripted)",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "seed_search.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out["summary"]), "chosen:", chosen)


if __name__ == "__main__":
    main()
