"""Shared evaluation helpers (SPEC §11, results/prereg.md).

- `setup_env` points every writable path (DB, audit log, documents) at a temp dir and turns models off.
- `Driver` runs the real orchestrator turn by turn for one simulated owner, as tests/test_journey.py does.
- `wilson`, `bootstrap_ci` give the pre-registered 95% intervals.
- `write_results` merges eval entries into results/results.json; `render_markdown` writes RESULTS.md.

Everything evaluated here is simulated: a fictional company, a mocked WeBank feed, simulated units.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import math
import os
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
RESULTS_JSON = RESULTS_DIR / "results.json"
RESULTS_MD = RESULTS_DIR / "RESULTS.md"
PREREG = RESULTS_DIR / "prereg.md"
SEED = 20261019
BOOTSTRAP_RESAMPLES = 10_000
Z95 = 1.959963984540054

EVAL_ORDER = [
    "E1a", "E1b", "E2", "E2-model", "E3", "E4", "E4-model", "E4-heldout", "E4-heldout-model",
    "E4-heldout-2", "E4-heldout-2-model", "E4-heldout-3", "E4-heldout-3-model",
    "E4-heldout-4", "E4-heldout-4-model",
    "E4-heldout-5", "E4-heldout-5-model", "E4-heldout-6", "E4-heldout-6-model",
    "E5", "E5-model", "E6", "E6-heldout", "E7", "E8",
]


# ------------------------------------------------------------------ environment


def model_arm() -> str | None:
    """The model arm this process runs (WAYPOINT_EVAL_MODEL_ARM), or None for the no-model evals."""
    return os.environ.get("WAYPOINT_EVAL_MODEL_ARM") or None


def setup_env(workdir: Path | None = None) -> Path:
    """Temp dirs for everything the app writes; no model; no mail server. Returns the work dir."""
    work = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="waypoint-eval-"))
    work.mkdir(parents=True, exist_ok=True)
    os.environ["WAYPOINT_VAR"] = str(work)
    os.environ["WAYPOINT_AUDIT"] = str(work / "audit.jsonl")
    os.environ["WAYPOINT_SMTP_PORT"] = "1"
    if model_arm():
        # a model arm (results/prereg.md addendum 2): the configured model is on (config/models.yaml)
        os.environ.pop("WAYPOINT_LLM_PROVIDER", None)
    else:
        os.environ["WAYPOINT_LLM_PROVIDER"] = "none"
    if os.environ.get("WAYPOINT_EVAL_READER") == "model":
        os.environ.pop("WAYPOINT_READER_REPLAY", None)  # E5-model: the vision reader reads the images
    else:
        # Gold-label replay for the synthetic sample quote (and E5's poisoned variants): test-only reader.
        os.environ["WAYPOINT_READER_REPLAY"] = "1"
    for role in ("TURN", "READER", "JUDGE", "SIM"):
        os.environ.pop(f"WAYPOINT_LLM_{role}_PROVIDER", None)
    logging.disable(logging.WARNING)  # email-not-delivered warnings etc.; results never depend on logs
    return work


def make_services(workdir: Path, name: str) -> Any:
    """A fresh AppServices with its own SQLite file, audit log and document dir under `workdir`."""
    sub = Path(workdir) / name
    sub.mkdir(parents=True, exist_ok=True)
    os.environ["WAYPOINT_AUDIT"] = str(sub / "audit.jsonl")
    from app.services import AppServices
    from app.store import Store

    svc = AppServices(Store(f"sqlite:///{sub / 'db.sqlite3'}"), base_url="http://eval.test", demo=True)
    svc.docs_dir = sub / "docs"
    svc.docs_dir.mkdir(parents=True, exist_ok=True)
    return svc


# ------------------------------------------------------------------ driver


class Driver:
    """One simulated owner driven through the real orchestrator (no model)."""

    _n = 0

    def __init__(self, svc: Any, host_mode: str = "embedded", tag: str = "owner") -> None:
        Driver._n += 1
        self.svc = svc
        self.user = svc.store.create_user(host_mode, email=f"{tag}{Driver._n}@eval.test", verified=True)
        self.state = svc.load_state(self.user)
        self.outs: list[Any] = []
        self.owner_turns = 0
        self.transcript: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def run(
        self,
        text: str | None = None,
        event: Any = None,
        init: bool = False,
        restore_on_error: bool = True,
    ) -> list[Any]:
        """One turn. Like app/main.py, state is saved only if the turn finishes; on an unhandled
        exception the in-memory state is replaced by the last saved one."""
        if not init:
            self.owner_turns += 1
        self.transcript.append(
            {
                "who": "owner",
                "text": text,
                "event": event.model_dump(mode="json") if event is not None else None,
                "step": self.state.step,
            }
        )
        try:
            self.outs = asyncio.run(self.svc.orchestrator.run(self.state, text=text, event=event, init=init))
        except Exception as exc:  # noqa: BLE001 - an unhandled exception is a result, recorded
            self.errors.append(f"{type(exc).__name__}: {exc}"[:300])
            self.outs = []
            if restore_on_error:
                self.state = self.svc.load_state(self.user)
            self.transcript.append({"who": "error", "error": self.errors[-1]})
            return self.outs
        self.svc.save_state(self.state)
        for o in self.outs:
            if o.kind == "text":
                self.transcript.append({"who": "bot", "text": o.text})
            elif o.kind == "widget" and o.widget is not None:
                self.transcript.append({"who": "bot", "widget": o.widget.payload.type, "id": o.widget.id})
        return self.outs

    # convenience
    def widgets(self, wtype: str | None = None) -> list[Any]:
        return [
            o.widget
            for o in self.outs
            if o.kind == "widget"
            and o.widget is not None
            and (wtype is None or o.widget.payload.type == wtype)
        ]

    def texts(self) -> list[str]:
        return [o.text or "" for o in self.outs if o.kind == "text"]

    def reply(self, value: str) -> list[Any]:
        from agent.widgets import WidgetEvent

        p = self.state.pending
        assert p is not None, "no pending question"
        return self.run(event=WidgetEvent(widget_id=p.widget_id or "", event="reply", value=value))

    def latest_widget_id(self, wtype: str) -> str | None:
        ids = [k for k, v in self.state.widget_types.items() if v == wtype]
        return max(ids, key=lambda k: int(k[1:])) if ids else None

    def event(
        self, wtype: str, event: str, value: Any = None, data: dict[str, Any] | None = None
    ) -> list[Any]:
        from agent.widgets import WidgetEvent

        wid = self.latest_widget_id(wtype) or ""
        return self.run(event=WidgetEvent(widget_id=wid, event=event, value=value, data=data or {}))  # type: ignore[arg-type]


def clone_state(state: Any) -> Any:
    from agent.state import JourneyState

    return JourneyState.model_validate(copy.deepcopy(state.model_dump()))


# ------------------------------------------------------------------ statistics


def wilson(k: int, n: int, z: float = Z95) -> dict[str, Any]:
    """Wilson score interval for k successes in n trials (95% by default)."""
    if n == 0:
        return {"k": k, "n": n, "p": None, "lo": None, "hi": None, "method": "wilson95"}
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {
        "k": k,
        "n": n,
        "p": round(p, 6),
        "lo": round(max(0.0, centre - half), 6),
        "hi": round(min(1.0, centre + half), 6),
        "method": "wilson95",
    }


def bootstrap_ci(
    values: Sequence[float],
    stat: Callable[[np.ndarray], float] = np.median,  # type: ignore[assignment]
    seed: int = SEED,
    resamples: int = BOOTSTRAP_RESAMPLES,
    level: float = 0.95,
) -> dict[str, Any]:
    """Percentile bootstrap CI (seeded)."""
    x = np.asarray(list(values), dtype=float)
    if x.size == 0:
        return {"value": None, "lo": None, "hi": None, "method": "percentile_bootstrap", "seed": seed}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(resamples, x.size))
    stats = np.apply_along_axis(stat, 1, x[idx]) if stat is not np.median else np.median(x[idx], axis=1)
    a = (1 - level) / 2
    return {
        "value": float(stat(x)),
        "lo": float(np.percentile(stats, 100 * a)),
        "hi": float(np.percentile(stats, 100 * (1 - a))),
        "method": "percentile_bootstrap",
        "resamples": resamples,
        "seed": seed,
    }


# ------------------------------------------------------------------ provenance


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def prompts_sha256() -> str:
    """Prompts in force: agent/prompts/*, config/models.yaml and the reader's fixed instructions."""
    from agent.reader import READER_INSTRUCTIONS

    h = hashlib.sha256()
    for p in sorted((ROOT / "agent" / "prompts").glob("**/*")):
        if p.is_file():
            h.update(p.relative_to(ROOT).as_posix().encode())
            h.update(p.read_bytes())
    models = ROOT / "config" / "models.yaml"
    if models.exists():
        h.update(models.read_bytes())
    h.update(READER_INSTRUCTIONS.encode())
    return h.hexdigest()


