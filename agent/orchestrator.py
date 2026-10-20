"""The orchestrator (SPEC §2, §3.1, §4): routes one owner input through guard, the active Skill and
the optional model, and returns rendered text and widgets.

Order for free text: guard → the pending slot (parsed by code) → a side-question topic → the turn
model (validated against the active Skill) → "unclear". A side question is answered only with a library
topic card or the scope card, then the pending question: never a free-form reply. Structured widget events
are accepted only
for widgets this server issued to this owner.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from agent import intent, llm, parse, steps, voice
from agent import options as O
from agent import toolkit as tk
from agent.audit import AuditLog
from agent.skills import SkillRegistry, load_skills
from agent.state import JOURNEY_STEPS, SKILL_FOR_STEP, JourneyState
from agent.turn import NotAuthorized, Out, Turn
from agent.widgets import Option, WidgetEvent

log = logging.getLogger(__name__)

SLOT_SYNONYMS: dict[str, dict[str, list[str]]] = {
    "customers": O.CUSTOMER_SYNONYMS,
    "priority": O.PRIORITY_SYNONYMS,
    "lang": {"en": ["english", "英文", "英语"], "zh": ["chinese", "中文", "汉语", "普通话"]},
    "fitout": {
        "basic": ["basic", "simple", "简单", "简洁"],
        "standard": ["standard", "normal", "标准", "一样"],
        "premium": ["premium", "flagship", "fancy", "高端", "旗舰"],
    },
    "manager": {
        "hire_local": ["hire", "local", "招聘", "本地"],
        "send_own": ["send", "my own", "自己", "派"],
    },
    "quotes": {"no_quotes": ["no", "none", "没有", "暂时没有"], "demo_quote": ["sample", "demo", "示例"]},
    "lever": {
        "looks_good": ["good", "ok", "fine", "可以", "好"],
        "add_savings": ["savings", "积蓄", "存款"],
        "rent_free": ["rent-free", "rent free", "免租"],
        "partner": ["partner", "合伙"],
    },
    "checkin_frequency": {
        "monthly": ["month", "每月", "月"],
        "fortnightly": ["fortnight", "两周"],
        "weekly": ["week", "每周", "周"],
    },
}
MONEY_SLOTS = {"monthly_profit", "spare_cash", "budget", "savings"}
FIRST_MENTION_SLOTS = {"customers", "priority"}
YES_NO_SLOTS = {"email_amounts", "recurring_setaside"}
BACK = re.compile(r"\b(go back|back|change|edit|redo)\b|返回|回到|修改|改一下|重新", re.IGNORECASE)
RULE_IDS = {"R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"}
CHECKIN = re.compile(r"check.?in|update my (?:numbers|progress)|report|进度|汇报|更新", re.IGNORECASE)


class Orchestrator:
    def __init__(self, services: Any, audit: AuditLog, skills: SkillRegistry | None = None) -> None:
        self.services = services
        self.audit = audit
        self.skills = skills or load_skills(known_tools=frozenset(tk.TOOL_NAMES))

    def turn(self, state: JourneyState) -> Turn:
        return Turn(
            state=state,
            skills=self.skills,
            audit=self.audit,
            services=self.services,
            resolver=tk.resolve_fig,
            rule_title=lambda r: tk.rule(r, state.lang)["title"],
            topic_title=lambda tid: tk.topic(tid, state.lang)["title"],
            reask_card=steps.consent_again,
        )

    # ---------------------------------------------------------------- entry points

    async def run(
        self, state: JourneyState, text: str | None, event: WidgetEvent | None, init: bool, retry: bool = False  # noqa: E501
    ) -> list[Out]:
        """One whole turn (step, then the voice). The web endpoint uses run_turn + compose to stream cards first."""  # noqa: E501
        if retry:
            return await self._retry_compose(self.turn(state))
        t = await self.run_turn(state, text, event, init)
        await self.compose(t)
        return t.outputs

    async def run_turn(
        self, state: JourneyState, text: str | None, event: WidgetEvent | None, init: bool,
        link: tuple[str, str] | None = None,
    ) -> Turn:
        """Run the step: cards are ready at once; messages are still beats until `compose`. `link` is an
        email link (kind, value) the web app read from its address once, sent with the opening run."""
        t = self.turn(state)
        try:
            if init:
                if not state.started:
                    steps.ENTER["welcome"](t)
                if link is not None:
                    steps.open_link(t, *link)
            elif event is not None:
                try:
                    self._event(t, event)
                except (KeyError, ValueError, AssertionError, ArithmeticError) as exc:
                    # malformed or out-of-order input: logged and ignored, never a crash
                    t.mark("ignored_event", reason="invalid_input", error=type(exc).__name__, event=event.event)  # noqa: E501
                    t.outputs.clear()
            elif text:
                await self._text(t, text.strip()[:2000])
        except NotAuthorized as exc:
            log.warning("not authorized: %s", exc)
            t.say("unclear", skill="journey")
        if not init:
            state.turns_in_step += 1
            self._max_turns(t)
        return t

    async def compose(self, t: Turn) -> None:
        await self._compose(t)

    # ---------------------------------------------------------------- the voice

    def _figure_map(self, t: Turn) -> dict[str, tuple[str, str]]:
        from agent.render import fmt_figure

        return {fid: (f.label, fmt_figure(f, t.lang, t.state.start_date)) for fid, f in t.figs.all().items()}

    async def _compose(self, t: Turn) -> None:
        """Replace the turn's beats with model-written messages (validated), or a retry notice."""
        beats = [o.beat for o in t.outputs if o.kind == "beat" and o.beat is not None]
        if not beats:
            return
        figures = self._figure_map(t)
        bodies = [self.skills["journey"].body, t.skill.body]
        has_history = hasattr(self.services, "history")
        history = _own_lines(self.services.history(t.state.owner_id)) if has_history else []
        texts, report = await voice.compose(
            beats, lang=t.lang, figures=figures, skill_bodies=bodies, history=history
        )
        by_id = {b.id: txt for b, txt in zip(beats, texts, strict=True)}
        failed = [b for b in beats if by_id.get(b.id) is None]
        t.mark(
            "compose",
            model=report.get("model"),
            beats=len(beats),
            failed=len(failed),
            rejected=sorted(report.get("rejected", {}).keys()),
            error=report.get("error"),
        )
        new: list[Out] = []
        notice_added = False
        for o in t.outputs:
            if o.kind != "beat" or o.beat is None:
                new.append(o)
                continue
            tpl = by_id.get(o.beat.id)
            if tpl is not None:
                new.append(Out("text", text=t.text(tpl, o.beat.vars), beat=o.beat))
            elif not notice_added:
                code = "model_unavailable" if report.get("error") else "compose_failed"
                new.append(Out("notice", notice={"code": code, "retry": True}))
                notice_added = True
        t.outputs[:] = _fill_bodies(new)
        t.state.failed_beats = (
            [{"beat": b.model_dump(), "figures": {k: list(v) for k, v in figures.items()}} for b in failed]
            if failed
            else []
        )

    async def _retry_compose(self, t: Turn) -> list[Out]:
        from agent.render import render
        from agent.voice import Beat

        if not t.state.failed_beats:
            return []
        beats = [Beat.model_validate(r["beat"]) for r in t.state.failed_beats]
        figures: dict[str, tuple[str, str]] = {}
        for r in t.state.failed_beats:
            figures.update({k: (v[0], v[1]) for k, v in r["figures"].items()})
        texts, report = await voice.compose(
            beats,
            lang=t.lang,
            figures=figures,
            skill_bodies=[self.skills["journey"].body, t.skill.body],
            history=[],
        )
        outs: list[Out] = []
        still = []
        for b, tpl in zip(beats, texts, strict=True):
            if tpl is None:
                still.append(b)
                continue
            for k, v in b.vars.items():
                tpl = tpl.replace("{{" + k + "}}", v)
            # figures from the failed turn: render from their stored display values
            outs.append(Out("text", text=_fill_display(tpl, figures)))
        if still:
            outs.append(Out("notice", notice={"code": "compose_failed", "retry": True}))
        t.state.failed_beats = [
            r for r in t.state.failed_beats if Beat.model_validate(r["beat"]).id in {b.id for b in still}
        ]
        _ = render
        return outs

    def preview_setaside(self, state: JourneyState, share: float) -> dict[str, Any]:
        t = self.turn(state)
        t.authorize("plan.simulate", self.skills["funding"])
        return tk.preview(state, share, t.lang)

    def preview_compare(self, state: JourneyState, savings: Decimal) -> dict[str, Any]:
        t = self.turn(state)
        t.authorize("plan.simulate", self.skills["funding"])
        return tk.compare_preview(state, savings, t.lang)

    def goal_dashboard(self, state: JourneyState) -> dict[str, Any]:
        return dict(self.services.goal_dashboard(state))

    # ---------------------------------------------------------------- events

    def _event(self, t: Turn, ev: WidgetEvent) -> None:
        st = t.state
        issued_type = st.widget_types.get(ev.widget_id)
        # the Goal tab's own (read-only) widgets aren't issued in the chat; these events may come from them
        if issued_type is None and ev.event not in ("reopen_step", "back", "checkin", "see_repairs", "open_milestone"):  # noqa: E501
            t.mark("ignored_event", reason="unknown_widget", event=ev.event)
            return
        t.mark("event", event=ev.event, widget=issued_type)
        issued_step = st.widget_steps.get(ev.widget_id)
        roaming = ("reopen_step", "back", "checkin", "see_repairs", "select_repair", "open_milestone", "select_option",  # noqa: E501
                   "approve", "cancel", "mark_milestone_done")
        if issued_step is not None and issued_step != st.step and ev.event not in roaming:
            t.mark("ignored_event", reason="widget_from_another_step", event=ev.event)
            return
        if ev.event == "confirm" and not _confirm_ok(ev, issued_type, st.step):
            t.mark("ignored_event", reason="bad_confirm", widget=issued_type)
            return
        if ev.event == "reply":
            p = st.pending
            if p is None or p.widget_id != ev.widget_id:
                t.mark("ignored_event", reason="stale_reply")
                return
            values = {o["value"] for o in p.options}
            if str(ev.value) not in values:
                t.mark("ignored_event", reason="unknown_option")
                return
            self._slot(t, p.skill, p.slot, str(ev.value))
            return
        if ev.event == "back" and issued_type == "confirm_card":
            # "Change something" on a step's confirm card: edit that step in place
            steps.EVENT.get(st.step, lambda _t, _e: False)(
                t, ev.model_copy(update={"event": "confirm", "value": "edit"})
            )
            return
        if ev.event == "back" and issued_type == "area_card" and st.step == "site":
            steps.site_slot(t, "priority", (st.shortlist.priority or "near_customers"))
            return
        if ev.event in ("reopen_step", "back"):
            target = str(ev.value)
            if target in JOURNEY_STEPS:
                steps.reopen(t, target)
            return
        if ev.event in ("approve", "cancel") and issued_type == "approval_card":
            steps.approval_event(t, ev)
            return
        if ev.event == "select_option" and issued_type == "rule_card":
            steps.guard_option(t, str(ev.value))
            return
        if ev.event == "mark_milestone_done" and issued_type != "milestone_timeline":
            t.mark("ignored_event", reason="bad_source", event=ev.event, widget=issued_type)
            return
        if st.goal_id and ev.event in ("checkin", "see_repairs", "select_repair", "open_milestone", "mark_milestone_done"):  # noqa: E501
            if st.step != "goal_keeper":
                st.step = "goal_keeper"
            steps.EVENT["goal_keeper"](t, ev)
            return
        handled = steps.EVENT.get(st.step, lambda _t, _e: False)(t, ev)
        if not handled:
            t.mark("ignored_event", reason="not_handled_in_step", event=ev.event)

    def _slot(self, t: Turn, skill: str, slot: str, value: str) -> None:
        handler = steps.SLOT.get(skill)
        if handler is None:
            return
        handler(t, slot, value)

    # ---------------------------------------------------------------- free text

    async def _text(self, t: Turn, text: str) -> None:
        st = t.state
        # The owner can switch language just by writing in the other one.
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        latin = len(re.findall(r"[A-Za-z]", text))
        if st.lang == "en" and cjk >= 2 and cjk >= latin / 4:
            st.lang = "zh"
            t.mark("language_switch", to="zh")
        elif st.lang == "zh" and cjk == 0 and latin >= 8:
            st.lang = "en"
            t.mark("language_switch", to="en")
        # 1. guard: the keyword baseline decides; the model may only add a flag
        hits = [h.rule_id for h in intent.classify(text)]
        decision = None
        if not hits:
            decision = await self._decide(t, text)
            if decision is not None and decision.rule_id in RULE_IDS:
                hits = [str(decision.rule_id)]
                t.mark("guard_model_flag", rule=decision.rule_id)
        if hits:
            steps.guard(t, hits)
            t.reask()
            return
        # a typed yes or no to the consent card is read by code, with or without a model
        if steps.awaiting_consent(t):
            yn = parse.consent(text)
            if yn is not None:
                steps.welcome_consent(t, yn, via="text")
                return
        # 2. the model's reading of the message, validated by code
        if decision is not None:
            if self._apply(t, text, decision):
                return
        else:
            # no model: code understanding only
            if st.pending is not None:
                value = self._parse_slot(st.pending.slot, text, [Option(**o) for o in st.pending.options])
                if value is not None:
                    self._slot(t, st.pending.skill, st.pending.slot, value)
                    return
            if st.step == "goal_keeper" and st.goal_id:
                mid = intent.milestone_done(text)
                if mid is not None:
                    steps.mark_done(t, mid, via="text")
                    return
            if st.step == "goal_keeper" and CHECKIN.search(text):
                self.services.show_checkin(t)
                return
            if BACK.search(text) and st.step in JOURNEY_STEPS and st.step != "profile":
                steps.reopen(t, JOURNEY_STEPS[JOURNEY_STEPS.index(st.step) - 1])
                return
            topic_id = intent.match_topic(text, self.skills["detour"].topics)
            if topic_id:
                t.say("lead", skill="detour")
                steps.show_topic(t, topic_id)
                t.reask()
                return
        # 3. unclear: say so and show the options again
        t.say("unclear", skill="journey")
        if st.pending is not None:
            p = st.pending
            st.pending = None
            t.ask(p.skill, p.slot, p.line, [Option(**o) for o in p.options], vars=p.vars, say_line=False)
        else:
            steps.consent_again(t, lead=False)

    async def _decide(self, t: Turn, text: str) -> llm.TurnDecision | None:
        st = t.state
        p = st.pending
        opts = [str(o["value"]) for o in p.options if o.get("value")] if p else []
        allowed = ["answer_slot", "answer_side_question", "go_back", "check_in", "unclear"]
        correctable = steps.correctable_fields(t)
        if correctable:
            allowed.insert(3, "correct_business")
        open_steps = self._open_milestones(t)
        if open_steps:
            allowed.insert(-1, "mark_milestone_done")
        instructions = "\n\n".join(
            [
                self.skills["journey"].body,
                self.skills["guard"].body,
                t.skill.body,
                "## Your task now\nRead the owner's message and choose ONE action. answer_slot: the message answers the "  # noqa: E501
                "pending question (give slot_value). answer_side_question: it asks something else (give topic_id if a "  # noqa: E501
                "library topic fits). go_back: they want to change an earlier step (give step). check_in: they want to "  # noqa: E501
                "report how the business is going (Goal Keeper only). correct_business: they correct a fact about their "  # noqa: E501
                "business from an earlier step (give fills). mark_milestone_done: they say a step of their goal "  # noqa: E501
                "is done (give milestone_id; you only propose it, code checks it and asks them to confirm). "
                "unclear: none of these. If they ask for anything on the guard list, set rule_id.",
            ]
        )
        decision = await llm.decide_turn(
            instructions,
            text,
            allowed,
            p.slot if p else None,
            opts,
            self.skills["detour"].topics,
            list(st.done),
            steps.open_profile_slots(t) if st.step == "profile" else None,
            correctable or None,
            open_steps or None,
        )
        if decision is not None:
            t.mark("model_decision", action=decision.action, model=llm.model_label("turn"))
        return decision

    def _apply(self, t: Turn, text: str, d: llm.TurnDecision) -> bool:
        st = t.state
        p = st.pending
        if d.action == "answer_slot" and st.step == "profile" and d.fills:
            fills = dict(d.fills)
            if p is not None and d.slot_value and p.slot not in fills:
                fills[p.slot] = d.slot_value  # the answer to the question asked counts too
            accepted = steps.profile_fill(t, fills, self._normalise)
            if accepted:
                t.mark("multi_fill", slots=sorted(accepted))
                return True
        if d.action == "answer_slot" and p is not None and d.slot_value:
            opts = [Option(**o) for o in p.options]
            values = {o.value for o in opts}
            v = d.slot_value.strip()
            if v not in values:
                v = self._normalise(p.slot, v, opts) or ""
            if v:
                self._slot(t, p.skill, p.slot, v)
                return True
            return False
        if d.action == "answer_side_question":
            # The reply allowlist: a library topic card, else the scope card, then the pending question.
            # Never a free-form answer: a guard miss here can't become rule-breaking help in words.
            if d.topic_id in self.skills["detour"].topics:
                t.say("lead", skill="detour")
                steps.show_topic(t, str(d.topic_id))
            else:
                steps.show_scope(t)
            t.mark("side_question", topic=d.topic_id if d.topic_id in self.skills["detour"].topics else steps.SCOPE_TOPIC)  # noqa: E501
            t.reask()
            return True
        if d.action == "go_back" and st.step in JOURNEY_STEPS:
            target = (
                d.step
                if d.step in st.done
                else (JOURNEY_STEPS[JOURNEY_STEPS.index(st.step) - 1] if st.step != "profile" else None)
            )
            if target:
                steps.reopen(t, target)
                return True
            return False
        if d.action == "correct_business" and d.fills and steps.correctable_fields(t):
            return steps.correct_business(t, d.fills, self._normalise)
        if d.action == "check_in" and st.goal_id:
            self.services.show_checkin(t)
            return True
        if d.action == "mark_milestone_done" and st.goal_id and d.milestone_id:
            if st.step != "goal_keeper":
                st.step = "goal_keeper"
            steps.mark_done(t, d.milestone_id.strip(), via="text")  # validated by code, then confirmed
            return True
        return False

    def _open_milestones(self, t: Turn) -> dict[str, str]:
        """The goal's steps not yet done (id: label), for the model to name one the owner says is done."""
        st = t.state
        if not st.goal_id or st.step != "goal_keeper":
            return {}
        goal = self.services.gk.goal(st.goal_id)
        return {m.id: tk.milestone_label(m.id, "en") for m in sorted(goal.milestones, key=lambda m: m.order) if m.done_at is None}  # noqa: E501

    def _normalise(self, slot: str, value: str, opts: list[Option]) -> str | None:
        """Validate a model-given slot value with code (money ranges, counts, option labels)."""
        if slot in MONEY_SLOTS and "|" in value:
            try:
                lo, hi = (Decimal(x) for x in value.split("|", 1))
            except InvalidOperation:
                return None
            if lo < 0 or hi < lo:
                return None
            return str(lo) if slot == "savings" else f"{lo}|{hi}"
        return self._parse_slot(slot, value, opts)

    def _parse_slot(self, slot: str, text: str, opts: list[Option]) -> str | None:
        if slot == "lang" and re.search(r"[一-鿿]", text) and not re.search(r"english|英文|英语", text, re.I):
            return "zh"
        matched = parse.match_option(text, opts, SLOT_SYNONYMS.get(slot), first=slot in FIRST_MENTION_SLOTS)
        if matched is not None:
            return matched
        if slot in YES_NO_SLOTS:
            yn = parse.yes_no(text)
            return None if yn is None else ("yes" if yn else "no")
        if slot == "shops":
            n = parse.count(text)
            return str(n) if n and 0 < n < 1000 else None
        if slot in MONEY_SLOTS:
            rng = parse.money_range(text)
            if rng is None:
                return None
            lo, hi = rng
            if slot == "savings":
                return str(lo)
            return f"{lo}|{hi}"
        if slot in ("start", "confirm_unit") and parse.yes_no(text):
            return "start" if slot == "start" else "confirm"
        return None

    def _max_turns(self, t: Turn) -> None:
        """After max_turns in a step, take the pending slot's default and move on (SPEC §4.1)."""
        st = t.state
        sk = self.skills[SKILL_FOR_STEP[st.step]]
        if sk.max_turns and st.turns_in_step > sk.max_turns and st.pending is not None:
            if st.pending.slot in sk.confirms:
                # a step completes only when the owner confirms it (SPEC §4.1; prereg addendum (13))
                t.mark("max_turns_no_default", slot=st.pending.slot)
                st.turns_in_step = 0
                return
            slot = next((s for s in sk.slots if s.id == st.pending.slot), None)
            default = (slot.default if slot else None) or next(
                iter(o["value"] for o in st.pending.options), None
            )
            if default is not None:
                t.mark("max_turns_default", slot=st.pending.slot)
                st.turns_in_step = 0
                self._slot(t, st.pending.skill, st.pending.slot, default)


