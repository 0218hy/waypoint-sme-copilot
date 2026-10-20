# ruff: noqa: E501
"""E1b: simulated owners played by a model (results/prereg.md, addendum 2: Claude in every role, a
single-family deviation; TODO: an owner from another model family).

The first 20 of E1a's fixed personas. Each owner gets a brief (its business, its preferences, its
language) and, every turn, only what the owner would see: the messages from the last turn and the
buttons on screen. It taps one button or types a message. The agent is the real orchestrator with the
configured model writing every message and understanding typed text. Measured by code: reached a
confirmed goal; owner turns; where an owner stopped. Cap: 40 owner turns.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, Field

from eval import common as C
from eval import drive as DR
from eval import e1a_journey as E1A

N = 20
MAX_TURNS = 40

LABELS = {
    "customers": {"young_adults": "young adults", "students": "students", "office_workers": "office workers",
                  "families": "families", "tourists": "tourists"},
    "budget": {"b1": "about S$200k-300k", "b2": "about S$300k-450k", "b3": "about S$450k-600k",
               "not_sure": "not sure yet"},
    "window": {"6_12": "within a year", "12_18": "in a year to eighteen months", "18_24": "in about two years",
               "no_rush": "no rush"},
    "priority": {"near_customers": "being near your kind of customer", "foot_traffic": "lots of foot traffic",
                 "low_rent": "low rent"},
    "fitout": {"basic": "a basic fit-out", "standard": "a standard fit-out", "premium": "a premium fit-out"},
    "manager": {"hire_local": "hire a manager in Singapore", "send_own": "send your own manager from Shenzhen"},
    "quotes": {"demo_quote": "you have a contractor quote (use the sample quote if offered)",
               "no_quotes": "you have no quotes yet"},
    "checkin_frequency": {"monthly": "monthly", "fortnightly": "every two weeks", "weekly": "weekly"},
}


class OwnerMove(BaseModel):
    action: str = Field(description="'tap' to press one of the buttons, or 'type' to send a message")
    button: int | None = Field(default=None, description="The button number when action is 'tap'")
    text: str | None = Field(default=None, description="The message when action is 'type'")


def brief(p: E1A.Persona) -> str:
    n, pr = p.numbers, p.prefs
    lang = "Chinese (Simplified)" if p.lang == "zh" else "English"
    style = {
        "tap": "You prefer tapping buttons; you type only when no button fits.",
        "typed": "You prefer typing short messages in your own words, even when buttons are shown.",
        "mixed": "You sometimes tap and sometimes type.",
    }[p.style]
    return (
        "You are role-playing a busy small-business owner using a chat app called Waypoint. Stay in character.\n"
        f"You own {n['shops']} milk-tea shops in Shenzhen, with about RMB {n['profit_k']}k monthly operating profit "
        f"and about RMB {n['spare_k']}k spare cash. You want to open your first shop in Singapore.\n"
        f"Your answers if asked: main customers {LABELS['customers'][pr['customers']]}; budget for the Singapore shop "
        f"{LABELS['budget'][pr['budget']]}; you hope to open {LABELS['window'][pr['window']]}; what matters most is "
        f"{LABELS['priority'][pr['priority']]}; you'd like {LABELS['fitout'][pr['fitout']]}; you'd "
        f"{LABELS['manager'][pr['manager']]}; {LABELS['quotes'][pr['quotes']]}; reminders "
        f"{LABELS['checkin_frequency'][pr['checkin_frequency']]}.\n"
        f"You write in {lang}. {style} You want to finish with an approved plan; agree to reasonable defaults, "
        "approve the plan when it is offered, and if the app reads your WeBank accounts, agree. You may ask at most "
        "one short side question during the whole chat. Never invent buttons: tap only a listed number."
    )


def affordances(d: C.Driver) -> list[tuple[str, Any]]:
    """The buttons the owner sees now, as (label, action) pairs; action is a WidgetEvent."""
    st = d.state
    out: list[tuple[str, Any]] = []
    if st.step == "goal_plan" and st.cards:
        wid = max(st.cards, key=lambda k: int(k[1:]))
        out.append(("Approve (start my goal)", DR._ev(wid, "approve", data={"card_hash": st.cards[wid].card_hash})))
    if st.step == "cost" and any(ln.status in ("pending", "check") for q in st.quotes for ln in q.lines):
        out.append(("Accept all lines read from the quote", DR._ev(d.latest_widget_id("upload_prompt") or "", "accept_all", st.quotes[-1].doc_id)))
    if st.pending is not None:
        for o in st.pending.options:
            out.append((str(o.get("label") or o["value"]), DR._ev(st.pending.widget_id or "", "reply", o["value"])))
    elif st.step == "welcome" and st.consent_feed is None and d.latest_widget_id("consent_card"):
        wid = d.latest_widget_id("consent_card") or ""
        out += [("Agree", DR._ev(wid, "consent", True)), ("Not now", DR._ev(wid, "consent", False))]
    elif d.latest_widget_id("confirm_card") and st.step in ("profile", "site", "cost", "funding"):
        wid = d.latest_widget_id("confirm_card") or ""
        out += [("That's right", DR._ev(wid, "confirm", st.step)), ("Change something", DR._ev(wid, "confirm", "edit"))]
    cards = d.widgets("rule_card")
    if st.pending is None and cards and cards[-1].payload.options:
        for o in cards[-1].payload.options:
            out.append((o.label, DR._ev(cards[-1].id, "select_option", o.value)))
    return out


def _screen(d: C.Driver, buttons: list[tuple[str, Any]]) -> str:
    texts = [t for t in d.texts() if t] or ["(no new message)"]
    lines = ["Waypoint just said:"] + [f"- {t}" for t in texts[-6:]]
    if buttons:
        lines.append("Buttons on screen:")
        lines += [f"{i + 1}. {label}" for i, (label, _) in enumerate(buttons)]
    else:
        lines.append("There are no buttons; type a message.")
    lines.append("What do you do next?")
    return "\n".join(lines)


async def _move(p: E1A.Persona, history: list[str], screen: str) -> OwnerMove:
    from agent import llm

    prompt = "\n".join([*history[-8:], screen])
    return await llm.structured("sim", brief(p), prompt, OwnerMove)  # type: ignore[arg-type]


def run_persona(svc: Any, p: E1A.Persona) -> dict[str, Any]:
    d = C.Driver(svc, p.host_mode, tag=p.pid.lower())
    d.state.lang = p.lang
    d.run(init=True)
    history: list[str] = []
    moves: list[dict[str, Any]] = []
    reached = {d.state.step}
    sim_errors = 0
    while d.state.goal_id is None and d.owner_turns < MAX_TURNS:
        buttons = affordances(d)
        screen = _screen(d, buttons)
        try:
            mv = asyncio.run(_move(p, history, screen))
        except Exception as exc:  # noqa: BLE001 - the simulator failing is recorded, then the turn is retried once
            sim_errors += 1
            moves.append({"sim_error": f"{type(exc).__name__}: {exc}"[:200]})
            if sim_errors >= 3:
                break
            continue
        history.append(screen.replace("What do you do next?", ""))
        if mv.action == "tap" and mv.button is not None and 1 <= mv.button <= len(buttons):
            label, ev = buttons[mv.button - 1]
            history.append(f"You tapped: {label}")
            moves.append({"step": d.state.step, "tap": label})
            d.run(event=ev)
        elif mv.text:
            history.append(f"You typed: {mv.text}")
            moves.append({"step": d.state.step, "type": mv.text})
            d.run(text=mv.text)
        else:
            moves.append({"step": d.state.step, "invalid_move": mv.model_dump()})
            d.owner_turns += 1  # a move the owner couldn't make still costs a turn
        reached.add(d.state.step)
    done = d.state.goal_id is not None
    return {
        "persona": asdict(p),
        "completed": done,
        "owner_turns": d.owner_turns,
        "end_step": d.state.step,
        "reached": sorted(reached, key=E1A.STEPS.index),
        "hit_turn_cap": (not done) and d.owner_turns >= MAX_TURNS,
        "sim_errors": sim_errors,
        "notices": sum(1 for t in d.transcript if t.get("who") == "bot" and t.get("text") is None and t.get("widget") is None),
        "errors": d.errors,
        "moves": moves,
        "transcript": d.transcript,
    }


def run_rows(n: int = N, seed: int = C.SEED, workdir: Any = None, only: set[str] | None = None) -> tuple[list[dict[str, Any]], str]:
    """Run the owners (or `only` those ids, for a shard); returns (rows, voice)."""
    work = workdir or C.setup_env()
    svc = C.make_services(work, "e1b")
    voice = DR.install_test_voice()
    rows = [run_persona(svc, p) for p in E1A.personas(seed, 60)[:n] if only is None or p.pid in only]
    return rows, voice


def evaluate(n: int = N, seed: int = C.SEED, workdir: Any = None) -> dict[str, Any]:
    t0 = time.time()
    rows, voice = run_rows(n, seed, workdir)
    return summarise(rows, voice, seed, time.time() - t0)


def summarise(rows: list[dict[str, Any]], voice: str, seed: int = C.SEED, runtime_s: float | None = None) -> dict[str, Any]:
    rows = sorted(rows, key=lambda r: r["persona"]["pid"])
    done = [r for r in rows if r["completed"]]
    w = C.wilson(len(done), len(rows))
    turns = [float(r["owner_turns"]) for r in done]
    med = C.bootstrap_ci(turns) if turns else {"value": None, "lo": None, "hi": None}
    drop: dict[str, int] = {}
    for r in rows:
        if not r["completed"]:
            drop[r["end_step"]] = drop.get(r["end_step"], 0) + 1
    typed = sum(1 for r in rows for m in r["moves"] if "type" in m)
    taps = sum(1 for r in rows for m in r["moves"] if "tap" in m)
    metrics = {
        "personas": len(rows),
        "reached_goal": w,
        "median_owner_turns_completed": med,
        "drop_off_by_step": drop,
        "hit_turn_cap": sum(1 for r in rows if r["hit_turn_cap"]),
        "owner_moves": {"taps": taps, "typed": typed},
        "simulator_errors": sum(r["sim_errors"] for r in rows),
        "unhandled_exceptions": sum(len(r["errors"]) for r in rows),
        "voice": voice,
        "rows": [{k: v for k, v in r.items() if k not in ("transcript", "persona")} | {"pid": r["persona"]["pid"]} for r in rows],
    }
    ok_reach = w["p"] is not None and w["p"] >= 0.90
    ok_turns = med["value"] is not None and med["value"] <= 25
    notes = [
        f"{len(rows)} simulated owners (the first {len(rows)} of E1a's fixed personas) played by a model; the agent is the "
        f"real orchestrator. {voice}. Single-family deviation: the owner and the agent are both Claude (prereg addendum 2).",
        f"Reached a confirmed goal: {C.wfmt(w)}; median owner turns among those {med['value']} "
        f"(95% CI {med['lo']}-{med['hi']}); stopped at: {drop or 'none'}; owner moves: {taps} taps, {typed} typed.",
    ]
    if metrics["simulator_errors"] or metrics["unhandled_exceptions"]:
        notes.append(f"Simulator errors {metrics['simulator_errors']}; unhandled exceptions {metrics['unhandled_exceptions']}.")
    return C.entry(
        "run",
        n=len(rows),
        title="Simulated owners played by a model (Claude; single-family deviation)",
        metrics=metrics,
        pass_marks={
            "reached a confirmed goal (single-family deviation)": C.mark(">= 90%", C.pct(w["p"]), ok_reach),
            "median owner turns (single-family deviation)": C.mark("<= 25", med["value"], ok_turns),
        },
        notes=notes,
        runtime_s=runtime_s,
        seed=seed,
    )


if __name__ == "__main__":  # a quick look at one owner
    import json
    import sys

    svc = C.make_services(C.setup_env(), "e1b-one")
    DR.install_test_voice()
    r = run_persona(svc, E1A.personas(C.SEED, 60)[int(sys.argv[1]) if len(sys.argv) > 1 else 0])
    print(json.dumps({k: r[k] for k in ("completed", "owner_turns", "end_step", "moves")}, ensure_ascii=False, indent=1, default=str))