def provenance() -> dict[str, Any]:
    from agent import llm, toolkit
    from agent.skills import load_skills

    reg = load_skills(known_tools=frozenset(toolkit.TOOL_NAMES))
    prereg_commit = _git("log", "-1", "--format=%H", "--", "results/prereg.md")
    prereg_dirty = bool(_git("status", "--porcelain", "--", "results/prereg.md"))
    head = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    return {
        "git_commit": head + ("-dirty" if dirty else ""),
        "prereg": {
            "path": "results/prereg.md",
            "commit": prereg_commit,
            "sha256": sha256_file(PREREG),
            "modified_since_commit": prereg_dirty,
        },
        "versions": {
            "skills": reg.versions(),
            "params": sha256_file(ROOT / "data" / "params.yaml"),
            "cost_key": sha256_file(ROOT / "data" / "cost_key.yaml"),
            "topics": sha256_file(ROOT / "data" / "topics.yaml"),
            "funding_catalogue": sha256_file(ROOT / "data" / "funding_catalogue.yaml"),
            "prompts": prompts_sha256(),
        },
        "model": llm.model_label(),
    }


# ------------------------------------------------------------------ results


def entry(
    status: str,
    n: int = 0,
    metrics: dict[str, Any] | None = None,
    pass_marks: dict[str, dict[str, Any]] | None = None,
    seed: int | None = SEED,
    notes: list[str] | str | None = None,
    reason: str | None = None,
    title: str = "",
    runtime_s: float | None = None,
) -> dict[str, Any]:
    e: dict[str, Any] = {
        "title": title,
        "status": status,
        "n": n,
        "metrics": metrics or {},
        "pass_marks": pass_marks or {},
        "seed": seed,
        "notes": [notes] if isinstance(notes, str) else list(notes or []),
    }
    if reason:
        e["reason"] = reason
    if runtime_s is not None:
        e["runtime_s"] = round(runtime_s, 2)
    return e


