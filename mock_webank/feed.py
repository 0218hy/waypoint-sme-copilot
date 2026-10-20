"""Mock WeBank feed (SPEC §1, §10): serves Chen's simulated snapshot, optionally with a scripted shock.

Labelled simulated. In-memory scenario registry per owner (the demo's "advance the clock" moves `as_of`).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sim.chen import BASE_AS_OF, DEFAULT_SEED, GoalTransfers, Scenario, generate_chen
from sim.shocks import Shock, demo_dip
from tools.models import FeedSnapshot

_SCENARIOS: dict[str, Scenario] = {}
_SEED = [DEFAULT_SEED]  # the persona's seed for every owner (only the demo seed search changes it)


def use_seed(seed: int) -> None:
    """Serve Chen from another seed (sim/demo_seed.py tries candidates); clears every scenario."""
    _SEED[0] = seed
    _SCENARIOS.clear()


def _new() -> Scenario:
    return Scenario(seed=_SEED[0])


def set_scenario(owner_id: str, shocks: Sequence[Shock] = (), seed: int | None = None) -> None:
    seed = _SEED[0] if seed is None else seed
    cur = _SCENARIOS.get(owner_id, Scenario(seed=seed))
    _SCENARIOS[owner_id] = Scenario(seed=seed, shocks=tuple(shocks), goal=cur.goal, persona=cur.persona)


def add_shocks(owner_id: str, shocks: Sequence[Shock]) -> None:
    cur = _SCENARIOS.get(owner_id, _new())
    _SCENARIOS[owner_id] = Scenario(
        seed=cur.seed, shocks=cur.shocks + tuple(shocks), goal=cur.goal, persona=cur.persona
    )


def register_goal(
    owner_id: str, start: date, spare_moved_cny: Decimal, monthly_setaside_cny: Decimal
) -> None:
    """Once the goal starts, the feed shows spare cash moved to the pot and the monthly set-aside."""
    cur = _SCENARIOS.get(owner_id, _new())
    goal = GoalTransfers(start=start, spare_moved_cny=spare_moved_cny, monthly_cny=monthly_setaside_cny)
    _SCENARIOS[owner_id] = Scenario(seed=cur.seed, shocks=cur.shocks, goal=goal, persona=cur.persona)


def apply_demo_dip(
    owner_id: str, plan_start: date = BASE_AS_OF, after_weeks: int = 8, shops: int = 4, pct: float = 0.20
) -> None:
    """The pitch's moment 6: sales −20% at four shops from week 8."""
    add_shocks(owner_id, demo_dip(plan_start, after_weeks, shops, pct))


def reset(owner_id: str | None = None) -> None:
    if owner_id is None:
        _SCENARIOS.clear()
    else:
        _SCENARIOS.pop(owner_id, None)


def scenario_for(owner_id: str) -> Scenario:
    return _SCENARIOS.get(owner_id, _new())


def get_feed(owner_id: str, as_of: date = BASE_AS_OF) -> FeedSnapshot:
    """The (mock) feed snapshot for an owner on a date. Every owner gets Chen in the demo."""
    return generate_chen(as_of, scenario_for(owner_id))


def accounts(owner_id: str) -> dict[str, str]:
    """The company's (fictional) WeBank accounts: the operating account and its own savings sub-account
    (the pot). Deterministic per owner; simulated, like everything the mock feed serves."""
    import hashlib

    h = int(hashlib.sha256(owner_id.encode()).hexdigest()[:12], 16)
    return {
        "operating": f"6236 0000 {h % 10_000:04d} {(h // 10_000) % 10_000:04d}",
        "savings": f"6236 0001 {(h // 10**8) % 10_000:04d} {(h // 10**4 + 7) % 10_000:04d}",
    }
