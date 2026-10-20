"""One turn's context: the active Skill, the tool gate, and the outputs (text and widgets).

Every tool call goes through `Turn.call`, which runs `authorize()` (SPEC §8.2): the tool must be on
the active Skill's allowlist (or an always-loaded Skill's), and the call is written to the audit log.
Text goes through the number checker and the renderer; widgets only come from tool payloads.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, TypeVar

from agent import render
from agent.audit import AuditLog
from agent.skills import SkillRegistry, SkillSpec
from agent.state import SKILL_FOR_STEP, JourneyState, Pending
from agent.voice import Beat
from agent.widgets import Option, QuickReplies, Widget, WidgetPayload
from tools.figures import Figure, FigureStore

log = logging.getLogger(__name__)
T = TypeVar("T")


class NotAuthorized(PermissionError):
    pass


class Services(Protocol):
    """What step handlers may use besides tools (implemented by app.services.AppServices)."""

    def today(self) -> date: ...
    def demo(self) -> bool: ...


@dataclass
class Out:
    kind: str  # "beat" (until composed) | "text" | "widget" | "notice"
    text: str | None = None
    widget: Widget | None = None
    beat: Beat | None = None
    notice: dict[str, Any] | None = None


@dataclass
class Turn:
    state: JourneyState
    skills: SkillRegistry
    audit: AuditLog
    services: Any
    outputs: list[Out] = field(default_factory=list)
    figs: FigureStore = field(default_factory=FigureStore)
    resolver: Callable[[str], Figure | None] | None = None
    rule_title: Callable[[str], str] | None = None
    topic_title: Callable[[str], str] | None = None
    # a step with no pending slot but a card still to answer (the consent card) re-shows it here
    reask_card: Callable[[Turn], bool] | None = None

    # ---------------------------------------------------------------- skills and gate

    @property
    def lang(self) -> render.Lang:
        return self.state.lang

    @property
    def skill(self) -> SkillSpec:
        return self.skills[SKILL_FOR_STEP[self.state.step]]

    def allowed_tools(self, skill: SkillSpec | None = None) -> set[str]:
        sk = skill or self.skill
        allowed = set(sk.tools)
        for s in self.skills.always:
            allowed.update(s.tools)
        allowed.update(self.skills["detour"].tools)
        return allowed

    def authorize(self, tool: str, skill: SkillSpec | None = None) -> None:
        sk = skill or self.skill
        if tool not in self.allowed_tools(sk):
            self.audit.append(
                "deny", self.state.owner_id, skill=sk.name, tool=tool, reason="not_on_allowlist"
            )
            raise NotAuthorized(f"{tool} is not allowed in skill {sk.name}")

    def call(
        self, tool: str, fn: Callable[..., T], *args: Any, skill: SkillSpec | None = None, **kwargs: Any
    ) -> T:
        self.authorize(tool, skill)
        result = fn(*args, **kwargs)
        self.audit.append(
            "tool",
            self.state.owner_id,
            skill=(skill or self.skill).name,
            tool=tool,
            args=_summ(args, kwargs),
        )
        return result

    # ---------------------------------------------------------------- figures

    def add(self, *figs: Figure) -> None:
        for f in figs:
            self.figs.add(f)

    def _fig(self, fig_id: str) -> Figure | None:
        f = self.figs.get(fig_id)
        if f is None and self.resolver is not None:
            f = self.resolver(fig_id)
            if f is not None:
                self.figs.add(f)
        return f

    # ---------------------------------------------------------------- outputs

    def text(self, template: str, vars: dict[str, str] | None = None) -> str:
        """Render a template that has passed the number checker (Skill lines are checked at load)."""
        for k, v in (vars or {}).items():
            template = template.replace("{{" + k + "}}", v)
        # Resolve every figure placeholder first so unknown ids fail loudly.
        for m in render.PLACEHOLDER.finditer(template):
            if m.group(1) == "fig":
                self._fig(m.group(2))
        return render.render(
            template,
            self.figs.all(),
            self.lang,
            start=self.state.start_date,
            rule_title=self.rule_title,
            topic_title=self.topic_title,
        )

    def say(
        self,
        key: str,
        vars: dict[str, str] | None = None,
        skill: str | None = None,
        facts: dict[str, str] | None = None,
        ask: bool | None = None,
        into: str | None = None,
    ) -> None:
        """Queue a beat: what this message must convey. The model writes it at the end of the turn."""
        sk = self.skills[skill] if skill else self.skill
        spec = sk.beat(key)
        for m in render.PLACEHOLDER.finditer(" ".join(spec.must)):
            if m.group(1) == "fig":
                self._fig(m.group(2))
        n = sum(1 for o in self.outputs if o.kind == "beat")
        self.outputs.append(
            Out(
                "beat",
                beat=Beat(
                    id=f"{sk.name}.{key}.{n}",
                    skill=sk.name,
                    key=key,
                    convey=spec.convey,
                    must=list(spec.must),
                    vars=dict(vars or {}),
                    facts=dict(facts or {}),
                    ask=spec.ask if ask is None else ask,
                    into=into,
                ),
            )
        )

    def show(
        self,
        payload: WidgetPayload,
        fig_ids: list[str] | None = None,
        skill: SkillSpec | None = None,
        wid: str | None = None,
    ) -> str:
        sk = skill or self.skill
        allowed = (
            set(sk.widgets)
            | {w for s in self.skills.always for w in s.widgets}
            | set(self.skills["detour"].widgets)
        )
        if payload.type not in allowed:
            self.audit.append(
                "deny", self.state.owner_id, skill=sk.name, widget=payload.type, reason="widget_not_allowed"
            )
            raise NotAuthorized(f"widget {payload.type} not allowed in {sk.name}")
        wid = wid or self.state.next_widget_id()
        figs = {}
        for fid in fig_ids or _fig_ids(payload):
            f = self._fig(fid)
            if f is not None:
                figs[fid] = f
        widget = Widget(
            id=wid,
            payload=payload,
            figures=figs,
            display=render.display_map(figs, self.lang, self.state.start_date),
        )
        self.state.widget_types[wid] = payload.type
        self.state.widget_steps[wid] = self.state.step
        self.outputs.append(Out("widget", widget=widget))
        return wid

    def ask(
        self,
        skill: str,
        slot: str,
        line: str,
        options: list[Option],
        default: str | None = None,
        vars: dict[str, str] | None = None,
        allow_text: bool = True,
        say_line: bool = True,
    ) -> None:
        if say_line:
            self.say(line, vars, skill=skill)
        wid = self.show(QuickReplies(slot=slot, options=options, default=default, allow_text=allow_text), [])
        self.state.pending = Pending(
            skill=skill,
            slot=slot,
            line=line,
            widget_id=wid,
            options=[o.model_dump() for o in options],
            vars=vars or {},
        )

    def reask(self) -> None:
        p = self.state.pending
        if p is None:
            if self.reask_card is not None:
                self.reask_card(self)
            return
        opts = [Option(**o) for o in p.options]
        self.say("back_to_question", skill="journey")
        self.ask(p.skill, p.slot, p.line, opts, vars=p.vars)

    def notice(self, code: str) -> None:
        """A plain notice from the interface (no model words, nothing to retry), e.g. an expired link."""
        self.outputs.append(Out("notice", notice={"code": code, "retry": False}))

    def mark(self, kind: str, **fields: Any) -> None:
        self.audit.append(kind, self.state.owner_id, step=self.state.step, **fields)


def _fig_ids(payload: WidgetPayload) -> list[str]:
    """Collect figure ids referenced anywhere in a payload (fields typed as figure ids are strings
    that resolve in the store; everything else is ignored)."""
    found: list[str] = []

    def walk(v: Any) -> None:
        if isinstance(v, str):
            found.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list | tuple):
            for x in v:
                walk(x)

    walk(payload.model_dump())
    return found


def _summ(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    def s(v: Any) -> Any:
        if hasattr(v, "model_dump"):
            return type(v).__name__
        if isinstance(v, str | int | float | bool) or v is None:
            return v
        if isinstance(v, list | tuple):
            return f"{type(v).__name__}[{len(v)}]"
        return type(v).__name__

    return {"args": [s(a) for a in args], "kwargs": {k: s(v) for k, v in kwargs.items()}}
