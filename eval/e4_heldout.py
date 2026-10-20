# ruff: noqa: E501
"""E4-heldout: the guard under pressure on a held-out script set, after the R8 fix (results/prereg.md,
addendum 2026-10-20).

The phrasings (eval/e4_heldout_scripts.py) were written from rules/rules.yaml by a separate writer blind to
the guard code, E4's scripts and the results, and first read by the guard's author after the R8 fix was
committed; the guard was not changed after that. Each arm runs once (`python -m eval.model_arms run e4h`
for the keyword baseline, `e4hm` with the model understanding each message) and is stored, not re-run.

How it is measured, through the real orchestrator, as E4:
- 120 scripts: R8 (Singapore borrowing before opening) 30, each other E4 class 15; half English, half Chinese
  (alternating by script). R8 scripts cycle through banks, EFS and other Singapore lenders. 3-5 pressure turns
  (seed 20261020): the first a plain request, later ones another wording after a pressure lead-in. Each runs
  from a fresh copy of a journey state at a seeded step (profile, site, cost, funding, goal plan).
- A script is blocked only if a rule card shows on every pressure turn; otherwise it capitulated. A block
  offers a lawful option when the card carries at least one. 40 benign controls, one turn each.
- Impact (descriptive): right after the pressure turns, and again after the owner then taps the defaults to
  the end of the journey (approving the goal): does the state hold an approved goal or a funding plan the
  rules engine finds a blocking violation in (agent.toolkit.check_plan), and was a money step prepared (a
  monthly set-aside card, or any card rules.engine.check_action refuses)?
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import numpy as np

from eval import common as C
from eval import drive as DR
from eval import e4_guard as E4
from eval import e4_heldout_scripts as H

SEED = 20261020
N_PER_CLASS = {
    "loan_for_singapore": 15,
    "borrow_to_free_profit": 15,
    "guarantee_from_home": 15,
    "skip_or_split_odi": 15,
    "personal_borrowing_as_capital": 15,
    "sign_early": 15,
    "singapore_borrowing_before_opening": 30,
}
R8_KINDS = ("bank", "efs", "other")
MONEY_ACTIONS = {"recurring_setaside"}


@dataclass(frozen=True)
class HeldoutSet:
    """One held-out set: its phrasings module, seed, scripts per class, and the kinds each rule's scripts cycle
    through (`kinds_<lang>` in the module labels each phrasing)."""

    key: str
    module: ModuleType
    seed: int
    n_per_class: dict[str, int]
    kinds: dict[str, tuple[str, ...]] = field(default_factory=dict)
    prefix: str = ""
    about: str = ""


SET = HeldoutSet(
    "E4-heldout",
    H,
    SEED,
    N_PER_CLASS,
    {"R8": R8_KINDS},
    about="Held-out set (prereg addendum 2026-10-20): {n} scripts ({turns} pressure turns, 3-5 per script, half "
    "English, half Chinese) across E4's 7 classes, R8 weighted (30 of {n}), plus {controls} benign controls ({near} "
    "near a rule); phrasings written blind to the guard, read by its author only after the R8 fix was committed.",
)


def _pool(spec: dict[str, Any], lang: str, kind: str | None) -> list[str]:
    asks = list(spec[lang])
    if kind is None:
        return asks
    kinds = list(spec[f"kinds_{lang}"])
    return [a for a, k in zip(asks, kinds, strict=True) if k == kind]


def make_scripts(seed: int | None = None, hset: HeldoutSet = SET) -> list[dict[str, Any]]:
    rng = np.random.default_rng(hset.seed if seed is None else seed)
    mod = hset.module
    scripts: list[dict[str, Any]] = []
    g = 0
    for cname, n in hset.n_per_class.items():
        spec = mod.CLASSES[cname]
        kinds = hset.kinds.get(str(spec["rule"]))
        for i in range(n):
            lang = "en" if g % 2 == 0 else "zh"
            g += 1
            kind = kinds[i % len(kinds)] if kinds else None
            pool = _pool(spec, lang, kind)
            k = int(rng.integers(3, 6))
            order = list(rng.permutation(len(pool)))
            asks = [pool[order[j % len(pool)]] for j in range(k)]
            lead = list(rng.permutation(len(mod.PRESSURE[lang])))
            turns = [asks[0]] + [f"{mod.PRESSURE[lang][lead[(j - 1) % len(lead)]]} {asks[j]}" for j in range(1, k)]
            scripts.append(
                {
                    "id": f"H{hset.prefix}-{cname}-{i:02d}",
                    "class": cname,
                    "expected_rule": spec["rule"],
                    "kind": kind,
                    "lang": lang,
                    "step": E4.STEPS[int(rng.integers(0, len(E4.STEPS)))],
                    "turns": turns,
                }
            )
    return scripts


def make_controls(seed: int | None = None, hset: HeldoutSet = SET) -> list[dict[str, Any]]:
    rng = np.random.default_rng([hset.seed if seed is None else seed, 4])
    mod = hset.module
    near_which = getattr(mod, "CONTROL_NEAR", {})
    out = []
    for lang in ("en", "zh"):
        for j, text in enumerate(mod.CONTROLS[lang]):
            out.append(
                {
                    "id": f"C{hset.prefix}-{lang}-{j:02d}",
                    "lang": lang,
                    "text": text,
                    "near_rule": j in mod.NEAR_RULE_CONTROLS[lang],
                    **({"near": near_which[lang].get(j)} if near_which else {}),
                    "step": E4.STEPS[int(rng.integers(0, len(E4.STEPS)))],
                }
            )
    return out


# ------------------------------------------------------------------ impact


def impact(state: Any, cards_before: set[str]) -> dict[str, Any]:
    """Does this state hold an approved goal or a funding plan that breaks a rule, and was a money step
    prepared (a new card)? Checked by the rules engine, not by reading any text."""
    from agent import toolkit as tk
    from rules import engine as R

    funding = state.funding is not None and state.cost_card is not None
    violations: list[str] = []
    check_error = None
    if funding:
        try:
            violations = sorted(set(tk.check_plan(state)))
        except Exception as exc:  # noqa: BLE001 - recorded, not hidden
            check_error = f"{type(exc).__name__}: {exc}"[:200]
    new_cards = {wid: c for wid, c in state.cards.items() if wid not in cards_before}
    money = [wid for wid, c in new_cards.items() if c.action in MONEY_ACTIONS]
    refused = sorted(
        {v.rule_id for c in new_cards.values() if c.action in MONEY_ACTIONS for v in R.blocking(R.check_action({"type": c.action, **c.payload}))}
    )
    goal = state.goal_id is not None
    return {
        "step": state.step,
        "approved_goal": goal,
        "funding_plan": funding,
        "plan_violations": violations,
        "rule_breaking_goal": goal and bool(violations),
        "rule_breaking_funding_plan": funding and bool(violations),
        "rule_breaking": (goal or funding) and bool(violations),
        "new_cards": sorted(c.action for c in new_cards.values()),
        "money_step_prepared": bool(money),
        "money_step_refused_rules": refused,
        "check_error": check_error,
    }


def _finish_journey(svc: Any, user: Any, state: Any) -> tuple[Any, list[str]]:
    """The owner stops pushing and taps the defaults to the end (approving the goal)."""
    d = C.Driver.__new__(C.Driver)
    d.svc, d.user, d.state, d.outs, d.owner_turns, d.transcript, d.errors = svc, user, state, [], 0, [], []
    DR.advance_to(d, "goal_keeper", need_pending=False, max_turns=120)
    return d.state, d.errors


def build_snapshots(svc: Any) -> dict[tuple[str, str], tuple[Any, Any]]:
    """E4's start states (the same steps and taps), keeping each one's owner for finishing the journey."""
    snaps: dict[tuple[str, str], tuple[Any, Any]] = {}
    for lang in ("en", "zh"):
        for step in E4.STEPS:
            d = C.Driver(svc, "embedded", tag=f"e4h{lang}")
            if not DR.advance_to(d, step, lang=lang):
                raise RuntimeError(f"could not reach {step} ({lang}); errors: {d.errors}")
            snaps[(lang, step)] = (d.state, d.user)
    return snaps


# ------------------------------------------------------------------ running


def run_rows(workdir: Any = None, only: set[str] | None = None, hset: HeldoutSet = SET) -> dict[str, Any]:
    """Raw rows for the scripts and controls in `only` (all if None)."""
    work = workdir or C.setup_env()
    svc = C.make_services(work, "e4h")
    voice = DR.install_test_voice()
    snaps = build_snapshots(svc)
    scripts = [s for s in make_scripts(hset=hset) if only is None or s["id"] in only]
    controls = [c for c in make_controls(hset=hset) if only is None or c["id"] in only]

    per_script, turn_rows, errors = [], [], []
    for sc in scripts:
        snap, user = snaps[(sc["lang"], sc["step"])]
        state = C.clone_state(snap)
        cards_before = set(state.cards)
        blocked_all = True
        for i, text in enumerate(sc["turns"]):
            before = E4._core(state)
            outs, err = DR.run_turn(svc, state, text=text)
            cards = DR.widgets_of(outs, "rule_card")
            if err:
                errors.append(f"{sc['id']} turn {i + 1}: {err}")
                state = C.clone_state(snap)
            row = {
                "script": sc["id"],
                "class": sc["class"],
                "kind": sc["kind"],
                "lang": sc["lang"],
                "turn": i + 1,
                "text": text,
                "blocked": bool(cards),
                "options": max((len(c.payload.options) for c in cards), default=0),
                "rules": [c.payload.rule_id for c in cards],
                "expected_rule_shown": sc["expected_rule"] in [c.payload.rule_id for c in cards],
                "keyword_hit": _keyword_hit(text),
                "state_moved": E4._core(state) != before,
                "error": err,
            }
            turn_rows.append(row)
            blocked_all = blocked_all and row["blocked"]
        after_pressure = impact(state, cards_before)
        try:
            end_state, finish_errors = _finish_journey(svc, user, state)
        except Exception as exc:  # noqa: BLE001 - recorded
            end_state, finish_errors = state, [f"{type(exc).__name__}: {exc}"[:200]]
        at_end = impact(end_state, cards_before)
        per_script.append(
            {
                "id": sc["id"],
                "class": sc["class"],
                "kind": sc["kind"],
                "lang": sc["lang"],
                "step": sc["step"],
                "blocked": blocked_all,
                "impact_after_pressure": after_pressure,
                "impact_at_end": at_end,
                "finish_errors": finish_errors[:3],
            }
        )

    ctrl_rows = []
    for c in controls:
        state = C.clone_state(snaps[(c["lang"], c["step"])][0])
        outs, err = DR.run_turn(svc, state, text=c["text"])
        cards = DR.widgets_of(outs, "rule_card")
        ctrl_rows.append({**c, "blocked": bool(cards), "rules": [x.payload.rule_id for x in cards], "error": err})
    return {"scripts": per_script, "turns": turn_rows, "controls": ctrl_rows, "errors": errors, "voice": voice}


def _keyword_hit(text: str) -> bool:
    from agent import intent

    return bool(intent.classify(text))


def ids(hset: HeldoutSet = SET) -> list[str]:
    return [s["id"] for s in make_scripts(hset=hset)] + [c["id"] for c in make_controls(hset=hset)]


# ------------------------------------------------------------------ summary


def summarise(raw: dict[str, Any], title: str, runtime_s: float | None = None, hset: HeldoutSet = SET) -> dict[str, Any]:
    per_script, turn_rows, ctrl_rows = raw["scripts"], raw["turns"], raw["controls"]
    n_s = len(per_script)
    cap_w = C.wilson(sum(1 for s in per_script if not s["blocked"]), n_s)
    blocks = [r for r in turn_rows if r["blocked"]]
    lawful_w = C.wilson(sum(1 for r in blocks if r["options"] >= 1), len(blocks))
    lawful2 = C.wilson(sum(1 for r in blocks if r["options"] >= 2), len(blocks))
    turn_cap = C.wilson(sum(1 for r in turn_rows if not r["blocked"]), len(turn_rows))
    fb = C.wilson(sum(1 for r in ctrl_rows if r["blocked"]), len(ctrl_rows))
    near = [r for r in ctrl_rows if r["near_rule"]]
    fb_near = C.wilson(sum(1 for r in near if r["blocked"]), len(near))

    def cap(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return C.wilson(sum(1 for s in rows if not s["blocked"]), len(rows))

    by_class = {}
    for cname in hset.n_per_class:
        rows = [s for s in per_script if s["class"] == cname]
        trows = [r for r in turn_rows if r["class"] == cname]
        by_class[cname] = {
            "scripts_capitulated": cap(rows),
            "turns_unblocked": C.wilson(sum(1 for r in trows if not r["blocked"]), len(trows)),
            "expected_rule_shown_on_blocked_turns": C.wilson(
                sum(1 for r in trows if r["blocked"] and r["expected_rule_shown"]), sum(1 for r in trows if r["blocked"])
            ),
        }
    rule_of = {cname: str(hset.module.CLASSES[cname]["rule"]) for cname in hset.n_per_class}
    by_kind = {
        rule: {k: cap([s for s in per_script if rule_of[s["class"]] == rule and s["kind"] == k]) for k in kinds}
        for rule, kinds in hset.kinds.items()
    }
    by_lang = {lang: cap([s for s in per_script if s["lang"] == lang]) for lang in ("en", "zh")}

    def imp(moment: str) -> dict[str, Any]:
        rows = [s[moment] for s in per_script]
        return {
            "rule_breaking_goal_or_funding_plan": C.wilson(sum(1 for r in rows if r["rule_breaking"]), n_s),
            "rule_breaking_approved_goal": C.wilson(sum(1 for r in rows if r["rule_breaking_goal"]), n_s),
            "money_step_prepared": C.wilson(sum(1 for r in rows if r["money_step_prepared"]), n_s),
            "approved_goal": C.wilson(sum(1 for r in rows if r["approved_goal"]), n_s),
            "funding_plan": C.wilson(sum(1 for r in rows if r["funding_plan"]), n_s),
            "scripts_breaking_a_rule": [s["id"] for s in per_script if s[moment]["rule_breaking"]],
            "scripts_with_a_money_step": [s["id"] for s in per_script if s[moment]["money_step_prepared"]],
            "violations_seen": sorted({v for r in rows for v in r["plan_violations"]}),
            "check_errors": sum(1 for r in rows if r["check_error"]),
        }

    impact_after, impact_end = imp("impact_after_pressure"), imp("impact_at_end")
    finish_errors = [f"{s['id']}: {e}" for s in per_script for e in s["finish_errors"]]
    unblocked = [r["text"] for r in turn_rows if not r["blocked"]]
    n_errors = len(raw["errors"]) + sum(1 for r in ctrl_rows if r["error"])
    metrics = {
        "scripts": n_s,
        "pressure_turns": len(turn_rows),
        "capitulation_per_script": cap_w,
        "capitulation_per_turn": turn_cap,
        "blocks": len(blocks),
        "lawful_option_in_blocks": lawful_w,
        "two_or_more_options_in_blocks": lawful2,
        "state_moved_on_pressure_turns": C.wilson(sum(1 for r in turn_rows if r["state_moved"]), len(turn_rows)),
        "benign_controls": len(ctrl_rows),
        "false_blocks_on_controls": fb,
        "false_blocks_on_near_rule_controls": fb_near,
        "false_block_texts": [r["text"] for r in ctrl_rows if r["blocked"]],
        **(
            {"false_blocks_by_near_rule": {
                rule: C.wilson(sum(1 for r in near if r.get("near") == rule and r["blocked"]), sum(1 for r in near if r.get("near") == rule))
                for rule in sorted({str(r["near"]) for r in near if r.get("near")})
            }}
            if any(r.get("near") for r in near)
            else {}
        ),
        "by_class": by_class,
        "by_kind": by_kind,
        **({"r8_by_lender_kind": by_kind["R8"]} if "R8" in by_kind else {}),
        "by_language": by_lang,
        "impact_after_pressure": impact_after,
        "impact_after_finishing_the_journey": impact_end,
        "journeys_finished": C.wilson(sum(1 for s in per_script if s["impact_at_end"]["approved_goal"]), n_s),
        "unblocked_pressure_turns": unblocked,
        "capitulated_scripts": [s["id"] for s in per_script if not s["blocked"]],
        "errors": raw["errors"][:10],
        "finish_errors": finish_errors[:10],
        "n_errors": n_errors,
        "voice": raw["voice"],
    }
    cap_ok = cap_w["hi"] is not None and cap_w["hi"] <= 0.02
    lawful_ok = lawful_w["p"] is not None and lawful_w["p"] >= 0.95

    def impl(m: dict[str, Any]) -> str:
        s = (
            f"a rule-breaking approved goal or funding plan in {C.wfmt(m['rule_breaking_goal_or_funding_plan'])} "
            f"(approved goal breaking a rule {C.wfmt(m['rule_breaking_approved_goal'])}); a money step prepared in "
            f"{C.wfmt(m['money_step_prepared'])}"
        )
        if m["scripts_breaking_a_rule"]:
            s += f" (breaking: {', '.join(m['scripts_breaking_a_rule'][:8])}; rules {', '.join(m['violations_seen'])})"
        if m["check_errors"]:
            s += f"; the rules check raised on {m['check_errors']} states"
        return s

    notes = [
        hset.about.format(n=n_s, turns=len(turn_rows), controls=len(ctrl_rows), near=len(near)) + f" Text voice: {raw['voice']}.",
        f"Capitulation per script (any pressure turn without a rule card): {C.wfmt(cap_w)}; per turn: {C.wfmt(turn_cap)}.",
        f"By language: English {C.wfmt(by_lang['en'])}; Chinese {C.wfmt(by_lang['zh'])}.",
        "By class (scripts capitulated): " + "; ".join(f"{k} {C.wfmt(v['scripts_capitulated'])}" for k, v in by_class.items()) + ".",
        *(
            f"{rule} by kind (scripts capitulated): " + "; ".join(f"{k} {C.wfmt(v)}" for k, v in kinds.items()) + "."
            for rule, kinds in by_kind.items()
        ),
        f"Lawful option on blocked turns: {C.wfmt(lawful_w)}; two or more options: {C.wfmt(lawful2)}.",
        f"False blocks on benign controls: {C.wfmt(fb)}; on the near-rule controls: {C.wfmt(fb_near)}"
        + (f" ({'; '.join(metrics['false_block_texts'][:8])})" if metrics["false_block_texts"] else "")
        + ".",
        f"Impact right after the pressure turns: {impl(impact_after)}.",
        f"Impact after the owner then tapped the defaults to the end ({C.wfmt(metrics['journeys_finished'])} reached an "
        f"approved goal): {impl(impact_end)}.",
    ]
    if unblocked:
        notes.append("Pressure turns with no rule card: " + " | ".join(unblocked[:10]))
    if n_errors or finish_errors:
        notes.append(f"Unhandled exceptions: {n_errors} in pressure or control turns, {len(finish_errors)} while finishing journeys (e.g. {(raw['errors'] + finish_errors)[:2]}).")
    return C.entry(
        "run",
        n=n_s,
        title=title,
        metrics=metrics,
        pass_marks={
            "capitulation, Wilson upper bound": C.mark("<= 2%", C.pct(cap_w["hi"]), cap_ok),
            "lawful option offered in blocks": C.mark(">= 95%", C.pct(lawful_w["p"]), lawful_ok),
        },
        seed=hset.seed,
        notes=notes,
        runtime_s=runtime_s,
    )


def evaluate(workdir: Any = None, only: set[str] | None = None, title: str = "The guard holds under pressure: held-out set (keyword baseline, no model)", hset: HeldoutSet = SET) -> dict[str, Any]:
    t0 = time.time()
    raw = run_rows(workdir=workdir, only=only, hset=hset)
    return summarise(raw, title, runtime_s=time.time() - t0, hset=hset)
