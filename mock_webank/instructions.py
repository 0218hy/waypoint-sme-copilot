"""Mock WeBank standing instructions (SPEC §7.4, §8.2): what Waypoint prepares for the owner to sign.

Waypoint never moves money. Approving the `recurring_setaside` card records a *prepared* monthly
transfer here, "pending your signature in WeBank"; only the owner's signature in WeBank's own flow
(simulated in the demo by "Sign in WeBank") makes it active, and WeBank then runs it: the fixed amount
in the first week of each month, re-checked every month and skipped for that month while borrowing is above
its usual level (R2) or if it would leave the operating account below `pause_below_cny` (floor + buffer,
R5). The simulated feed applies exactly this rule (`sim/chen.py` `_cash_and_loan`). Labelled
simulated. In memory, like the mock feed; Waypoint keeps its own copy on the goal record and restores
it here after a restart.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

PENDING, SIGNED, SUPERSEDED, REPLACED = "pending_signature", "signed", "superseded", "replaced"
_BY_OWNER: dict[str, dict[str, dict[str, Any]]] = {}


def prepare(owner_id: str, terms: dict[str, Any], card_hash: str) -> dict[str, Any]:
    """Record a prepared monthly transfer. An earlier unsigned one is superseded; a signed one stays
    active until the owner signs this one."""
    mine = _BY_OWNER.setdefault(owner_id, {})
    for rec in mine.values():
        if rec["status"] == PENDING:
            rec["status"] = SUPERSEDED
    rec = {
        "id": "si_" + secrets.token_hex(6),
        "kind": "recurring_setaside",
        "status": PENDING,
        "terms": dict(terms),
        "card_hash": card_hash,
        "prepared_at": datetime.now(UTC).isoformat(),
        "signed_at": None,
        "simulated": True,
    }
    mine[rec["id"]] = rec
    return dict(rec)


def sign(owner_id: str, instruction_id: str) -> dict[str, Any] | None:
    """The owner signs in WeBank's own flow (simulated). Only a pending instruction can be signed."""
    mine = _BY_OWNER.get(owner_id, {})
    rec = mine.get(instruction_id)
    if rec is None or rec["status"] != PENDING:
        return None
    for other in mine.values():
        if other["status"] == SIGNED:
            other["status"] = REPLACED
    rec["status"] = SIGNED
    rec["signed_at"] = datetime.now(UTC).isoformat()
    return dict(rec)


def get(owner_id: str, instruction_id: str) -> dict[str, Any] | None:
    rec = _BY_OWNER.get(owner_id, {}).get(instruction_id)
    return dict(rec) if rec else None


def for_owner(owner_id: str) -> list[dict[str, Any]]:
    return [dict(r) for r in _BY_OWNER.get(owner_id, {}).values()]


def restore(owner_id: str, rec: dict[str, Any]) -> None:
    """Put back an instruction Waypoint has on record (the mock bank lives in memory)."""
    _BY_OWNER.setdefault(owner_id, {}).setdefault(rec["id"], dict(rec))


def reset(owner_id: str | None = None) -> None:
    if owner_id is None:
        _BY_OWNER.clear()
    else:
        _BY_OWNER.pop(owner_id, None)
