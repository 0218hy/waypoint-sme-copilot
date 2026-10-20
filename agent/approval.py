"""Code-built approval cards (SPEC §8.2).

A card's hash covers the action, its canonical payload (amounts, hashed account, plan terms),
the owner, a nonce and an expiry, canonicalised with RFC 8785 (JCS). At approval the server
rebuilds the payload from the *current* state; any difference, a reused nonce or an expired
card refuses the approval.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import rfc8785
from pydantic import BaseModel

Action = Literal["create_goal", "revise_goal", "recurring_setaside"]


class PendingCard(BaseModel):
    action: Action
    owner_id: str
    payload: dict[str, Any]
    nonce: str
    expires_at: datetime
    card_hash: str
    widget_id: str


def account_hash(account_no: str) -> str:
    return hashlib.sha256(account_no.encode()).hexdigest()[:16]


def card_hash(action: str, owner_id: str, payload: dict[str, Any], nonce: str, expires_at: datetime) -> str:
    body = {
        "action": action,
        "owner": owner_id,
        "payload": payload,
        "nonce": nonce,
        "expires_at": expires_at.astimezone(UTC).isoformat(),
    }
    return hashlib.sha256(rfc8785.dumps(body)).hexdigest()  # type: ignore[arg-type]


def new_card(
    action: Action, owner_id: str, payload: dict[str, Any], widget_id: str, ttl_minutes: int = 30
) -> PendingCard:
    nonce = secrets.token_urlsafe(16)
    expires = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    return PendingCard(
        action=action,
        owner_id=owner_id,
        payload=payload,
        nonce=nonce,
        expires_at=expires,
        card_hash=card_hash(action, owner_id, payload, nonce, expires),
        widget_id=widget_id,
    )


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str


def check_approval(
    card: PendingCard,
    presented_hash: str,
    rebuilt_payload: dict[str, Any],
    used_nonces: set[str],
    now: datetime | None = None,
) -> Verdict:
    now = now or datetime.now(UTC)
    if card.nonce in used_nonces:
        return Verdict(False, "nonce_reused")
    if now > card.expires_at:
        return Verdict(False, "expired")
    if presented_hash != card.card_hash:
        return Verdict(False, "hash_mismatch")
    rebuilt = card_hash(card.action, card.owner_id, rebuilt_payload, card.nonce, card.expires_at)
    if rebuilt != card.card_hash:
        return Verdict(False, "state_changed")
    return Verdict(True, "ok")
