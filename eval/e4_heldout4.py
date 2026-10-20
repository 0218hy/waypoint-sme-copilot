# ruff: noqa: E501
"""E4-heldout-4: the guard under pressure on a fourth held-out script set, weighted to R2 and R1, after the R2/R1
fix (results/prereg.md, addendum 2026-10-20 (4)).

The phrasings (eval/e4_heldout4_scripts.py) were written from the text of rules/rules.yaml and the funding routes,
given in the writer's prompt, by a separate writer that read no file; the guard's author first read them after the
fix was committed (300c1dc), and the guard was not changed after that. The writer's file is unchanged but for a
first line `# ruff: noqa: E501` (its data, from the second line on, has SHA-256 27f21cc3…a779). Each arm runs once
(`python -m eval.model_arms run e4h4` for the keyword baseline, `e4h4m` with the model understanding each message)
and is stored, not re-run. Measured exactly as E4-heldout (eval/e4_heldout.py): 300 scripts (R2 70, R1 60, R4 40,
R6 40, R3, R7 and R8 30 each), half English and half Chinese; R1, R2, R4, R6 and R8 scripts cycle through their
kinds; 3-5 pressure turns (seed 20261023); 100 benign controls; the same marks (with 300 scripts, at most 1
capitulation passes the 2% Wilson upper bound) and the same impact check.
"""

from __future__ import annotations

from typing import Any

from eval import e4_heldout as E4H
from eval import e4_heldout4_scripts as H4

SEED = 20261023
N_PER_CLASS = {
    "loan_for_singapore": 60,
    "borrow_to_free_profit": 70,
    "guarantee_from_home": 30,
    "skip_or_split_odi": 40,
    "personal_borrowing_as_capital": 30,
    "sign_early": 40,
    "singapore_borrowing_before_opening": 30,
}
KINDS = {
    "R1": ("shop", "pot", "company", "indirect"),
    "R2": ("keep", "bills", "usual"),
    "R4": ("skip", "order", "split", "allowance"),
    "R6": ("lease", "offer", "partial"),
    "R8": ("bank", "efs", "other"),
}
SET = E4H.HeldoutSet(
    "E4-heldout-4",
    H4,
    SEED,
    N_PER_CLASS,
    KINDS,
    prefix="4",
    about="Fourth held-out set (prereg addendum 2026-10-20 (4)): {n} scripts ({turns} pressure turns, 3-5 per script, "
    "half English, half Chinese) across E4's 7 classes, weighted to R2 (70) and R1 (60), plus {controls} benign "
    "controls ({near} near a rule); phrasings written blind to the guard from the rule text, read by the guard's author "
    "only after the R2/R1 fix was committed (300c1dc). No smoke run on this set (only a shape check that loads it).",
)
TITLE = "The guard holds under pressure: fourth held-out set (keyword baseline, no model)"
TITLE_MODEL = "The guard holds under pressure: fourth held-out set, with a model understanding each message"


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
