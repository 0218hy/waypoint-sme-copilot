"""Run every pre-registered evaluation that can run in this build, in prereg order, and write
results/results.json and results/RESULTS.md (`make eval`).

Evaluations needing a model or outside participants are listed as not run with the prereg's reasons.
Everything is simulated (fictional company, mocked WeBank feed, simulated units, scripted owners).
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from collections.abc import Callable
from typing import Any

from eval import common as C

NOT_RUN = {
    "E1b": (
        "Simulated owners with a model in the loop (LLM user simulator)",
        "Needs a configured model (and simulator, judge and agent from three model families); no model is "
        "configured in this build (results/prereg.md).",
    ),
    "E2-model": (
        "Every delivered quantity is grounded, with a model writing the messages",
        "E2 ran with the deterministic test composer (no model). The same check with a model composing "
        "needs a configured model; none is configured in this build.",
    ),
    "E5-model": (
        "Documents are only data: the model-mode reader arm",
        "Needs a configured vision model for the quarantined reader; no model is configured in this "
        "build (results/prereg.md).",
    ),
    "E7": (
        "Easier than a dashboard (SUS, chat vs form)",
        "No participants recruited yet (results/prereg.md: 8-12 people; SUS >= 75 when run).",
    ),
}


def _safe(key: str, title: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    t0 = time.time()
    try:
        e = fn()
    except Exception as exc:  # noqa: BLE001 - an eval that crashes is reported, not hidden
        traceback.print_exc()
        return C.entry(
            "not_run",
            title=title,
            reason=f"the evaluation code crashed: {type(exc).__name__}: {exc}",
            runtime_s=time.time() - t0,
        )
    print(f"{key}: done in {time.time() - t0:.1f} s", flush=True)
    return e


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--quick", action="store_true", help="tiny sample sizes (smoke run; results not for reporting)"
    )
    ap.add_argument("--no-write", action="store_true", help="don't write results/")
    args = ap.parse_args(argv)
    t0 = time.time()
    work = C.setup_env()
    from agent import llm

    if llm.model_label() not in ("off", "test-model"):
        print(f"note: a model is configured ({llm.model_label()}); this harness still runs the no-model arms")

    from eval import e1a_journey, e2_grounding, e3_skills, e4_guard, e5_documents, e6_detection, e8_perf

    q = args.quick
    evals: dict[str, dict[str, Any]] = {}

    payload: dict[str, Any] = {}

    def e1a() -> dict[str, Any]:
        s = time.time()
        rec = e2_grounding.Recorder()
        payload.update(e1a_journey.run(n=6 if q else 60, workdir=work, recorder=rec))
        return e1a_journey.evaluate(payload, runtime_s=time.time() - s)

    evals["E1a"] = _safe("E1a", "Scripted simulated owners reach a confirmed goal", e1a)
    evals["E1b"] = C.entry("not_run", title=NOT_RUN["E1b"][0], reason=NOT_RUN["E1b"][1], seed=None)
    evals["E2"] = _safe(
        "E2", "Every delivered quantity is grounded", lambda: e2_grounding.evaluate(payload or None)
    )
    evals["E2-model"] = C.entry(
        "not_run", title=NOT_RUN["E2-model"][0], reason=NOT_RUN["E2-model"][1], seed=None
    )
    evals["E3"] = _safe(
        "E3", "Skills hold", lambda: e3_skills.evaluate(per_class=3 if q else 45, workdir=work)
    )
    evals["E4"] = _safe(
        "E4",
        "The guard holds under pressure (keyword baseline, no model)",
        lambda: e4_guard.evaluate(n_per_class=2 if q else 30, n_controls=4 if q else None, workdir=work),
    )
    evals["E5"] = _safe(
        "E5",
        "Documents are only data (replay reader)",
        lambda: e5_documents.evaluate(n=5 if q else 240, workdir=work),
    )
    evals["E5-model"] = C.entry(
        "not_run", title=NOT_RUN["E5-model"][0], reason=NOT_RUN["E5-model"][1], seed=None
    )
    evals["E6"] = _safe(
        "E6",
        "The Goal Keeper catches real problems, not noise",
        lambda: e6_detection.evaluate(n=10 if q else 300),
    )
    evals["E7"] = C.entry("not_run", title=NOT_RUN["E7"][0], reason=NOT_RUN["E7"][1], seed=None)
    evals["E8"] = _safe(
        "E8",
        "Fast and reproducible",
        lambda: e8_perf.evaluate(n_preview=5, n_full=2, n_repeat=2) if q else e8_perf.evaluate(),
    )
    # a model arm measured by eval.model_arms is kept, not overwritten with "not run"
    from eval import model_arms

    for key, entry in model_arms.measured().items():
        if evals.get(key, {}).get("status") in (None, "not_run"):
            evals[key] = entry
    runtime = time.time() - t0
    if q:
        for e in evals.values():
            e["notes"] = ["QUICK SMOKE RUN: tiny samples, not a result.", *e.get("notes", [])]
    if args.no_write:
        for k, e in evals.items():
            print(k, e["status"], {n: (m["value"], m["pass"]) for n, m in e.get("pass_marks", {}).items()})
        return 0
    results = C.write_results(evals)
    text = C.render_markdown(results, runtime_s=runtime)
    print(text)
    print(f"\nwrote {C.RESULTS_JSON} and {C.RESULTS_MD} in {runtime:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
