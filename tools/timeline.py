"""Timeline (SPEC §6.7): milestones in legal order with likely, latest-safe and act-by weeks.

- likely: the plan model's median completion week;
- latest-safe: the latest completion that does not move the likely opening, i.e. the likely opening minus
  the likely durations of the steps still to come (never earlier than likely: a step already on the
  critical path has no slack);
- act-by: latest-safe minus the step's own likely duration (when it must be started), not before week 0.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from tools import params as P
from tools.models import Milestone, MilestoneStatus, PlanResult
from tools.plan import week_to_date


def _defs() -> list[dict[str, Any]]:
    return [dict(m) for m in P.items("timeline_milestones")]


def _likely(key: str | None) -> int:
    return 0 if key is None else round(P.tri(key).likely)


def _downstream(defs: list[dict[str, Any]], i: int) -> int:
    """Likely weeks from milestone i's completion to opening along the chain."""
    ids = [d["id"] for d in defs]
    after = ids[i + 1 :]
    total = 0
    for d in defs[i + 1 :]:
        if d["id"] in ("setup_transfer", "first_transfer", "opening", "hiring"):
            continue  # transfers take no time of their own; hiring runs alongside the fit-out
        total += _likely(d.get("duration"))
    if ids[i] in ("lender_consent", "odi_filing", "bank_registration") and "incorporate" in after:
        total += _likely("incorporation_weeks")  # incorporation runs before the account opening
    return total


def build_timeline(result: PlanResult, lang: str = "en") -> list[Milestone]:
    defs = _defs()
    weeks = result.milestone_weeks
    opening = result.open_likely_week
    out: list[Milestone] = []
    for i, d in enumerate(defs):
        mid = str(d["id"])
        likely = weeks.get(mid)
        if likely is None:
            continue  # not reached in the median run: the plan doesn't open in the horizon
        if opening is None:
            latest = likely
        elif mid == "hiring":
            latest = max(likely, opening)  # a parallel branch: it only has to be done by opening day
        else:
            latest = max(likely, opening - _downstream(defs, i))
        own = _likely(d.get("duration"))
        if mid == "incorporate":
            own += _likely("incorporation_weeks")
        act_by = max(0, latest - own)
        label = d["label_zh" if lang == "zh" else "label_en"]
        who = d["who_zh" if lang == "zh" else "who_en"]
        out.append(
            Milestone(
                id=mid,
                order=i + 1,
                label=str(label),
                who=str(who),
                likely_week=likely,
                latest_safe_week=latest,
                act_by_week=act_by,
            )
        )
    return out


def milestone_status(m: Milestone, today_week: int) -> MilestoneStatus:
    if m.done_at is not None:
        return MilestoneStatus.DONE
    if today_week > m.latest_safe_week:
        return MilestoneStatus.LATE
    if today_week >= m.act_by_week:
        return MilestoneStatus.DUE
    return MilestoneStatus.UPCOMING


def milestone_dates(m: Milestone, start: date) -> dict[str, date]:
    return {
        "likely": week_to_date(start, m.likely_week),
        "latest_safe": week_to_date(start, m.latest_safe_week),
        "act_by": week_to_date(start, m.act_by_week),
    }


# ------------------------------------------------------------------ marking steps done (SPEC §7.4)


def prerequisites(mid: str) -> list[str]:
    """The steps that must be done before `mid` can be (legal order; params `after`)."""
    for d in _defs():
        if d["id"] == mid:
            return [str(x) for x in d.get("after") or []]
    raise KeyError(mid)


def is_money_step(mid: str) -> bool:
    """A step the owner releases money for: marking it done always needs the owner's confirmation."""
    return any(d["id"] == mid and bool(d.get("money_step")) for d in _defs())


def can_mark_done(milestones: list[Milestone], mid: str) -> tuple[bool, str, list[str]]:
    """Whether the owner may mark `mid` done now: (ok, reason, the steps still missing before it).

    Reasons: `ok`, `unknown` (not one of this goal's milestones), `already_done`, `out_of_order`.
    """
    by_id = {m.id: m for m in milestones}
    m = by_id.get(mid)
    if m is None:
        return False, "unknown", []
    if m.done_at is not None or m.status == MilestoneStatus.DONE:
        return False, "already_done", []
    missing = [
        p
        for p in prerequisites(mid)
        if p in by_id and by_id[p].done_at is None and by_id[p].status != MilestoneStatus.DONE
    ]
    if missing:
        return False, "out_of_order", missing
    return True, "ok", []


def mark_done(milestones: list[Milestone], mid: str, on: date) -> list[Milestone]:
    """The milestones with `mid` done on `on`. Raises ValueError if it can't be marked done now."""
    ok, reason, _missing = can_mark_done(milestones, mid)
    if not ok:
        raise ValueError(reason)
    return [
        m.model_copy(update={"status": MilestoneStatus.DONE, "done_at": on}) if m.id == mid else m
        for m in milestones
    ]


def carry_done(old: list[Milestone], new: list[Milestone]) -> list[Milestone]:
    """A rebuilt timeline keeps the steps the owner already marked done."""
    done = {m.id: m.done_at for m in old if m.done_at is not None}
    return [
        m.model_copy(update={"status": MilestoneStatus.DONE, "done_at": done[m.id]}) if m.id in done else m
        for m in new
    ]


def next_open(milestones: list[Milestone]) -> Milestone | None:
    """The first step in legal order that isn't done yet."""
    return next((m for m in sorted(milestones, key=lambda m: m.order) if m.done_at is None), None)
