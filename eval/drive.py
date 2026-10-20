"""Shared driving helpers for the evaluations: tap-through to a step, run a turn on a cloned state, and the
deterministic test voice used when no model is configured.

The orchestrator is always the real one (`AppServices().orchestrator.run`). These helpers decide only
what the simulated owner does next.
"""

from __future__ import annotations

import asyncio
from typing import Any

from eval import common as C

JOURNEY = ("welcome", "profile", "site", "cost", "funding", "goal_plan", "goal_keeper")


def install_test_voice() -> str:
    """No model: the product's deterministic test composer (each beat's key plus its required
    placeholders) and code-only understanding of free text (tests/conftest.py defaults).

    In a model arm (results/prereg.md addendum 2) the configured model understands free text; with
    WAYPOINT_EVAL_VOICE=model it also writes every message (E2-model, E1b)."""
    import os

    from agent import llm, voice

    llm.set_test_decider(None)
    if C.model_arm() and os.environ.get("WAYPOINT_EVAL_VOICE") == "model":
        voice.set_test_composer(None)
        return f"the configured model writes every message ({llm.model_label()})"
    voice.set_test_composer(voice.echo_composer)
    if C.model_arm():
        label = llm.model_label()
        return f"deterministic test composer; the configured model understands typed text ({label})"
    return "deterministic test composer (agent.voice.echo_composer; no model)"


def pick(options: list[dict[str, Any]], prefs: dict[str, str] | None, slot: str) -> str:
    values = [str(o["value"]) for o in options]
    want = (prefs or {}).get(slot)
    if want is not None and want in values:
        return want
    return values[0]


def tap_once(d: C.Driver, prefs: dict[str, str] | None = None, lang: str = "en") -> bool:
    """One sensible tap for the current state. False if there is nothing to tap."""
    st = d.state
    if st.step == "goal_plan" and st.cards:  # the approval card carries sensible defaults: approve it
        wid = max(st.cards, key=lambda k: int(k[1:]))
        d.run(event=_ev(wid, "approve", data={"card_hash": st.cards[wid].card_hash}))
        return True
    if st.step == "cost" and any(ln.status in ("pending", "check") for q in st.quotes for ln in q.lines):
        d.event("upload_prompt", "accept_all", st.quotes[-1].doc_id)
        return True
    if st.pending is not None:
        d.reply(pick(st.pending.options, prefs, st.pending.slot))
        return True
    if st.step == "welcome":
        if st.consent_feed is None and d.latest_widget_id("consent_card"):
            d.event("consent_card", "consent", True)
            return True
        return False
    if st.step in ("profile", "site", "cost", "funding") and d.latest_widget_id("confirm_card"):
        d.event("confirm_card", "confirm", "confirm")
        return True
    if st.step == "goal_plan" and st.cards:
        wid = max(st.cards, key=lambda k: int(k[1:]))
        d.run(event=_ev(wid, "approve", data={"card_hash": st.cards[wid].card_hash}))
        return True
    return False


def _ev(wid: str, event: str, value: Any = None, data: dict[str, Any] | None = None) -> Any:
    from agent.widgets import WidgetEvent

    return WidgetEvent(widget_id=wid, event=event, value=value, data=data or {})  # type: ignore[arg-type]


def advance_to(
    d: C.Driver,
    step: str,
    prefs: dict[str, str] | None = None,
    lang: str = "en",
    need_pending: bool = True,
    max_turns: int = 80,
) -> bool:
    """Tap through until the journey is at `step` (with a pending question if asked). True on success."""
    if not d.state.started:
        d.state.lang = lang  # the interface's language (the toggle); the chat greets in it
        d.run(init=True)
    target = JOURNEY.index(step)
    for _ in range(max_turns):
        st = d.state
        here = JOURNEY.index(st.step)
        if here == target and (not need_pending or st.pending is not None):
            return True
        if here > target:
            return False
        if not tap_once(d, prefs, lang):
            return False
    return False


def run_turn(
    svc: Any, state: Any, text: str | None = None, event: Any = None
) -> tuple[list[Any], str | None]:
    """Run one turn on `state` (mutated in place). Returns (outputs, error)."""
    try:
        outs = asyncio.run(svc.orchestrator.run(state, text=text, event=event, init=False))
        return outs, None
    except Exception as exc:  # noqa: BLE001 - an unhandled exception is recorded as a result
        return [], f"{type(exc).__name__}: {exc}"[:300]


def widgets_of(outs: list[Any], wtype: str | None = None) -> list[Any]:
    return [
        o.widget
        for o in outs
        if o.kind == "widget" and o.widget is not None and (wtype is None or o.widget.payload.type == wtype)
    ]
