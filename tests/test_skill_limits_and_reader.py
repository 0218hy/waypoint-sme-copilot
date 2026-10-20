"""SPEC §12.4: a step that runs past its Skill's `max_turns` falls back to the pending slot's default and
moves on, and a quote line the model reads with low confidence goes to the owner as "please check"."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent import llm, reader
from tests.test_journey import Driver, _to_cost, svc  # noqa: F401 - svc is a fixture


def _audit(svc: Any, kind: str) -> list[dict[str, Any]]:  # noqa: F811 - not the fixture
    lines = svc.audit.path.read_text(encoding="utf-8").splitlines()
    return [r for r in map(json.loads, lines) if r["kind"] == kind]


def test_max_turns_takes_the_pending_default_and_moves_on(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    d.run(init=True)
    d.event("consent_card", "consent", True)
    assert d.state.step == "profile" and d.state.pending is not None
    limit = svc.orchestrator.skills["profile"].max_turns
    assert limit > 0
    first = d.state.pending.slot
    sent = 0
    while d.state.pending is not None and d.state.pending.slot == first and sent < limit + 5:
        d.run(text="hmm, let me think about it")  # understood as nothing, so the slot stays open
        sent += 1
    assert d.state.pending is None or d.state.pending.slot != first, "the step never fell back"
    assert sent <= limit  # the consent tap counted as the step's first turn
    [rec] = _audit(svc, "max_turns_default")
    assert rec["slot"] == first and rec["step"] == "profile"


def test_a_step_under_its_limit_does_not_fall_back(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    d.run(init=True)
    d.event("consent_card", "consent", True)
    first = d.state.pending.slot  # type: ignore[union-attr]
    for _ in range(svc.orchestrator.skills["profile"].max_turns - 2):
        d.run(text="hmm")
    assert d.state.pending is not None and d.state.pending.slot == first
    assert _audit(svc, "max_turns_default") == []


@pytest.fixture()
def model_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """The model-mode reader with a canned answer: one clear line and one it is unsure of."""
    monkeypatch.delenv("WAYPOINT_READER_REPLAY", raising=False)

    async def fake(role: str, _instructions: str, _prompt: str, output: type, **_k: object) -> Any:
        if output is not reader.ReaderOutput:
            raise llm.ModelUnavailable("only the reader is faked here")
        return reader.ReaderOutput(lines=[
            reader._ModelLine(label="Flooring works", amount="9500", confidence=0.95),
            reader._ModelLine(label="Ceiling (smudged)", amount="4800", confidence=0.6),
            reader._ModelLine(label="Lighting", amount="3000", confidence=0.8),
        ])

    monkeypatch.setattr(llm, "enabled", lambda role: role == "reader")
    monkeypatch.setattr(llm, "structured", fake)


def test_a_low_confidence_line_goes_to_the_owner_as_please_check(svc: Any, model_reader: None) -> None:  # noqa: F811
    d = Driver(svc)
    _to_cost(d)
    d.reply("add_quote")
    d.reply("demo_quote")
    up = d.widgets("upload_prompt")[-1].payload
    assert up.reader_mode == "model"
    status = {row.label: row.status for row in up.extracted}
    assert status == {"Flooring works": "pending", "Ceiling (smudged)": "check", "Lighting": "pending"}
    # the flag is kept with the stored document, so the Documents tab shows it too
    [doc] = svc.documents_view(d.user["id"])["uploads"]
    assert {ln["label"]: ln["status"] for ln in doc["lines"]}["Ceiling (smudged)"] == "check"
    # the line counts only once the owner accepts it
    assert d.state.cost_card is not None and not any(ln.from_quote for ln in d.state.cost_card.lines)


def test_a_widget_off_the_skills_allowlist_is_refused_and_never_shown(svc: Any) -> None:  # noqa: F811
    from agent.turn import NotAuthorized
    from agent.widgets import GoalSummary

    d = Driver(svc)
    d.run(init=True)
    t = svc.orchestrator.turn(d.state)
    assert "goal_summary" not in t.skill.widgets
    with pytest.raises(NotAuthorized):
        t.show(GoalSummary(sentence="Open in Tampines", figures=[], assumptions=[]))
    assert t.outputs == []
    [deny] = _audit(svc, "deny")
    assert deny["widget"] == "goal_summary" and deny["reason"] == "widget_not_allowed"


def test_topics_come_only_from_the_skills_list_and_once_per_journey(svc: Any) -> None:  # noqa: F811
    from tests.test_journey import _approve, _to_goal_plan

    d = Driver(svc)
    ids: list[str] = []
    real_run = d.run

    def run(*a: Any, **k: Any) -> Any:
        outs = real_run(*a, **k)
        ids.extend(w.payload.topic_id for w in d.widgets("topic_card"))
        return outs

    d.run = run  # type: ignore[method-assign]
    _to_goal_plan(d)
    _approve(d)
    assert ids and len(ids) == len(set(ids)), ids
    assert set(ids) == set(d.state.raised_topics)
    listed = {tid for sk in svc.orchestrator.skills.by_step.values() for tid in sk.topics}
    assert set(ids) <= listed


def test_accept_all_leaves_please_check_lines_for_the_owner(svc: Any, model_reader: None) -> None:  # noqa: F811
    d = Driver(svc)
    _to_cost(d)
    d.reply("add_quote")
    d.reply("demo_quote")
    up = d.widgets("upload_prompt")[-1].payload
    d.event("upload_prompt", "accept_all", up.doc_id)
    q = next(q for q in d.state.quotes if q.doc_id == up.doc_id)
    status = {ln.label: ln.status for ln in q.lines}
    assert status == {"Flooring works": "accepted", "Ceiling (smudged)": "check", "Lighting": "accepted"}
    assert any(t.startswith("check left") for t in d.texts())  # the check_left beat (test composer)
    # confirming the last one by itself decides the document and re-costs the card
    ceiling = next(ln.id for ln in q.lines if ln.status == "check")
    d.event("upload_prompt", "accept_line", ceiling)
    q = next(q for q in d.state.quotes if q.doc_id == up.doc_id)
    assert all(ln.status == "accepted" for ln in q.lines)
    assert d.widgets("cost_breakdown")


def test_replay_reader_marks_low_confidence_lines_please_check() -> None:
    gold = {
        "lines": [
            {"id": "a", "label": "Flooring", "amount": "9500", "bbox": [0, 0, 1, 1], "confidence": 0.93},
            {"id": "b", "label": "Ceiling", "amount": "4800", "bbox": [0, 0, 1, 1], "confidence": 0.5},
        ]
    }
    quote, _pii, _ignored = reader._from_gold("doc", gold)
    assert [ln.status for ln in quote.lines] == ["pending", "check"]