def mark(label: str, value: Any, ok: bool) -> dict[str, Any]:
    return {"mark": label, "value": value, "pass": bool(ok)}


# A model arm ran with Claude in every role (prereg addendum 2): a met mark is descriptive, not a pass.
MET_SINGLE_FAMILY = "met (descriptive, single-family deviation)"


def result_label(e: dict[str, Any], pm: dict[str, Any]) -> str:
    """How a pass mark's outcome is reported: pass, fail, or met but descriptive for a single-family arm."""
    if not pm["pass"]:
        return "fail"
    return MET_SINGLE_FAMILY if _is_model_arm(e) else "pass"


# What changed in the product between runs (written when the change is made, before re-running).
CHANGES: list[str] = [
    "E3 found product bugs; fixed with regression tests (tests/test_journey.py): widgets are bound to the step "  # noqa: E501
    "that issued them, so an old confirm card can't confirm the current step; confirm events must come from a "  # noqa: E501
    "confirm-capable card with a known value; reopen only reaches steps already done; units and areas must be "  # noqa: E501
    "ones offered; consent accepts only a boolean, and a step's confirm card must name its step (both tightened after the second run); slider shares are validated to [0, 1]; unknown or closed "  # noqa: E501
    "funding options are refused; malformed events are logged and ignored instead of raising.",
    "The guard's keyword lists were broadened twice after E4 had failed (judge reviews, 2026-10-19): new "
    "EN/ZH patterns written from rules/rules.yaml and tested on new phrasings, without reading the E4 "
    "scripts; the second round also stops flagging a question that only asks about a rule or its risk. "
    "E4 capitulation per script was 89.0% (Wilson upper bound 92.6%) before the first round and 65.2% "
    "(upper bound 71.4%) after it. These re-runs are therefore not independent; a held-out script set is "
    "still to do. E4-model was not re-run.",
    "Journey simplified after the earlier runs (v3, from E1a's own turn count and the UX research memo): "
    "no language question; cost uses defaults plus one 'anything to change?' question; quote lines "
    "'Accept all'; picking a unit confirms it; 'Looks good' moves funding on; goal preferences are defaults "
    "on the approval card. Personas now tap 'Accept all' and approve the card with its defaults. E1a's pass "
    "marks and persona set are unchanged.",
    "Detector changed after E6 failed its false-alert mark (prereg addendum 2026-10-19, written before the "
    "re-run): seasonal shape shrunk for noise; CUSUM k 0.05 -> 0.12, h 0.30 -> 0.40, chosen on the dev "
    "chains only. Measured once on the test chains; not re-tuned on them.",
    "Model arms (prereg addendum 2, Claude in every role). A first E4-model run was discarded, not reported: a "  # noqa: E501
    "change to the model layer left most turns without the model (an unfinished answer started the provider "
    "cooldown); fixed in 34bca7d, and every arm now records its model calls and failures. E4-model and "
    "E5-model then ran from commit 34bca7d, but their entries record the commit when they finished (a harness "  # noqa: E501
    "bug, fixed: arms now record the commit they start from). E2-model and E1b ran in slices from 4d3b5b9.",
    "R8 guard fix and a held-out test (prereg addendum 2026-10-20, written before the set existed): the keyword "  # noqa: E501
    "check's R8 patterns were rewritten from R8's text (Singapore banks, EFS and other Singapore lenders before "  # noqa: E501
    "opening, EN/ZH; a request counts as before opening unless it says after) and the guard Skill (v4) states R8 for "  # noqa: E501
    "the model. E4 re-runs after this are not independent. The new held-out set (eval/e4_heldout_scripts.py, 120 "  # noqa: E501
    "scripts and 40 controls, written blind to the guard) ran once per arm: E4-heldout (keyword baseline) and "  # noqa: E501
    "E4-heldout-model (single-family deviation), stored in results/model_arms/.",
    "R4/R6 guard fix and a second held-out test (prereg addendum 2026-10-20 (2), written before the set existed): "  # noqa: E501
    "R4 and R6 keyword patterns written from the rule text (the legal order, split or relayed transfers, the "  # noqa: E501
    "pre-investment allowance; no commitment to the unit before all the money is in Singapore, EN/ZH) and the "  # noqa: E501
    "guard Skill (v5) states both for the model. E4 re-runs after this are not independent. The second set "
    "(eval/e4_heldout2_scripts.py, 120 scripts weighted to R4 and R6 and 40 controls, written by a subagent that "  # noqa: E501
    "read no file) ran once per arm: E4-heldout-2 (keyword) and E4-heldout-2-model (single-family deviation).",  # noqa: E501
    "R4/R6 narrowed (prereg addendum 2026-10-20 (3), written before the set existed): questions about a step, "  # noqa: E501
    "its order or status, step-done reports, what a rule means, and the next lawful step once every step is done "  # noqa: E501
    "or all the money is in stay quiet (guard Skill v6). A third held-out set (eval/e4_heldout3_scripts.py, 280 "  # noqa: E501
    "scripts and 80 controls, written blind) ran once per arm: E4-heldout-3 and E4-heldout-3-model.",
    "R2 and R1 guard fix (prereg addendum 2026-10-20 (4), written before the set existed): R2 (the set-aside "  # noqa: E501
    "kept going while borrowing is above usual, borrowing for home costs to free profit, making borrowing look "  # noqa: E501
    "usual), R1 (loan money flowing to anything in Singapore, incl. bridges and relabelling) and R4's every-step-done "  # noqa: E501
    "reading, from the rule text (guard Skill v7). E4 re-runs after this are not independent. A fourth held-out set "  # noqa: E501
    "(eval/e4_heldout4_scripts.py, 300 scripts weighted to R2 and R1, 100 controls, written blind) ran once per "  # noqa: E501
    "arm: E4-heldout-4 and E4-heldout-4-model.",
    "Found by the model arms and fixed after they ran (the arms are not re-run): E1b's two stuck owners could "  # noqa: E501
    "not correct a business fact at the funding step (correct_business action; a lower spare cash now reaches "  # noqa: E501
    "the plan); E1b's first live try found the approval message saying 'monthly' after the owner picked "
    "another reminder frequency (the message now follows the owner's choices).",
    "Persona: Chen's chain is 30 shops (was 14), with the same totals (sales, profit, cash, payroll). The "
    "demo's sales dip is four shops (was two), so it stays about the same share of the chain (13% vs 14%); "
    "E6's demo-dip class follows it (demo_dip_four_shops_-20_sales). Other classes and all pass marks are "
    "unchanged.",
    "Cash-flow fixes after the judge review of 2026-10-20 (prereg addendum 2026-10-20 (6), written before the "  # noqa: E501
    "re-run): the plan simulates the monthly set-aside as the signed instruction (a fixed amount, skipped any "  # noqa: E501
    "month R2 holds or it would leave home cash below floor + buffer; the mock bank does the same); the wall "  # noqa: E501
    "needs the floor risk's Wilson 95% upper bound <= 5%, on 4,000 runs (was the point estimate on 1,000), "  # noqa: E501
    "and the preview's runs are the first 200 of those, its floor risk the full solve's; Goal Keeper status "  # noqa: E501
    "reads its thresholds from params. The demo persona's seed is 1423 (was 1414, whose no-shock run alerted by "  # noqa: E501
    "itself), chosen by the addendum's rule (results/demo/seed_search.json). E8 times the 4,000-run solve. "
    "Pass marks and methods are unchanged; the model arms are not re-run.",
    "Goal Keeper detector (prereg addendum 2026-10-20 (7), written before the change): two input bugs fixed "  # noqa: E501
    "(the channel-shift guard fired on about 95% of normal weeks in Jan, Feb and June, and the seasonal shape "  # noqa: E501
    "carried late-December days into January); the CUSUM now runs on drops below an adaptive reference, in "  # noqa: E501
    "sigmas, with k, h, lambda, lag and the shape shrink frozen on dev seeds 0-299 (results/detect_freeze.json). "  # noqa: E501
    "E6 is re-run on its own chains (no longer clean held-out evidence: the judge-response memo explored on "  # noqa: E501
    "its seeds); E6-heldout, a new held-out shock set, ran once (results/model_arms/E6-heldout.json). The demo "  # noqa: E501
    "seed rule (addendum (6)) was re-run with the new detector and chose 1422 (was 1423), so every eval that uses "  # noqa: E501
    "the persona's default seed (E1a, E2, E3, E8, the demo) runs on a different simulated history. E6's earlier "  # noqa: E501
    "FAIL rows stay in previous_runs. Pass marks are unchanged.",
    "Reply allowlist (prereg addendum 2026-10-20 (8), written before the code): a side question is answered only "  # noqa: E501
    "with a library topic card or the fixed scope card (T-SCOPE), then the pending question, never a free-form "  # noqa: E501
    "reply; the voice no longer sees the owner's typed words (journey Skill v4, detour Skill v4). From E4-heldout-5 on, "  # noqa: E501
    "end-to-end harm is E4's primary safety mark (capitulation kept as a secondary measure, mark unchanged), "  # noqa: E501
    "measured with an adversarial finisher and a model reply-content check. A fifth held-out set "
    "(eval/e4_heldout5_scripts.py, 300 scripts weighted to R2, 60% Chinese, 120 controls, written blind after the "  # noqa: E501
    "code was frozen) ran once per arm: E4-heldout-5 and E4-heldout-5-model.",
    "Two harm paths closed (prereg addendum 2026-10-20 (13), written before the code): with the feed connected, a "  # noqa: E501
    "figure the feed provides is never used above the feed's (a higher typed correction is kept as not verified; the "  # noqa: E501
    "goal moves the spare cash the plan used; the approval card covers it and its re-check re-simulates the plan); "  # noqa: E501
    "any change to an input of the funding plan clears its confirmation; the max_turns fallback never answers a "  # noqa: E501
    "step-confirming question (funding v5, cost v4, site-finder v4, journey v5). A sixth held-out set "
    "(eval/e4_heldout6_scripts.py, 300 scripts weighted to R2 and the two paths, 60% Chinese, 120 controls, written "  # noqa: E501
    "blind after the code was frozen) ran once per arm: E4-heldout-6 and E4-heldout-6-model.",
]


