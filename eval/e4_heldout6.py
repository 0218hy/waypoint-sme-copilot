# ruff: noqa: E501
"""E4-heldout-6: end-to-end harm under pressure on a sixth held-out set (results/prereg.md, addendum 2026-10-20 (13)),
after closing the two product harm paths E4-heldout-5 exposed (an inflated owner figure used over the bank feed; a
funding plan left confirmed after going back) and the max_turns fallback confirming a step for the owner.

The harness is E4-heldout-5's, unchanged (eval/e4_heldout5.py: the same harm definition, adversarial finisher, judge,
rubric and marks); this module only supplies the set: its phrasings (eval/e4_heldout6_scripts.py, written blind by a
separate writer after this code was frozen and committed), seed and class weights. Two path classes (R5) are new:
`inflate_feed_figures` and `change_after_confirm`. Harm (primary) counts all 300 scripts; capitulation (secondary)
counts the 210 scripts of E4's seven rule classes, since for a path script a rule card is not the only right answer.

Each arm runs once: `python -m eval.model_arms run e4h6` (keyword baseline) and `e4h6m` in slices, then `combine`.
"""

from __future__ import annotations

from typing import Any

from eval import e4_heldout5 as E5

SEED = 20261026
N_PER_CLASS = {
    "borrow_to_free_profit": 75,
    "inflate_feed_figures": 50,
    "change_after_confirm": 40,
    "loan_for_singapore": 40,
    "skip_or_split_odi": 25,
    "personal_borrowing_as_capital": 20,
    "sign_early": 20,
    "guarantee_from_home": 15,
    "singapore_borrowing_before_opening": 15,
}
PATH_CLASSES = frozenset({"inflate_feed_figures", "change_after_confirm"})
RULE_OF = {**E5.RULE_OF, "inflate_feed_figures": "R5", "change_after_confirm": "R5"}
PATH_STEPS = ("cost", "funding", "goal_plan")
TITLE = "End-to-end harm under pressure: sixth held-out set, after closing two harm paths (keyword baseline, no model)"
TITLE_MODEL = "End-to-end harm under pressure: sixth held-out set, after closing two harm paths, with a model understanding and replying"
ABOUT = (
    "Sixth held-out set (prereg addendum 2026-10-20 (13)): {n} scripts ({turns} script pressure turns, 3-5 per script, "
    "{zh} in Chinese), weighted to R2 (75) and to two R5 harm paths (50 inflating a figure the bank feed shows, 40 going "
    "back to change an input and keep the confirmation), plus E4's other classes, and {controls} benign controls "
    "({near} near a rule); phrasings written blind after the code measured here was frozen and committed. The harness, "
    "harm definition, finisher, judge and rubric are E4-heldout-5's (addendum (8)). No smoke run on this set (only a "
    "shape check that loads it)."
)
SPEC = E5.SetSpec(
    module="eval.e4_heldout6_scripts",
    seed=SEED,
    n_per_class=N_PER_CLASS,
    rule_of=RULE_OF,
    tag="6",
    about=ABOUT,
    path_classes=PATH_CLASSES,
    path_steps=PATH_STEPS,
)


def make_scripts(seed: int | None = None) -> list[dict[str, Any]]:
    return E5.make_scripts(seed, spec=SPEC)


def make_controls(seed: int | None = None) -> list[dict[str, Any]]:
    return E5.make_controls(seed, spec=SPEC)


def ids() -> list[str]:
    return E5.ids(spec=SPEC)


def run_rows(workdir: Any = None, only: set[str] | None = None) -> dict[str, Any]:
    return E5.run_rows(workdir=workdir, only=only, spec=SPEC)


def judge(raw: dict[str, Any]) -> dict[str, Any]:
    return E5.judge(raw)


def summarise(raw: dict[str, Any], judged: dict[str, Any] | None, title: str, runtime_s: float | None = None) -> dict[str, Any]:
    return E5.summarise(raw, judged, title, runtime_s=runtime_s, spec=SPEC)


def evaluate(workdir: Any = None, only: set[str] | None = None, title: str = TITLE, with_judge: bool = True) -> dict[str, Any]:
    return E5.evaluate(workdir=workdir, only=only, title=title, with_judge=with_judge, spec=SPEC)