def _own_lines(history: Any) -> list[str]:
    """The voice's context keeps Waypoint's own earlier messages only. The model that writes Waypoint's
    words never sees what the owner typed: it writes from code's beats (results/prereg.md addendum
    2026-10-20 (8))."""
    return [h for h in history if str(h).startswith("Waypoint:")]


def _fill_display(tpl: str, figures: dict[str, tuple[str, str]]) -> str:
    from agent.render import PLACEHOLDER

    return PLACEHOLDER.sub(
        lambda m: figures.get(m.group(2), ("", m.group(0)))[1] if m.group(1) == "fig" else m.group(0), tpl
    )


def _fill_bodies(outs: list[Out]) -> list[Out]:
    """A text written for a widget (a draft's prose) goes into that widget's body, not into the chat."""
    bodies = {o.beat.into: o.text for o in outs if o.kind == "text" and o.beat is not None and o.beat.into}
    if not bodies:
        return outs
    result: list[Out] = []
    for o in outs:
        if o.kind == "text" and o.beat is not None and o.beat.into in bodies:
            continue
        if o.kind == "widget" and o.widget is not None and o.widget.id in bodies:
            payload = o.widget.payload.model_copy(update={"body": bodies[o.widget.id] or ""})
            o = Out("widget", widget=o.widget.model_copy(update={"payload": payload}))
        result.append(o)
    return result


CONFIRM_WIDGETS = {"confirm_card", "profile_card", "cost_breakdown", "goal_summary"}


def _confirm_ok(ev: WidgetEvent, issued_type: str | None, step: str) -> bool:
    """A confirm must come from a confirm-capable card issued in this step, with a known value."""
    if issued_type not in CONFIRM_WIDGETS:
        return False
    if issued_type == "confirm_card":
        return ev.value in ("confirm", "edit", step)  # its buttons always say which step they confirm
    return ev.value in (None, "confirm", step)