def write_results(evals: dict[str, dict[str, Any]], path: Path = RESULTS_JSON) -> dict[str, Any]:
    """Merge eval entries into results.json (other evals already there are kept) and refresh provenance."""
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    merged = dict(data.get("evals", {}))
    merged.update(evals)
    for e in merged.values():
        for pm in e.get("pass_marks", {}).values():
            pm["result"] = result_label(e, pm)
    history = list(data.get("previous_runs", []))
    if data.get("evals") and data.get("git_commit"):
        # keep every earlier run's pass marks: a later run never erases an earlier failure
        history.append({
            "git_commit": data["git_commit"], "generated_at": data.get("generated_at"),
            "pass_marks": {k: {n: {"value": pm["value"], "pass": pm["pass"]} for n, pm in e.get("pass_marks", {}).items()}  # noqa: E501
                           for k, e in data["evals"].items() if e.get("status") == "run"},
        })
    out = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **provenance(),
        "simulated": True,
        "evals": {k: merged[k] for k in sorted(merged, key=_order)},
        "previous_runs": history,
        "changes_since_previous": CHANGES,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return out


def _order(k: str) -> tuple[int, str]:
    return (EVAL_ORDER.index(k) if k in EVAL_ORDER else 99, k)


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, dict):
        return ", ".join(f"{k} {_fmt(x)}" for k, x in v.items())
    return str(v)


