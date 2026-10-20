"""The voice (SPEC §0.1–0.3): the model writes every Waypoint message.

Step handlers don't write text. They emit *beats*: what a message must convey (from the active
Skill), which figures it must mention (as placeholders) and which names it may use. One model call
per turn writes all the turn's messages in the owner's language. Code then validates each message:
no digits or number words outside placeholders, only placeholders this turn provided, and every
required placeholder present. A failed message is retried once with the errors; if it still fails,
the turn's cards still show and the owner gets a retry notice. Nothing here is pre-written text.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, Field

from agent import llm
from agent.render import PLACEHOLDER, check_text

_VAR = re.compile(r"\{\{([a-z_]+)\}\}")


class Beat(BaseModel):
    id: str  # "<skill>.<key>.<n>"
    skill: str
    key: str
    convey: str
    must: list[str] = []  # placeholders that must appear, e.g. "{{fig:funding.gap}}"
    vars: dict[str, str] = {}  # names the text may use as {{name}}
    facts: dict[str, str] = {}  # extra context, e.g. the owner's question
    ask: bool = False  # the message ends by asking the pending question
    into: str | None = None  # a widget id: the text becomes that widget's body (a draft), not a message


class ComposedMessage(BaseModel):
    beat: str = Field(description="The beat id this message is for.")
    text: str = Field(description="The message. Quantities only as the given {{fig:…}} placeholders.")


class Composed(BaseModel):
    messages: list[ComposedMessage]


_TEST_COMPOSER: Callable[[list[Beat], str], list[str]] | None = None


def set_test_composer(fn: Callable[[list[Beat], str], list[str]] | None) -> None:
    """Tests and evals inject a deterministic composer (no model)."""
    global _TEST_COMPOSER
    _TEST_COMPOSER = fn


def echo_composer(beats: list[Beat], lang: str) -> list[str]:
    """A deterministic stand-in for tests: the beat key plus its required placeholders."""
    return [" ".join([b.key.replace("_", " "), *b.must]).strip() for b in beats]


def validate(text: str, allowed_figs: set[str], allowed_vars: set[str], must: list[str]) -> list[str]:
    errors: list[str] = []
    stripped = _VAR.sub(" ", text)
    res = check_text(stripped)
    if not res.ok:
        errors.append(f"contains quantities outside placeholders: {', '.join(res.hits)}")
    for m in PLACEHOLDER.finditer(text):
        kind, key = m.group(1), m.group(2)
        if kind == "fig" and key not in allowed_figs and not key.startswith("param:"):
            errors.append(f"unknown placeholder {{{{fig:{key}}}}}")
    for v in _VAR.findall(text):
        if v not in allowed_vars:
            errors.append(f"unknown name {{{{{v}}}}}")
    for need in must:
        if need not in text:
            errors.append(f"missing required {need}")
    if not text.strip():
        errors.append("empty message")
    return errors


def _instructions(skill_bodies: list[str], lang: str) -> str:
    language = "Simplified Chinese (简体中文)" if lang == "zh" else "English"
    return "\n\n".join(
        [
            *skill_bodies,
            "## How to write this turn",
            f"- Write in {language}. Warm, plain, brief: one or two short sentences per message; a question "
            "only where the beat asks for one.",
            "- Write one message per beat, in the same order, each conveying that beat's purpose. Don't repeat "  # noqa: E501
            "what an earlier message in this turn already said.",
            "- NEVER write digits, amounts, percentages, dates or number words (in any language). Every "
            "quantity goes in as one of the given {{fig:…}} placeholders, copied exactly; code fills them.",
            "- Use names only as the given {{name}} placeholders. Don't invent facts, options, rules or "
            "advice beyond the beat, the Skills and the figures listed.",
            "- The cards (widgets) beside your messages show the details; refer to them instead of repeating.",  # noqa: E501
        ]
    )


def _prompt(
    beats: list[Beat],
    figures: Mapping[str, tuple[str, str]],
    history: list[str],
    errors: dict[str, list[str]],
) -> str:
    lines = ["Recent conversation (oldest first):"]
    lines += [f"  {h}" for h in history[-8:]] or ["  (start of the conversation)"]
    lines.append(
        "\nFigures you may reference (placeholder: what it is — current value, for your understanding only; "
        "never copy the value):"
    )
    for fid, (label, shown) in figures.items():
        lines.append(f"  {{{{fig:{fid}}}}}: {label} — {shown}")
    lines.append("\nBeats to write, in order:")
    for b in beats:
        lines.append(f"- id {b.id} [{b.skill}]: {b.convey}")
        if b.must:
            lines.append(f"    must include: {' '.join(b.must)}")
        if b.vars:
            lines.append(
                "    names you may use: " + ", ".join(f"{{{{{k}}}}} = {v}" for k, v in b.vars.items())
            )
        if b.facts:
            lines.append("    context: " + "; ".join(f"{k}: {v}" for k, v in b.facts.items()))
        if b.ask:
            lines.append("    end by asking the question")
        if b.into:
            lines.append(
                "    this text is the body of a draft the owner will send in their own name (first person); "
                "it is not a message to the owner, and it may run to a few short paragraphs"
            )
        if errors.get(b.id):
            lines.append("    YOUR PREVIOUS ATTEMPT WAS REJECTED: " + "; ".join(errors[b.id]))
    return "\n".join(lines)


async def compose(
    beats: list[Beat],
    *,
    lang: str,
    figures: Mapping[str, tuple[str, str]],
    skill_bodies: list[str],
    history: list[str],
) -> tuple[list[str | None], dict[str, Any]]:
    """Write the turn's messages. Returns one template per beat (None where it failed) and a report."""
    if not beats:
        return [], {"model": "none"}
    allowed = set(figures)
    if _TEST_COMPOSER is not None:
        texts = _TEST_COMPOSER(beats, lang)
        out: list[str | None] = []
        for b, t in zip(beats, texts, strict=True):
            errs = validate(t, allowed, set(b.vars), b.must)
            out.append(None if errs else t)
        return out, {"model": "test-composer"}
    instructions = _instructions(skill_bodies, lang)
    results: dict[str, str] = {}
    errors: dict[str, list[str]] = {}
    pending = list(beats)
    attempts = 0
    while pending and attempts < 2:
        attempts += 1
        try:
            composed = await llm.structured(
                "voice", instructions, _prompt(pending, figures, history, errors), Composed
            )
        except llm.ModelUnavailable as exc:
            return [results.get(b.id) for b in beats], {"model": llm.model_label("voice"), "error": str(exc)}
        by_id = {m.beat: m.text.strip() for m in composed.messages}
        still: list[Beat] = []
        for b in pending:
            text = by_id.get(b.id, "")
            errs = validate(text, allowed, set(b.vars), b.must)
            if errs:
                errors[b.id] = errs
                still.append(b)
            else:
                results[b.id] = text
        pending = still
    report = {
        "model": llm.model_label("voice"),
        "attempts": attempts,
        "rejected": {k: v for k, v in errors.items() if k not in results},
    }
    return [results.get(b.id) for b in beats], report
