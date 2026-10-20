"""Repairs (SPEC §6.8): a fixed catalogue of fixes, each re-simulated (same seed) and checked by every rule.
Returns the best 2-3 by new likely opening week. The AI never invents a repair.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Literal

from rules.engine import check_plan, is_recommendable
from tools import params as P
from tools.figures import dec
from tools.models import CostCard, FeedSnapshot, FundingPlan, PlanResult, Profile, Repair
from tools.plan import build_inputs, find_wall, simulate_plan

RepairKind = Literal[
    "raise_share", "add_savings", "cheaper_unit", "rent_free", "stage_contractor", "move_target"
]
Candidate = tuple[RepairKind, dict[str, str], FundingPlan, CostCard]


def _candidates(
    card: CostCard, plan: FundingPlan, wall: Decimal, alternatives: Sequence[CostCard]
) -> list[Candidate]:
    out: list[Candidate] = []
    step = P.num("wall_step")
    shares = sorted({min(plan.setaside_share + step, wall), wall})
    for s in shares:
        if s > plan.setaside_share:
            out.append(
                (
                    "raise_share",
                    {"setaside_share": str(s)},
                    plan.model_copy(update={"setaside_share": s}),
                    card,
                )
            )
    add = P.num("repair_savings_step_cny")
    out.append(
        (
            "add_savings",
            {"own_savings_cny": str(plan.own_savings_cny + add), "added_cny": str(add)},
            plan.model_copy(
                update={"own_savings_cny": plan.own_savings_cny + add, "own_savings_source": "savings"}
            ),
            card,
        )
    )
    for alt in alternatives:
        if alt.unit_id != card.unit_id and alt.total_likely_sgd < card.total_likely_sgd:
            out.append(
                (
                    "cheaper_unit",
                    {"unit_id": alt.unit_id, "total_likely_sgd": str(alt.total_likely_sgd)},
                    plan,
                    alt,
                )
            )
    if plan.rent_free_months < P.num("rent_free_months_max"):
        rf = plan.rent_free_months + 1
        out.append(
            (
                "rent_free",
                {"rent_free_months": str(rf)},
                plan.model_copy(update={"rent_free_months": rf}),
                card,
            )
        )
    # Staged contractor payments are not a repair: R6 puts the whole fit-out in Singapore before signing,
    # so staging can't move any date (SPEC §6.4, §6.8).
    out.append(("move_target", {}, plan, card))
    return out


def find_repairs(
    src: FeedSnapshot | Profile,
    card: CostCard,
    plan: FundingPlan,
    *,
    alternatives: Sequence[CostCard] = (),
    seed: int | None = None,
    start_date: date | None = None,
    unit_available_from: date | None = None,
    feed: FeedSnapshot | None = None,
) -> list[Repair]:
    """Try each fix, keep those passing every rule, return the best by new likely week (then floor risk)."""
    seed = P.default_seed() if seed is None else seed
    runs = P.inum("repair_runs")
    wall = find_wall(build_inputs(src, card, plan, start_date, unit_available_from), seed=seed)
    feed = feed if feed is not None else (src if isinstance(src, FeedSnapshot) else None)
    scored: list[tuple[float, float, Repair]] = []
    for i, (kind, prm, new_plan, new_card) in enumerate(_candidates(card, plan, wall, alternatives)):
        res: PlanResult = simulate_plan(
            src, new_card, new_plan, runs, seed, start_date, unit_available_from=unit_available_from
        )
        ok = is_recommendable(check_plan(new_plan, res, new_card, None, feed))
        if not ok:
            continue
        rep = Repair(
            id=f"rep-{i}-{kind}",
            kind=kind,
            params=prm,
            new_open_likely_week=res.open_likely_week,
            new_open_p95_week=res.open_p95_week,
            new_floor_risk=res.floor_risk,
            rules_ok=ok,
        )
        key = math.inf if res.open_likely_week is None else float(res.open_likely_week)
        scored.append((key, float(res.floor_risk), rep))
    scored.sort(key=lambda x: (x[0], x[1], x[2].kind == "move_target"))
    best: dict[str, Repair] = {}
    for _, _, rep in scored:
        best.setdefault(rep.kind, rep)  # one per kind: the best of each
    ranked = sorted(
        best.values(),
        key=lambda r: (
            math.inf if r.new_open_likely_week is None else r.new_open_likely_week,
            float(r.new_floor_risk),
        ),
    )
    return ranked[: P.inum("repair_max")]


def repair_share(rep: Repair) -> Decimal | None:
    v = rep.params.get("setaside_share")
    return None if v is None else dec(v)
