# ruff: noqa: E501
"""E4-heldout-2: the guard under pressure on a second held-out script set, after the R4 and R6 fix
(results/prereg.md, addendum 2026-10-20 (2)).

The phrasings (eval/e4_heldout2_scripts.py) were written from the text of rules/rules.yaml and the funding
catalogue, given in the writer's prompt, by a separate writer that read no file; the guard's author first read
them after the R4/R6 fix was committed (6d3f36f), and the guard was not changed after that. Each arm runs once
(`python -m eval.model_arms run e4h2` for the keyword baseline, `e4h2m` with the model understanding each message)
and is stored, not re-run. Measured exactly as E4-heldout (eval/e4_heldout.py): 120 scripts, R4 30, R6 30, each
other E4 class 12, half English and half Chinese; R4 scripts cycle through four kinds, R6 scripts through three;
3-5 pressure turns (seed 20261021); 40 benign controls; the same marks and the same impact check.
"""

from __future__ import annotations

from typing import Any

from eval import e4_heldout as E4H
from eval import e4_heldout2_scripts as H2

SEED = 20261021
N_PER_CLASS = {
    "loan_for_singapore": 12,
    "borrow_to_free_profit": 12,
    "guarantee_from_home": 12,
    "skip_or_split_odi": 30,
    "personal_borrowing_as_capital": 12,
    "sign_early": 30,
    "singapore_borrowing_before_opening": 12,
}
KINDS = {"R4": ("skip", "order", "split", "allowance"), "R6": ("lease", "offer", "partial")}
SET = E4H.HeldoutSet(
    "E4-heldout-2",
    H2,
    SEED,
    N_PER_CLASS,
    KINDS,
    prefix="2",
    about="Second held-out set (prereg addendum 2026-10-20 (2)): {n} scripts ({turns} pressure turns, 3-5 per script, "
    "half English, half Chinese) across E4's 7 classes, weighted to R4 (30 of {n}) and R6 (30), plus {controls} benign "
    "controls ({near} near a rule); phrasings written blind to the guard from the rule text, read by the guard's author "
    "only after the R4/R6 fix was committed (6d3f36f). No smoke run on this set (only a shape check that loads it).",
)
TITLE = "The guard holds under pressure: second held-out set (keyword baseline, no model)"
TITLE_MODEL = "The guard holds under pressure: second held-out set, with a model understanding each message"


def make_scripts(seed: int | None = None) -> list[dict[str, Any]]:
    return E4H.make_scripts(seed, SET)


def make_controls(seed: int | None = None) -> list[dict[str, Any]]:
    return E4H.make_controls(seed, SET)


def ids() -> list[str]:
    return E4H.ids(SET)


def run_rows(workdir: Any = None, only: set[str] | None = None) -> dict[str, Any]:
    return E4H.run_rows(workdir=workdir, only=only, hset=SET)


def summarise(raw: dict[str, Any], title: str = TITLE, runtime_s: float | None = None) -> dict[str, Any]:
    return E4H.summarise(raw, title, runtime_s=runtime_s, hset=SET)


def evaluate(workdir: Any = None, only: set[str] | None = None, title: str = TITLE) -> dict[str, Any]:
    return E4H.evaluate(workdir=workdir, only=only, title=title, hset=SET)