def _is_model_arm(e: dict[str, Any]) -> bool:
    return bool(e.get("model_arm")) and not e["model_arm"].get("no_model")


def render_markdown(results: dict[str, Any], path: Path = RESULTS_MD, runtime_s: float | None = None) -> str:
    ev = results["evals"]
    lines = [
        "# Waypoint evaluation results (simulated)",
        "",
        f"Generated {results['generated_at']} by `eval/run_all.py` from commit `{results['git_commit']}`. "
        f"Pre-registration: `{results['prereg']['path']}` (commit `{results['prereg']['commit'][:10]}`, "
        f"sha256 `{results['prereg']['sha256'][:12]}`).",
        "",
        "**Everything here is simulated**: a fictional company (TulBrew, Joon Rui's tea chain), "
        "a mocked WeBank feed, "
        "simulated unit listings, scripted owners. These numbers say how the build behaves on simulated "
        "inputs, not how real owners would fare. This page is written by code; never edit it by hand.",
        "",
        "**The no-model arms (E1a, E2, E3, E4, E5).** The voice layer normally has a model write every "
        "message; these ran with the product's deterministic test composer (`agent.voice.echo_composer`: "
        "each beat's key "
        "plus its required figure placeholders) and code-only understanding of typed text. The quarantined "
        "document reader ran in gold-label replay mode (`WAYPOINT_READER_REPLAY=1`, test-only).",
        "",
        *(
            [
                "**The model arms (" + ", ".join(k for k, e in ev.items() if _is_model_arm(e)) + ")** ran "
                "with Claude in every role (the agent, and the simulated owner in E1b), through "
                "`eval.model_arms`, "
                "each at its own commit (in its notes). That breaks the pre-registration's three-family rule "
                "(addendum 2): their marks are labelled *single-family deviation* and are descriptive, not "
                f"pre-registered passes; a mark they reach reads *{MET_SINGLE_FAMILY}*, not pass. TODO: "
                "re-run with an owner from another model family.",
                "",
            ]
            if any(_is_model_arm(e) for e in ev.values())
            else []
        ),
        "## Pass marks",
        "",
        "| Eval | What | Pass mark | Measured | Result |",
        "|---|---|---|---|---|",
    ]
    for key, e in ev.items():
        if e["status"] == "not_run":
            lines.append(f"| {key} | {e.get('title', '')} | — | — | not run |")
            continue
        for name, pm in e["pass_marks"].items():
            res = result_label(e, pm)
            res = "**FAIL**" if res == "fail" else res
            lines.append(f"| {key} | {name} | {pm['mark']} | {_fmt(pm['value'])} | {res} |")
    if results.get("previous_runs"):
        lines += ["", "## Earlier runs (kept; nothing is erased)", ""]
        for run in results["previous_runs"]:
            fails = [f"{k} {n} ({_fmt(v['value'])})" for k, pms in run["pass_marks"].items()
                     for n, v in pms.items() if not v["pass"]]
            lines.append(f"- Commit `{run['git_commit'][:10]}` ({run.get('generated_at')}): "
                         + ("failed: " + "; ".join(fails) if fails else "no failed pass marks"))
        if results.get("changes_since_previous"):
            lines += ["", "**Changed since the previous run, and why** (pass marks and methods unchanged):", ""]  # noqa: E501
            lines += [f"- {c}" for c in results["changes_since_previous"]]
    lines += ["", "## Not run", ""]
    for key, e in ev.items():
        if e["status"] == "not_run":
            lines.append(f"- **{key}** ({e.get('title', '')}): {e.get('reason', '')}")
    lines += ["", "## Notes (descriptive)", ""]
    for key, e in ev.items():
        if e["status"] == "not_run":
            continue
        lines.append(f"### {key}: {e.get('title', '')}")
        lines.append("")
        lines.append(
            f"n = {e['n']}; seed {e.get('seed')}"
            + (f"; runtime {e['runtime_s']} s" if e.get("runtime_s") is not None else "")
            + "."
        )
        for note in e.get("notes", []):
            lines.append(f"- {note}")
        lines.append("")
    if runtime_s is not None:
        lines.append(f"Total runtime of this run: {runtime_s:.0f} s.")
        lines.append("")
    text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    return text


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def wfmt(w: dict[str, Any]) -> str:
    """'k/n = p% (95% CI lo–hi%)'."""
    if not w.get("n"):
        return "n/a"
    return f"{w['k']}/{w['n']} = {pct(w['p'])} (95% CI {pct(w['lo'])}–{pct(w['hi'])})"
