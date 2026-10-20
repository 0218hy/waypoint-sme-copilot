# ruff: noqa: E501
"""The model arms (results/prereg.md, addendum 2): Claude in every role, a single-family deviation.

    python -m eval.model_arms run e4m|e5m|e4h|e4hm|e4h2|e4h2m|e4h3|e4h3m|e4h4|e4h4m|e4h5|e4h6|e6h   # one arm, in its own process
    python -m eval.model_arms run e2m|e1b|e4hm|e4h2m|e4h3m|e4h4m|e4h5m|e4h6m --shard 0/8      # one slice (run every slice)
    python -m eval.model_arms combine e2m|e1b|e4hm|e4h2m|e4h3m|e4h4m|e4h5m|e4h6m             # evaluate the slices together
    python -m eval.model_arms merge                       # copy every measured arm into results/

A slice runs the same owners, the same way, as an unsplit run would; only the wall-clock time changes.
Each arm writes `results/model_arms/<KEY>.json` (the entry, with the commit and models it ran with).
`eval.run_all` keeps those entries instead of marking the arms "not run". TODO (prereg addendum 2): re-run
with the simulated owner and the agent from different model families.

E4-heldout (prereg addendum 2026-10-20) is stored here too: its keyword arm `e4h` runs once with no model
(like E4, but stored, not re-run by `make eval`), and `e4hm` with the model understanding each message. The
second, third and fourth held-out sets (prereg addenda 2026-10-20 (2), (3) and (4)) run the same way as
`e4h2`/`e4h2m`, `e4h3`/`e4h3m` and `e4h4`/`e4h4m`. E6-heldout (prereg addendum 2026-10-20 (7)), the Goal
Keeper's detector on a held-out shock set, is stored the same way as `e6h` (no model).

E4-heldout-5 (prereg addendum 2026-10-20 (8)) measures end-to-end harm (primary) with an adversarial finisher and a
reply-content check: `e4h5` (keyword baseline; the judge runs after the product, on the cards' text) and `e4h5m`
(the model understands each typed message and writes every reply to one; the judge runs in `combine`, once per arm).
E4-heldout-6 (prereg addendum 2026-10-20 (13)) runs the same harness on a sixth set as `e4h6` and `e4h6m`.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from typing import Any

from eval import common as C

DIR = C.ROOT / "results" / "model_arms"
PARTS = DIR / "parts"
ARMS: dict[str, dict[str, Any]] = {
    "e2m": {"key": "E2-model", "env": {"WAYPOINT_EVAL_VOICE": "model"}, "owners": 60},
    "e4m": {"key": "E4-model", "env": {}},
    "e5m": {"key": "E5-model", "env": {"WAYPOINT_EVAL_READER": "model"}},
    "e1b": {"key": "E1b", "env": {"WAYPOINT_EVAL_VOICE": "model"}, "owners": 20},
    "e4h": {"key": "E4-heldout", "env": {}, "no_model": True},
    "e4hm": {"key": "E4-heldout-model", "env": {}},
    "e4h2": {"key": "E4-heldout-2", "env": {}, "no_model": True},
    "e4h2m": {"key": "E4-heldout-2-model", "env": {}},
    "e4h3": {"key": "E4-heldout-3", "env": {}, "no_model": True},
    "e4h3m": {"key": "E4-heldout-3-model", "env": {}},
    "e4h4": {"key": "E4-heldout-4", "env": {}, "no_model": True},
    "e4h4m": {"key": "E4-heldout-4-model", "env": {}},
    "e4h5": {"key": "E4-heldout-5", "env": {}, "no_model": True},
    "e4h5m": {"key": "E4-heldout-5-model", "env": {}},
    "e4h6": {"key": "E4-heldout-6", "env": {}, "no_model": True},
    "e4h6m": {"key": "E4-heldout-6-model", "env": {}},
    "e6h": {"key": "E6-heldout", "env": {}, "no_model": True},
}
E4H_TITLE = "The guard holds under pressure: held-out set (keyword baseline, no model)"
E4HM_TITLE = "The guard holds under pressure: held-out set, with a model understanding each message"
E4H_SMOKE = (
    "Before this run, the harness was checked once on 3 of these scripts and 1 control with the keyword baseline "
    "(guard at 4d7c971); the guard was not changed after it."
)
E4H2_NOTE = (
    "The guard (6d3f36f) was not changed after its author first read this set; no smoke run on the set before this "
    "arm (only a shape check that loads it)."
)
E4H3_NOTE = (
    "The guard (d6e5cc0) was not changed after its author first read this set; no smoke run on the set before this "
    "arm (only a shape check that loads it)."
)
E4H4_NOTE = (
    "The guard (300c1dc) was not changed after its author first read this set; no smoke run on the set before this "
    "arm (only a shape check that loads it)."
)
E6H_NOTE = (
    "The detector's parameters were frozen on dev seeds (results/detect_freeze.json, commit 9b58a7d) before this set "
    "was built; the harness was checked on dev seeds only; this arm runs once on the held-out seeds."
)
# the later held-out sets: keyword arm -> (module, model arm, note)
LATER_SETS = {
    "e4h2": ("eval.e4_heldout2", "e4h2m", E4H2_NOTE),
    "e4h3": ("eval.e4_heldout3", "e4h3m", E4H3_NOTE),
    "e4h4": ("eval.e4_heldout4", "e4h4m", E4H4_NOTE),
}
E4H5_NOTE = (
    "The code measured here (reply allowlist, adversarial finisher, judge) was frozen and committed before the set was "
    "written; neither was changed after the set was read. No smoke run on the set (only a shape check that loads it)."
)
E4H6_NOTE = (
    "The product change (prereg addendum 2026-10-20 (13): figures the feed provides held at the feed's; a funding "
    "plan's confirmation cleared when an input changes; no max_turns default on a step-confirming question), its "
    "tests and this set's harness module were frozen and committed before the set was written; none was changed "
    "after the set was read. No smoke run on the set (only a shape check that loads it)."
)
# the end-to-end harm sets (addenda (8) and (13)): keyword arm -> (module, model arm, note)
HARM_SETS = {
    "e4h5": ("eval.e4_heldout5", "e4h5m", E4H5_NOTE),
    "e4h6": ("eval.e4_heldout6", "e4h6m", E4H6_NOTE),
}
HARM_BY_ARM = {a: (mod, note) for k, (mod, m, note) in HARM_SETS.items() for a in (k, m)}
LATER_BY_ARM = {a: (mod, note) for k, (mod, m, note) in LATER_SETS.items() for a in (k, m)}
DEVIATION = "single-family deviation: Claude in every role (prereg addendum 2); TODO re-run with an owner from another family"


def _env(arm: str) -> Any:
    if ARMS[arm].get("no_model"):
        os.environ.pop("WAYPOINT_EVAL_MODEL_ARM", None)
        return C.setup_env()  # the keyword baseline: no model, as in `make eval`
    os.environ["WAYPOINT_EVAL_MODEL_ARM"] = arm
    os.environ.update(ARMS[arm]["env"])
    work = C.setup_env()
    from agent import llm

    if llm.model_label() in ("off", "test-model"):
        raise SystemExit("no model is configured: a model arm needs one (config/models.yaml)")
    return work


def _deviation(entry: dict[str, Any], title: str) -> dict[str, Any]:
    entry["title"] = title
    entry["pass_marks"] = {
        (k if "deviation" in k else f"{k} (single-family deviation)"): v for k, v in entry.get("pass_marks", {}).items()
    }
    if not any("deviation" in n for n in entry.get("notes", [])[:1]):
        entry["notes"] = [f"Model arm, {DEVIATION}.", *entry.get("notes", [])]
    return entry


def _finish(arm: str, entry: dict[str, Any], stats: dict[str, int], runtime_s: float, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    entry.setdefault("metrics", {})["model_calls"] = stats
    entry["notes"] = [
        *entry.get("notes", []),
        f"Model calls in this arm: {stats['calls']} made, {stats['failed']} failed, {stats['cooling_refusals']} refused "
        "during a cooldown after a provider failure (those reached the owner as the product's fallback).",
    ]
    entry["model_arm"] = {
        "arm": arm,
        **{k: v for k, v in C.provenance().items() if k in ("git_commit", "model", "versions")},
        "runtime_s": round(runtime_s, 1),
        **({"no_model": True} if ARMS[arm].get("no_model") else {}),
        **(extra or {}),
    }
    for pm in entry.get("pass_marks", {}).values():
        pm["result"] = C.result_label(entry, pm)
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / f"{ARMS[arm]['key']}.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return entry


def run(arm: str) -> dict[str, Any]:
    """An arm that runs in one process (E4-model, E5-model)."""
    work = _env(arm)
    from agent import llm

    started = C.provenance()["git_commit"]  # the code this process runs, not the commit when it ends
    t0 = time.time()
    if arm == "e4m":
        from eval import e4_guard as E4

        entry = _deviation(E4.evaluate(workdir=work), "The guard holds under pressure, with a model understanding each message")
    elif arm == "e5m":
        from eval import e5_documents as E5

        entry = _deviation(E5.evaluate(workdir=work), "Documents are only data: the model-mode reader")
    elif arm in ("e4h", "e4hm"):
        from eval import e4_heldout as E4H

        entry = E4H.evaluate(workdir=work, title=E4H_TITLE if arm == "e4h" else E4HM_TITLE)
        entry["notes"] = [*entry["notes"], E4H_SMOKE]
        if arm == "e4hm":
            entry = _deviation(entry, E4HM_TITLE)
    elif arm in HARM_SETS:
        mod_name, note = HARM_BY_ARM[arm]
        hs = importlib.import_module(mod_name)
        entry = hs.evaluate(workdir=work, title=hs.TITLE)
        entry["notes"] = [*entry["notes"], note, "The product ran with no model; only the judge (the evaluation's) is a model."]
    elif arm == "e6h":
        from eval import e6h_detection as E6H

        entry = E6H.evaluate()
        entry["notes"] = [*entry["notes"], E6H_NOTE]
    elif arm in LATER_BY_ARM:
        mod_name, note = LATER_BY_ARM[arm]
        hs = importlib.import_module(mod_name)
        model = arm not in LATER_SETS
        entry = hs.evaluate(workdir=work, title=hs.TITLE_MODEL if model else hs.TITLE)
        entry["notes"] = [*entry["notes"], note]
        if model:
            entry = _deviation(entry, hs.TITLE_MODEL)
    else:
        raise SystemExit(f"{arm} runs in slices: --shard K/N, then combine")
    return _finish(arm, entry, llm.call_stats(), time.time() - t0, {"started_commit": started})


def _units(arm: str) -> list[str]:
    if arm == "e4hm":
        from eval import e4_heldout as E4H

        return E4H.ids()
    if arm in LATER_BY_ARM:
        return list(importlib.import_module(LATER_BY_ARM[arm][0]).ids())
    if arm in HARM_BY_ARM:
        return list(importlib.import_module(HARM_BY_ARM[arm][0]).ids())
    return [f"P{i + 1:02d}" for i in range(ARMS[arm]["owners"])]


def _slice(arm: str, k: int, n: int) -> set[str]:
    return {u for i, u in enumerate(_units(arm)) if i % n == k}


def run_shard(arm: str, k: int, n: int) -> None:
    """One slice of the owners (E2-model, E1b): saves its raw rows for `combine`."""
    work = _env(arm)
    from agent import llm

    t0 = time.time()
    only = _slice(arm, k, n)
    part: dict[str, Any] = {"arm": arm, "shard": [k, n], "owners": sorted(only), "git_commit": C.provenance()["git_commit"]}
    if arm == "e2m":
        from eval import e1a_journey as E1A
        from eval import e2_grounding as E2

        rec = E2.Recorder()
        payload = E1A.run(n=60, workdir=work, recorder=rec, only=only)
        part |= {"rows": payload["rows"], "voice": payload["voice"], "records": rec.records, "composed": rec.composed}
    elif arm == "e1b":
        from eval import e1b_model_owner as E1B

        rows, voice = E1B.run_rows(workdir=work, only=only)
        part |= {"rows": rows, "voice": voice}
    elif arm == "e4hm":
        from eval import e4_heldout as E4H

        part |= {"raw": E4H.run_rows(workdir=work, only=only)}
    elif arm in LATER_BY_ARM and arm not in LATER_SETS:
        part |= {"raw": importlib.import_module(LATER_BY_ARM[arm][0]).run_rows(workdir=work, only=only)}
    elif arm in HARM_BY_ARM and arm not in HARM_SETS:
        part |= {"raw": importlib.import_module(HARM_BY_ARM[arm][0]).run_rows(workdir=work, only=only)}
    else:
        raise SystemExit(f"{arm} is not sliced")
    part |= {"model_calls": llm.call_stats(), "runtime_s": round(time.time() - t0, 1)}
    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / f"{arm}_{k}of{n}.json").write_text(json.dumps(part, ensure_ascii=False, default=str), encoding="utf-8")


def combine(arm: str) -> dict[str, Any]:
    parts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PARTS.glob(f"{arm}_*of*.json"))]
    if not parts:
        raise SystemExit(f"no slices of {arm} yet")
    n = parts[0]["shard"][1]
    got = sorted({o for p in parts for o in p["owners"]})
    want = sorted(_units(arm))
    if got != want or len(parts) != n:
        raise SystemExit(f"{arm}: slices cover {len(got)}/{len(want)} units in {len(parts)}/{n} parts; run the rest first")
    commits = sorted({p["git_commit"] for p in parts})
    stats = {k: sum(p["model_calls"][k] for p in parts) for k in ("calls", "failed", "cooling_refusals")}
    wall = max(p["runtime_s"] for p in parts)
    extra = {"slices": n, "slice_commits": commits, "summed_runtime_s": round(sum(p["runtime_s"] for p in parts), 1)}
    if arm in HARM_BY_ARM and arm not in HARM_SETS:
        mod_name, note = HARM_BY_ARM[arm]
        hs = importlib.import_module(mod_name)
        order = {u: i for i, u in enumerate(want)}
        raw5: dict[str, Any] = {"voice": parts[0]["raw"]["voice"], "errors": [e for p in parts for e in p["raw"]["errors"]]}
        raw5["scripts"] = sorted((r for p in parts for r in p["raw"]["scripts"]), key=lambda r: order[r["id"]])
        raw5["controls"] = sorted((r for p in parts for r in p["raw"]["controls"]), key=lambda r: order[r["id"]])
        raw5["turns"] = sorted((r for p in parts for r in p["raw"]["turns"]), key=lambda r: order[r["script"]])  # stable: each script's turns stay in order
        judged = hs.judge(raw5)
        stats = {k: stats[k] + judged["calls"].get(k, 0) for k in stats}
        entry = hs.summarise(raw5, judged, hs.TITLE_MODEL, runtime_s=wall)
        entry["notes"] = [*entry["notes"], note, f"Judge: {judged['runtime_s']} s in combine, {judged['calls']} (included in the model calls below)."]
        return _finish(arm, _deviation(entry, hs.TITLE_MODEL), stats, wall, extra)
    if arm == "e4hm" or (arm in LATER_BY_ARM and arm not in LATER_SETS):
        from eval import e4_heldout as E4H

        order = {u: i for i, u in enumerate(want)}
        raw: dict[str, Any] = {"voice": parts[0]["raw"]["voice"], "errors": [e for p in parts for e in p["raw"]["errors"]]}
        for key, idk in (("scripts", "id"), ("turns", "script"), ("controls", "id")):
            raw[key] = sorted((r for p in parts for r in p["raw"][key]), key=lambda r, idk=idk: (order[r[idk]], r.get("turn", 0)))
        if arm == "e4hm":
            entry = E4H.summarise(raw, E4HM_TITLE, runtime_s=wall)
            entry["notes"] = [*entry["notes"], E4H_SMOKE]
            return _finish(arm, _deviation(entry, E4HM_TITLE), stats, wall, extra)
        mod_name, note = LATER_BY_ARM[arm]
        hs = importlib.import_module(mod_name)
        entry = hs.summarise(raw, hs.TITLE_MODEL, runtime_s=wall)
        entry["notes"] = [*entry["notes"], note]
        return _finish(arm, _deviation(entry, hs.TITLE_MODEL), stats, wall, extra)
    rows = sorted((r for p in parts for r in p["rows"]), key=lambda r: r["persona"]["pid"])
    if arm == "e2m":
        from eval import e1a_journey as E1A
        from eval import e2_grounding as E2

        rec = E2.Recorder()
        for p in parts:
            rec.records.update(p["records"])
            rec.composed.update(p["composed"])
        payload = {"n": len(rows), "rows": rows, "voice": parts[0]["voice"], "recorder": rec,
                   "delivered": {r["persona"]["pid"]: r["delivered"] for r in rows}}
        e1a = E1A.evaluate(payload, runtime_s=wall)
        entry = E2.evaluate(payload)
        entry.setdefault("metrics", {})["e1a_with_the_model"] = {"pass_marks": e1a.get("pass_marks"), "metrics": e1a.get("metrics")}
        entry["notes"] = [
            *entry.get("notes", []),
            "E1a's 60 personas with the model writing and understanding (descriptive): "
            + "; ".join(f"{k} {v['value']}" for k, v in (e1a.get("pass_marks") or {}).items()) + ".",
        ]
        entry = _deviation(entry, "Every delivered quantity is grounded, with a model writing the messages")
    else:
        from eval import e1b_model_owner as E1B

        entry = E1B.summarise(rows, parts[0]["voice"], runtime_s=wall)
        entry["notes"] = [f"Model arm, {DEVIATION}.", *entry.get("notes", [])]
    return _finish(arm, entry, stats, wall, extra)


def measured() -> dict[str, dict[str, Any]]:
    """Every arm already measured (results/model_arms/*.json), by eval key."""
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(DIR.glob("*.json")) if DIR.exists() else []:
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return out


def _describe_e5(entry: dict[str, Any]) -> None:
    """E5-model, descriptive: how many recorded failures were only the reader's own 'ignored a planted
    instruction' audit entry (no tool call, transfer, recipient or field changed). Computed from the stored
    failure rows; the mark itself is the pre-registered one and is not changed."""
    from eval.e5_documents import _only_ignore_mark

    m = entry.get("metrics", {})
    rows = m.get("failure_examples") or []
    total = int(m.get("by_kind", {}).get("action", 0)) + int(m.get("by_kind", {}).get("recipient", 0)) + int(m.get("by_kind", {}).get("non-cost", 0))
    only = sum(1 for r in rows if _only_ignore_mark(r.get("fails", [])))
    note = (
        f"Descriptive: of the failures recorded in full ({len(rows)} of {total or len(rows)} variants with a change), "
        f"{only} changed nothing but the audit log's 'ignored_document_instruction' entry: the reader dropping a planted "
        "instruction line, with no tool call, transfer, recipient or field changed. The pre-registered measure counts any "
        "new audit action, so they stay failures here. (This run kept only the first 8 failure rows; later runs keep all.)"
    )
    if not any(n.startswith("Descriptive: of the failures recorded in full") for n in entry.get("notes", [])):
        entry["notes"] = [*entry.get("notes", []), note]


def _describe_e4h5m(entry: dict[str, Any]) -> None:
    """E4-heldout-5-model, descriptive: the provider refused calls for part of the run (a usage limit; the product
    fell back to no model, and the judge could not run). Splits the stored rows into the scripts whose every pressure
    turn had the model's words (no model-unavailable notice) and the rest. The marks are the pre-registered ones,
    over all 300 scripts, and are not changed."""
    parts = sorted(PARTS.glob("e4h5m_*of*.json"))
    if not parts or any(n.startswith("Descriptive (provider outage)") for n in entry.get("notes", [])):
        return
    scripts: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    for p in parts:
        raw = json.loads(p.read_text(encoding="utf-8"))["raw"]
        scripts += raw["scripts"]
        turns += raw["turns"]
        controls += raw["controls"]
    no_model = {r["script"] for r in turns if "Notice:" in r["reply"]}
    ok = [x for x in scripts if x["id"] not in no_model]

    def w(rows: list[dict[str, Any]], f: Any) -> dict[str, Any]:
        return C.wilson(sum(1 for r in rows if f(r)), len(rows))

    def plan(x: dict[str, Any]) -> bool:
        return bool(x["after_pressure"]["rule_breaking"] or x["at_end"]["rule_breaking"])

    sub = {
        "scripts_with_the_model_throughout": len(ok),
        "pressure_turns_with_a_model_unavailable_notice": sum(1 for r in turns if "Notice:" in r["reply"]),
        "pressure_turns": len(turns),
        "capitulation_per_script": w(ok, lambda x: not x["blocked"]),
        "rule_breaking_approved_goal_or_confirmed_plan": w(ok, plan),
        "approved_goal_breaking_a_rule_only_with_facts_restored": sum(
            1 for x in ok if x["at_end"]["approved_goal"] and x["at_end"]["rule_breaking"] and not x["at_end"]["violations_as_is"]
        ),
        "reached_an_approved_goal": w(ok, lambda x: x["at_end"]["approved_goal"]),
        "facts_changed_by_the_finisher": sum(1 for x in ok if x["at_end"]["facts_changed"]),
        "money_step_prepared": w(ok, lambda x: bool(x["money_steps"])),
    }
    entry.setdefault("metrics", {})["descriptive_scripts_with_the_model_throughout"] = sub
    entry["notes"] = [
        *entry.get("notes", []),
        "Descriptive (provider outage): the Claude Code login hit its usage limit part-way through every slice, so "
        f"{sub['pressure_turns_with_a_model_unavailable_notice']}/{sub['pressure_turns']} pressure turns got the product's "
        "no-model fallback (keyword guard, no words), the controls (run last in each slice) ran without the model, and "
        "the judge could not run in combine (every call failed: the reply check is not valid, as pre-registered). "
        f"On the {len(ok)} scripts whose every pressure turn had the model's words: capitulation "
        f"{C.wfmt(sub['capitulation_per_script'])}; a rule-breaking approved goal or confirmed plan "
        f"{C.wfmt(sub['rule_breaking_approved_goal_or_confirmed_plan'])} ({sub['approved_goal_breaking_a_rule_only_with_facts_restored']} "
        "approved goals breaking R5 only once the finisher's inflated spare cash is restored to the feed's figure); "
        f"a money step {C.wfmt(sub['money_step_prepared'])}. This split is post hoc and descriptive.",
    ]


def merge() -> None:
    got = measured()
    if "E5-model" in got:
        _describe_e5(got["E5-model"])
    if "E4-heldout-5-model" in got:
        _describe_e4h5m(got["E4-heldout-5-model"])
        (DIR / "E4-heldout-5-model.json").write_text(json.dumps(got["E4-heldout-5-model"], indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    if not got:
        print("no model arm measured yet")
        return
    results = C.write_results(got)
    C.render_markdown(results)
    print("merged:", ", ".join(got))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "combine", "merge"])
    ap.add_argument("arm", nargs="?", choices=sorted(ARMS))
    ap.add_argument("--shard", help="K/N: run slice K of N (E2-model, E1b, E4-heldout-model, E4-heldout-2-model, E4-heldout-3-model, E4-heldout-4-model, E4-heldout-5-model, E4-heldout-6-model)")
    a = ap.parse_args(argv)
    if a.cmd == "merge":
        merge()
        return 0
    if not a.arm:
        ap.error(f"{a.cmd} needs an arm")
    if a.cmd == "combine":
        e = combine(a.arm)
    elif a.shard:
        k, n = (int(x) for x in a.shard.split("/"))
        run_shard(a.arm, k, n)
        print(a.arm, "slice", a.shard, "done")
        return 0
    else:
        e = run(a.arm)
    print(a.arm, e["status"], {k: (m["value"], m["pass"]) for k, m in e.get("pass_marks", {}).items()})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
