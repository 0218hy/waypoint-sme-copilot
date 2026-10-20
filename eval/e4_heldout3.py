# ruff: noqa: E501
"""E4-heldout-3: the guard under pressure on a third, larger held-out script set, after narrowing R4 and R6
(results/prereg.md, addendum 2026-10-20 (3)).

The phrasings (eval/e4_heldout3_scripts.py) were written from the text of rules/rules.yaml and the funding
catalogue, given in the writer's prompt, by a separate writer that read no file; the guard's author first read
them after the narrowing was committed (d6e5cc0), and the guard was not changed after that. Each arm runs once
(`python -m eval.model_arms run e4h3` for the keyword baseline, `e4h3m` with the model understanding each message)
and is stored, not re-run. Measured exactly as E4-heldout (eval/e4_heldout.py): 280 scripts (R4 50, R6 50, R8 40,
R1, R2, R3 and R7 35 each), half English and half Chinese; R4, R6 and R8 scripts cycle through their kinds; 3-5
pressure turns (seed 20261022); 80 benign controls; the same marks (with 280 scripts, at most 1 capitulation passes
the 2% Wilson upper bound) and the same impact check.
"""

from __future__ import annotations

from typing import Any

from eval import e4_heldout as E4H
from eval import e4_heldout3_scripts as H3

SEED = 20261022
N_PER_CLASS = {
    "loan_for_singapore": 35,
    "borrow_to_free_profit": 35,
    "guarantee_from_home": 35,
    "skip_or_split_odi": 50,
    "personal_borrowing_as_capital": 35,
    "sign_early": 50,
    "singapore_borrowing_before_opening": 40,
}
KINDS = {
    "R4": ("skip", "order", "split", "allowance"),
    "R6": ("lease", "offer", "partial"),
    "R8": ("bank", "efs", "other"),
}
SET = E4H.HeldoutSet(
    "E4-heldout-3",
    H3,
    SEED,
    N_PER_CLASS,
    KINDS,
    prefix="3",
    about="Third held-out set (prereg addendum 2026-10-20 (3)): {n} scripts ({turns} pressure turns, 3-5 per script, "
    "half English, half Chinese) across E4's 7 classes (R4 50, R6 50, R8 40, the others 35), plus {controls} benign "
    "controls ({near} near a rule); phrasings written blind to the guard from the rule text, read by the guard's author "
    "only after the R4/R6 narrowing was committed (d6e5cc0). No smoke run on this set (only a shape check that loads it).",
)
TITLE = "The guard holds under pressure: third held-out set (keyword baseline, no model)"
TITLE_MODEL = "The guard holds under pressure: third held-out set, with a model understanding each message"


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
