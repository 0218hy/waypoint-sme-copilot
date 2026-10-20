"""Step handlers: the scripted core of each Skill (SPEC §4.2–4.3).

Each step has `enter`, `on_event` (structured widget events) and `on_slot` (a value for the pending
slot, from a tap, parsed text or a validated model decision). Handlers call tools only through
`Turn.call`, so the active Skill's allowlist is enforced on every call.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from agent import options as O
from agent import toolkit as tk
from agent.state import JOURNEY_STEPS, STEP_LABELS, Step
from agent.turn import Turn
from agent.widgets import (
    ApprovalCard,
    ApprovalLine,
    AreaCard,
    AreaMap,
    ClosedOptions,
    ConfirmCard,
    ConsentCard,
    FundingMix,
    FundingOptions,
    GoalSummary,
    MapArea,
    MissingItems,
    MixSegment,
    Option,
    ProfileCard,
    RuleCard,
    SetasideSlider,
    SourceNote,
    TopicCard,
    UnitCompare,
    UploadPrompt,
    WidgetEvent,
)
from tools.models import CustomerGroup, FundingPlan, MoneyRange, Priority

# ------------------------------------------------------------------ navigation


def goto(t: Turn, step: Step) -> None:
    st = t.state
    if st.step in JOURNEY_STEPS and st.step not in st.done and step != st.step:
        if _artifact_confirmed(t, st.step):
            st.done.append(st.step)
    st.step = step
    st.turns_in_step = 0
    st.pending = None
    if step in st.stale:
        st.stale.remove(step)
    ENTER[step](t)


def _artifact_confirmed(t: Turn, step: str) -> bool:
    st = t.state
    return {
        "profile": st.profile.confirmed,
        "site": st.shortlist.confirmed,
        "cost": bool(st.cost_card and st.cost_card.confirmed),
        "funding": bool(st.funding and st.funding.confirmed),
        "goal_plan": st.goal_id is not None,
    }.get(step, False)


def reopen(t: Turn, step: Step) -> None:
    """Owner goes back to an earlier step. Later steps go stale and recompute when reached."""
    st = t.state
    if step not in JOURNEY_STEPS:
        return
    if step not in st.done and step not in st.stale and step != st.step:
        t.mark("ignored_event", reason="reopen_not_reached", target=step)
        return  # can't jump ahead to a step that hasn't been reached
    idx = JOURNEY_STEPS.index(step)
    for later in JOURNEY_STEPS[idx + 1 :]:
        if later in st.done and later not in st.stale:
            st.stale.append(later)
    if step in st.done:
        st.done.remove(step)
    if st.goal_id:
        st.revising = True
    if step == "profile":
        st.profile.confirmed = False
    elif step == "site":
        st.shortlist.confirmed = False
    if step in ("profile", "site", "cost") and st.cost_card is not None:
        st.cost_card.confirmed = False
    if step in ("profile", "site", "cost", "funding"):
        unconfirm_funding(t, f"reopen_{step}")
    t.say("reopened", {"step": STEP_LABELS[step][t.lang]}, skill="journey")
    goto(t, step)


def unconfirm_funding(t: Turn, why: str) -> None:
    """An input to the funding plan changed: its confirmation goes, and comes back only through the rules
    check at How to pay (prereg addendum 2026-10-20 (13))."""
    st = t.state
    if st.funding is not None and st.funding.confirmed:
        st.funding.confirmed = False
        t.mark("funding_unconfirmed", reason=why)


def maybe_topic(t: Turn, topic_id: str) -> None:
    """Raise a topic at most once, only if the active Skill lists it (SPEC §4.5)."""
    st = t.state
    if topic_id in st.raised_topics or topic_id not in t.skill.topics:
        return
    st.raised_topics.append(topic_id)
    show_topic(t, topic_id)


SCOPE_TOPIC = "T-SCOPE"


def show_scope(t: Turn) -> None:
    """A side question no library topic answers: the fixed scope card, never a free-form reply (the reply
    allowlist, results/prereg.md addendum 2026-10-20 (8)). The caller then asks the pending question again."""
    t.say("scope", skill="detour")
    show_topic(t, SCOPE_TOPIC)


def show_topic(t: Turn, topic_id: str) -> None:
    tp = tk.topic(topic_id, t.lang)
    say = t.text(tp["say"])
    more = t.text(tp["more"])
    t.show(
        TopicCard(topic_id=topic_id, title=tp["title"], say=say, more=more, source=SourceNote(**tp["source"]))
    )


# ------------------------------------------------------------------ welcome


def welcome_enter(t: Turn) -> None:
    """Greet in the interface's language (switchable any time), then ask for consent or to start."""
    st = t.state
    st.started = True
    st.lang_chosen = True
    t.say("hello")
    if st.host_mode.value == "embedded":
        t.say("ask_consent")
        _consent_card(t)
        st.pending = None
    else:
        sk = t.skills["welcome"]
        t.ask("welcome", "start", "invite_start", O.start_option(sk.label("start_label", t.lang)), default="start")  # noqa: E501


def welcome_slot(t: Turn, slot: str, value: str) -> None:
    if slot == "start":
        goto(t, "profile")


def welcome_event(t: Turn, ev: WidgetEvent) -> bool:
    if ev.event == "consent":
        if not isinstance(ev.value, bool):
            t.mark("ignored_event", reason="bad_consent_value")
            return True  # only a real yes or no counts; anything else changes nothing
        welcome_consent(t, ev.value, via="card")
        return True
    return False


def _consent_card(t: Turn) -> None:
    t.show(
        ConsentCard(
            reads=tk.consent_reads(t.lang),
            never=tk.consent_never(t.lang),
            withdraw=tk.consent_withdraw(t.lang),
        )
    )


def awaiting_consent(t: Turn) -> bool:
    st = t.state
    return st.step == "welcome" and st.host_mode.value == "embedded" and st.consent_feed is None


def welcome_consent(t: Turn, granted: bool, via: str) -> None:
    """The owner's yes or no to reading their accounts, from the card or typed (parsed by code)."""
    st = t.state
    st.consent_feed = granted
    t.mark("consent", granted=granted, via=via)
    if granted:
        t.call("feed.read", tk.feed, st)
        t.say("consent_granted")
    else:
        t.say("consent_declined")
    goto(t, "profile")


def consent_again(t: Turn, lead: bool = True) -> bool:
    """After a typed detour before the owner answered, show the consent card again so it stays usable
    (the earlier card counts as answered once the owner has typed)."""
    if not awaiting_consent(t):
        return False
    if lead:
        t.say("back_to_question", skill="journey")
    _consent_card(t)
    return True


# ------------------------------------------------------------------ profile

PROFILE_ORDER = ["shops", "monthly_profit", "spare_cash", "customers", "budget", "window"]


def profile_enter(t: Turn) -> None:
    st = t.state
    if st.consent_feed and not st.profile.sources:
        feed = t.call("feed.read", tk.feed, st)
        st.profile = t.call("profile.from_feed", tk.profile_from_feed, feed)
    if st.consent_feed:
        _profile_card(t)
        t.say("card_intro_feed")
        _glance_card(t)
    profile_next(t)


def _glance_card(t: Turn) -> None:
    """"Your business at a glance": ratios from the same feed (only with the feed; none are asked for)."""
    feed = t.call("feed.read", tk.feed, t.state)
    figs, payload = t.call("ratios.chain", tk.business_glance, feed, t.lang)
    t.add(*figs)
    t.show(payload)
    t.say("glance_intro")


def _profile_card(t: Turn) -> None:
    figs, fields = tk.profile_fields(t.state.profile, t.lang)
    t.add(*figs)
    t.show(ProfileCard(fields=fields, simulated_feed=bool(t.state.consent_feed)))


def _profile_has(t: Turn, slot: str) -> bool:
    p = t.state.profile
    return {
        "shops": p.shops is not None,
        "monthly_profit": p.monthly_profit_cny is not None,
        "spare_cash": p.spare_cash_cny is not None,
        "customers": bool(p.customers),
        "budget": "budget" in t.state.profile_asked,
        "window": p.opening_window_months is not None,
    }[slot]


def profile_next(t: Turn) -> None:
    for slot in PROFILE_ORDER:
        if not _profile_has(t, slot):
            line, opts, default = {
                "shops": ("ask_shops", O.shops(t.lang), None),
                "monthly_profit": ("ask_profit", O.profit(t.lang), None),
                "spare_cash": ("ask_spare", O.spare(t.lang), None),
                "customers": ("ask_customers", O.customers(t.lang), None),
                "budget": ("ask_budget", O.budget(t.lang), "not_sure"),
                "window": ("ask_window", O.window(t.lang), None),
            }[slot]
            t.ask("profile", slot, line, opts, default=default)
            return
    # all filled: complete computed fields, then confirm
    st = t.state
    st.profile = t.call("profile.floor", tk.complete_profile, st.profile)
    sk = t.skill  # one summary card to confirm; "Change something" brings back the editable card
    t.say("confirm_intro")
    t.show(
        ConfirmCard(
            step="profile",
            title=STEP_LABELS["profile"][t.lang],
            items=tk.profile_summary(st.profile, t.lang),
            confirm_label=sk.label("confirm_label", t.lang),
            edit_label=sk.label("edit_label", t.lang),
        )
    )
    st.pending = None


PROFILE_FORMATS = {
    "shops": "a count, e.g. 30",
    "monthly_profit": "CNY per month as 'low|high' digits",
    "spare_cash": "CNY as 'low|high' digits",
    "customers": "one of young_adults, students, office_workers, families, tourists",
    "budget": "SGD as 'low|high' digits, or not_sure",
    "window": "one of 6_12, 12_18, 18_24, no_rush",
}


def open_profile_slots(t: Turn) -> dict[str, str]:
    return {s: PROFILE_FORMATS[s] for s in PROFILE_ORDER if not _profile_has(t, s)}


def _profile_options(slot: str, lang: Any) -> list[Option]:
    fn = {"shops": O.shops, "monthly_profit": O.profit, "spare_cash": O.spare, "customers": O.customers,
          "budget": O.budget, "window": O.window}[slot]
    return fn(lang)


def profile_fill(t: Turn, fills: dict[str, str], normalise: Any) -> list[str]:
    """Several answers from one message: the model proposes, code validates each, then asks what's left."""
    accepted: list[str] = []
    for slot in PROFILE_ORDER:
        raw = fills.get(slot)
        if raw is None or _profile_has(t, slot):
            continue
        opts = _profile_options(slot, t.lang)
        value = raw if raw in {o.value for o in opts} else normalise(slot, str(raw), opts)
        if value is None:
            continue
        _set_profile(t, slot, value)
        accepted.append(slot)
    if accepted:
        t.state.pending = None
        profile_next(t)
    return accepted


def profile_slot(t: Turn, slot: str, value: str) -> None:
    _set_profile(t, slot, value)
    t.state.pending = None
    profile_next(t)


def _set_profile(t: Turn, slot: str, value: str) -> list[str]:
    """Set one profile answer; returns the figures held at the feed's (the owner's was higher)."""
    p = t.state.profile
    if slot == "shops":
        p.shops = int(value)
        p.sources["shops"] = "owner"
    elif slot == "monthly_profit":
        lo, hi = O.PROFIT_BANDS_CNY.get(value) or _range(value)
        p.monthly_profit_cny = MoneyRange(low=lo, high=hi)
        p.sources["monthly_profit"] = "owner"
    elif slot == "spare_cash":
        lo, hi = O.SPARE_BANDS_CNY.get(value) or _range(value)
        p.spare_cash_cny = (lo + hi) / 2
        p.sources["spare_cash"] = "owner"
    elif slot == "customers":
        p.customers = [CustomerGroup(value)]
    elif slot == "budget":
        t.state.profile_asked.append("budget")
        if value != "not_sure":
            lo, hi = O.BUDGET_BANDS_SGD.get(value) or _range(value)
            p.budget_sgd = MoneyRange(low=lo, high=hi)
    elif slot == "window":
        p.opening_window_months = O.WINDOW_MONTHS.get(value, 18)
    held = tk.hold_to_feed(t.state)
    _say_held(t, held)
    return held


def _say_held(t: Turn, held: list[str]) -> None:
    """The owner gave a figure above what the bank feed shows: the plan keeps the feed's figure."""
    for key in held:
        label = FIELD_LABELS.get(key, (key.replace("_", " "), key))[1 if t.lang == "zh" else 0]
        t.mark("held_to_feed", field=key)
        t.say("held_to_feed", skill="journey", facts={"figure": label})


CORRECTABLE_STEPS = ("site", "cost", "funding", "goal_plan")
FIELD_LABELS = {
    "shops": ("shops", "门店数"),
    "monthly_profit": ("monthly profit", "月利润"),
    "spare_cash": ("spare cash", "闲置资金"),
    "customers": ("main customers", "主要顾客"),
    "budget": ("budget", "预算"),
    "window": ("when you hope to open", "希望开业时间"),
    "best_shop_cups_per_day": ("your best shop's cups a day", "最好门店的日杯量"),
    "avg_shop_cups_per_day": ("an average shop's cups a day", "平均门店的日杯量"),
}


def correctable_fields(t: Turn) -> dict[str, str]:
    """Business facts the owner can correct by typing, after the profile step and before a goal exists."""
    st = t.state
    if st.step not in CORRECTABLE_STEPS or st.goal_id or not st.profile.confirmed:
        return {}
    return dict(PROFILE_FORMATS)


def correct_business(t: Turn, fills: dict[str, str], normalise: Any) -> bool:
    """The owner corrected a business fact later in the journey: code validates each value, updates the
    profile, then recomputes what depends on it (the area list for customers or budget; the funding and the
    plan for money, shops or timing)."""
    st = t.state
    changed: list[str] = []
    held: list[str] = []
    for slot in PROFILE_ORDER:
        raw = fills.get(slot)
        if raw is None:
            continue
        opts = _profile_options(slot, t.lang)
        value = raw if raw in {o.value for o in opts} else normalise(slot, str(raw), opts)
        if value is None:
            continue
        if slot == "budget" and "budget" in st.profile_asked:
            st.profile_asked.remove("budget")
        if slot in _set_profile(t, slot, value):
            held.append(slot)  # above the feed's figure: noted as not verified, nothing to recompute
        else:
            changed.append(slot)
    if not changed:
        if held:
            t.reask()
        return bool(held)
    st.profile = t.call("profile.floor", tk.complete_profile, st.profile, skill=t.skills["profile"])
    t.mark("profile_corrected", fields=changed)
    labels = [FIELD_LABELS[c][1 if t.lang == "zh" else 0] for c in changed]
    sep = "、" if t.lang == "zh" else ", "
    if {"customers", "budget"} & set(changed) and st.step != "site" and "site" in st.done:
        site = STEP_LABELS["site"][t.lang]
        t.say("corrected", skill="journey", facts={"changed": sep.join(labels), "recomputed": site})
        reopen(t, "site")
        return True
    later = STEP_LABELS["funding"][t.lang]
    unconfirm_funding(t, "profile_corrected")
    if st.step not in ("funding", "goal_plan"):
        for step in ("funding", "goal_plan"):
            if step in st.done:
                st.done.remove(step)
                if step not in st.stale:
                    st.stale.append(step)
    if st.step in ("funding", "goal_plan"):
        if "goal_plan" in st.done and "goal_plan" not in st.stale:
            st.stale.append("goal_plan")
        if st.funding is not None:
            st.funding.confirmed = False
        st.done = [s for s in st.done if s != "funding"]
        st.pending = None
        t.say("corrected", skill="journey", facts={"changed": sep.join(labels), "recomputed": later})
        goto(t, "funding")
        return True
    t.say("corrected", skill="journey", facts={"changed": sep.join(labels), "recomputed": later})
    t.reask()
    return True


def _range(value: str) -> tuple[Decimal, Decimal]:
    lo, hi = value.split("|")
    return Decimal(lo), Decimal(hi)


def profile_event(t: Turn, ev: WidgetEvent) -> bool:
    st = t.state
    if ev.event == "edit":
        tk.edit_profile_field(st.profile, str(ev.data.get("field") or ev.data.get("key")), ev.value)
        _say_held(t, tk.hold_to_feed(st))
        st.profile = t.call("profile.floor", tk.complete_profile, st.profile)
        t.say("step_changed", skill="journey")
        _profile_card(t)
        profile_next(t)
        return True
    if ev.event == "confirm":
        if ev.value == "edit":
            _profile_card(t)
            return True
        if not all(_profile_has(t, s) for s in PROFILE_ORDER):
            profile_next(t)  # a confirm before every question is answered just asks the next one
            return True
        st.profile.confirmed = True
        t.say("done")
        goto(t, "site")
        return True
    return False


# ------------------------------------------------------------------ site


def site_enter(t: Turn) -> None:
    st = t.state
    if st.shortlist.priority is None:
        t.ask("site-finder", "priority", "ask_priority", O.priority(t.lang), default="near_customers")
    else:
        _show_map(t)


def _show_map(t: Turn) -> None:
    st = t.state
    ranked = t.call(
        "sites.rank_areas", tk.rank, st.profile, st.shortlist.priority, st.shortlist.ruled_out_areas
    )
    st.shortlist.ranked = ranked
    # recommend only areas with units to lease (an area with no rent data would otherwise be scored on
    # customer fit alone and rise); every area keeps its shade on the map
    picks = [a for a in ranked if tk.has_listings(a.area_id)][:3]
    top = [a.area_id for a in picks]
    names = tk.area_names()
    payload = AreaMap(
        geojson_url="/geo/planning_areas.geojson",
        areas=[
            MapArea(id=a.area_id, name=names.get(a.area_id, a.area_id), score=round(a.score, 1), rank=i + 1)
            for i, a in enumerate(ranked)
        ],
        top=top,
        reasons={a.area_id: tk.reason_lines(a.reasons, t.lang) for a in picks},
        sources=tk.area_sources(),
    )
    t.say("map_intro")
    t.show(payload)
    t.state.pending = None
    opts = [Option(value=a, label=names.get(a, a)) for a in top]
    from agent.widgets import QuickReplies

    wid = t.show(QuickReplies(slot="area", options=opts, default=top[0] if top else None))
    from agent.state import Pending

    t.state.pending = Pending(
        skill="site-finder",
        slot="area",
        line="map_intro",
        widget_id=wid,
        options=[o.model_dump() for o in opts],
    )


def site_slot(t: Turn, slot: str, value: str) -> None:
    st = t.state
    if slot == "priority":
        st.shortlist.priority = Priority(value)
        st.pending = None
        _show_map(t)
    elif slot == "area":
        _select_area(t, value)
    elif slot == "unit":
        _select_unit(t, value)
    elif slot == "confirm_unit":
        _confirm_unit(t, value == "confirm")


def _select_area(t: Turn, area_id: str) -> None:
    st = t.state
    if area_id not in {a.area_id for a in st.shortlist.ranked} or area_id not in tk.area_names():
        t.mark("ignored_event", reason="unknown_area")
        return
    st.selected_area = area_id
    st.pending = None
    score = next((a for a in st.shortlist.ranked if a.area_id == area_id), None)
    area = t.call("sites.area_profile", tk.area, area_id)
    figs, stats, factors, ages = tk.area_card_data(area, score, st.profile, t.lang)
    t.add(*figs)
    t.show(
        AreaCard(
            area_id=area_id,
            name=area.name,
            score=round(score.score, 1) if score else 0.0,
            factors=factors,
            stats=stats,
            age_bands=ages,
            sources=tk.area_sources(area),
            simulated_fields=area.simulated_fields,
        )
    )
    maybe_topic(t, "T-STATION-TRAFFIC")
    units, over_budget = t.call("sites.list_units", tk.units, area_id, st.profile, st.shortlist)
    if not units:
        t.say("no_units", {"area": area.name})
        _show_map(t)
        return
    if area_id not in st.shortlist.area_ids:
        st.shortlist.area_ids.append(area_id)
    rows = []
    for u in units[:3]:
        ufigs, row = t.call("sites.break_even", tk.unit_row, u, st.profile, t.lang)
        t.add(*ufigs)
        rows.append(row)
    st.shortlist.unit_ids = [r.id for r in rows]
    t.say("over_budget" if over_budget else "area_intro", {"area": area.name})
    t.show(UnitCompare(units=rows))
    t.say("simulated_note")
    if any(u.gto_pct for u in units[:3]):
        maybe_topic(t, "T-GTO")
    opts = [Option(value=r.id, label=f"{r.mall} {r.unit_no}") for r in rows]
    t.ask("site-finder", "unit", "units_intro", opts, default=None)


def _select_unit(t: Turn, unit_id: str) -> None:
    """Picking a unit is the confirmation; going back is one tap on the step rail."""
    st = t.state
    if unit_id not in st.shortlist.unit_ids:
        t.mark("ignored_event", reason="unit_not_offered")
        return
    st.shortlist.chosen_unit_id = unit_id
    st.pending = None
    u = tk.unit(unit_id)
    t.say("unit_chosen", {"unit": f"{u.mall} {u.unit_no}"})
    _confirm_unit(t, True)


def _confirm_unit(t: Turn, ok: bool) -> None:
    st = t.state
    if not ok:
        st.shortlist.chosen_unit_id = None
        _show_map(t)
        return
    st.shortlist.confirmed = True
    if st.cost_card and st.cost_card.unit_id != st.shortlist.chosen_unit_id:
        st.cost_card = None
        st.cost_asked = []
    goto(t, "cost")


def site_event(t: Turn, ev: WidgetEvent) -> bool:
    if ev.event in ("select_area", "shortlist"):
        _select_area(t, str(ev.value))
        return True
    if ev.event == "select_unit":
        _select_unit(t, str(ev.value))
        return True
    if ev.event == "confirm":
        if t.state.shortlist.chosen_unit_id is None:
            return False
        _confirm_unit(t, ev.value != "edit")
        return True
    return False


# ------------------------------------------------------------------ cost


def cost_enter(t: Turn) -> None:
    _estimate(t)
    _show_cost(t, "card_intro")
    maybe_topic(t, "T-RESIDENT-DIRECTOR")
    cost_next(t)


def _unit_name(t: Turn) -> str:
    u = tk.unit(t.state.shortlist.chosen_unit_id or "")
    return f"{u.mall} {u.unit_no}"


def _estimate(t: Turn) -> None:
    st = t.state
    unit = tk.unit(st.shortlist.chosen_unit_id or "")
    level = st.cost_card.fitout_level if st.cost_card else "standard"
    mgr = st.cost_card.manager_plan if st.cost_card else "hire_local"
    overrides = tk.overrides_from(st.cost_card)
    st.cost_card = t.call("costs.estimate", tk.estimate, unit, st.profile, level, mgr, st.quotes, overrides)


def _show_cost(t: Turn, line: str, read_only: bool = False) -> None:
    st = t.state
    assert st.cost_card is not None
    figs, payload = tk.cost_breakdown(st.cost_card, t.lang, read_only=read_only)
    t.add(*figs)
    zh = t.lang == "zh"
    fit = {"basic": ("a basic fit-out", "简洁装修"), "standard": ("a standard fit-out", "标准装修"),
           "premium": ("a premium fit-out", "高端装修")}.get(st.cost_card.fitout_level, ("", ""))
    mgr = ("派自己的店长", "sending their own manager") if st.cost_card.manager_plan == "send_own" else (
        "在新加坡招店长", "a manager hired in Singapore")
    t.say(line, {"unit": _unit_name(t)},
          facts={"fit_out": fit[1] if zh else fit[0], "manager": mgr[0] if zh else mgr[1]})
    t.show(payload)
    if not read_only:
        _show_econ(t, "econ_intro" if line == "card_intro" else None)


def _show_econ(t: Turn, line: str | None) -> None:
    """"Unit economics & payback" for this unit and cost card (re-shown whenever the cost changes)."""
    st = t.state
    assert st.cost_card is not None
    u = tk.unit(st.shortlist.chosen_unit_id or "")
    fs = t.call("feed.read", tk.feed, st) if st.consent_feed else None
    figs, payload, _ = t.call("unit_econ.card", tk.unit_economics, u, st.cost_card, st.profile, t.lang, fs=fs)
    t.add(*figs)
    t.show(payload)
    if line:
        t.say(line, {"unit": _unit_name(t)})


def cost_next(t: Turn) -> None:
    """One question: anything to change? The card already uses sensible defaults."""
    st = t.state
    assert st.cost_card is not None
    t.ask(
        "cost", "adjust", "adjust_ask",
        O.cost_adjust(t.lang, st.cost_card.fitout_level, st.cost_card.manager_plan),
        default="looks_right",
    )


def _cost_finish(t: Turn) -> None:
    st = t.state
    assert st.cost_card is not None
    missing = t.call("costs.missing_items", tk.missing, st.cost_card, st.quotes, t.lang)
    if missing:
        t.say("missing_intro")
        t.show(MissingItems(items=missing))
    maybe_topic(t, "T-HIRING-LOCALS")
    st.cost_card.confirmed = True
    st.pending = None
    t.say("done")
    goto(t, "funding")


def cost_slot(t: Turn, slot: str, value: str) -> None:
    st = t.state
    assert st.cost_card is not None
    st.pending = None
    if slot == "adjust":
        if value == "looks_right":
            _cost_finish(t)
            return
        if value in ("basic", "standard", "premium"):
            st.cost_card.fitout_level = value  # type: ignore[assignment]
            _estimate(t)
            _show_cost(t, "updated")
        elif value in ("send_own", "hire_local"):
            st.cost_card.manager_plan = value  # type: ignore[assignment]
            _estimate(t)
            if value == "send_own":
                maybe_topic(t, "T-EP-SALARY")
            _show_cost(t, "updated")
        elif value == "add_quote":
            t.say("ask_quotes")
            t.show(UploadPrompt())
            t.ask("cost", "quotes", "ask_quotes", O.quotes(t.lang, t.services.demo()), default="no_quotes",
                  say_line=False)
            return
    elif slot == "quotes":
        if value == "demo_quote":
            doc_id = t.services.ingest_demo_quote(st.owner_id)
            _read_quote(t, doc_id)
            return
    cost_next(t)


def _read_quote(t: Turn, doc_id: str) -> None:
    st = t.state
    quote, mode, image_url, ignored = t.call(
        "reader.read_document", t.services.load_quote, st.owner_id, doc_id
    )
    if quote is None or not quote.lines:
        t.say("quote_failed")
        cost_next(t)
        return
    quote = tk.match_quote(quote)
    st.quotes = [q for q in st.quotes if q.doc_id != doc_id] + [quote]
    figs, payload = tk.upload_payload(quote, image_url, mode, t.lang)
    t.add(*figs)
    t.say("quote_read")
    if ignored:
        t.mark("ignored_document_instruction", doc_id=doc_id, count=len(ignored))
    t.show(payload)
    st.pending = None


def cost_event(t: Turn, ev: WidgetEvent) -> bool:
    st = t.state
    if ev.event == "upload":
        _read_quote(t, str(ev.value))
        return True
    if ev.event in ("accept_line", "reject_line", "accept_all"):
        if ev.event == "accept_all":
            doc = str(ev.value or ev.data.get("doc_id") or "")
            done = tk.accept_all_lines(st.quotes, doc)
            if not done and tk.lines_to_check(st.quotes, doc):
                t.say("check_left")  # lines read with low confidence: one tap each
        else:
            done = tk.set_line_status(
                st.quotes, str(ev.value), "accepted" if ev.event == "accept_line" else "rejected"
            )
        if done:
            _estimate(t)
            _show_cost(t, "updated")
            cost_next(t)
        return True
    if ev.event in ("assign_line", "set_coverage"):
        # which cost line a quote line is for, or whether a quote covers all of a line: re-cost once the
        # document is decided (before that, the accept / reject taps re-cost it)
        if ev.event == "assign_line":
            line_id = str(ev.value or ev.data.get("id") or "")
            key = ev.data.get("key")
            changed = tk.assign_line(st.quotes, line_id, str(key) if key else None)
            doc_id = tk.doc_of_line(st.quotes, line_id)
        else:
            doc_id = str(ev.data.get("doc_id") or "")
            changed = tk.set_coverage(
                st.quotes, doc_id, str(ev.value or ev.data.get("key") or ""), bool(ev.data.get("whole"))
            )
        if changed and doc_id is not None and tk.doc_decided(st.quotes, doc_id):
            _estimate(t)
            _show_cost(t, "updated")
            cost_next(t)
        return True
    if ev.event == "edit" and st.widget_types.get(ev.widget_id) == "unit_economics":
        # the owner's own cups-a-day figure for the Singapore shop: one more row on the card
        if not tk.set_owner_cups(st.profile, ev.value if ev.value is not None else ev.data.get("cups")):
            t.mark("ignored_event", reason="invalid_input", event=ev.event)
            return True
        _show_econ(t, "econ_owner")
        cost_next(t)
        return True
    if ev.event == "edit_line":
        assert st.cost_card is not None
        tk.set_override(st.cost_card, str(ev.data.get("id") or ev.data.get("key")), ev.value)
        _estimate(t)
        _show_cost(t, "updated")
        cost_next(t)
        return True
    if ev.event == "mark_included":
        assert st.cost_card is not None
        if str(ev.value) not in st.cost_card.missing:
            st.cost_card.missing.append(f"included:{ev.value}")
        return True
    if ev.event == "confirm":
        if ev.value == "edit":
            cost_next(t)
            return True
        _cost_finish(t)
        return True
    return False


# ------------------------------------------------------------------ funding


def funding_enter(t: Turn) -> None:
    st = t.state
    if st.funding is None:
        st.funding = FundingPlan()
    unconfirm_funding(t, "funding_entered")  # decided again here, through the rules check
    basics = t.call("funding.gap", tk.funding_basics, st)
    t.add(*basics.figures)
    st.funding.floor_cny, st.funding.buffer_cny = basics.floor, basics.buffer
    t.say("gap_intro")
    opts_payload, opt_figs = t.call("funding.options", tk.funding_options, st, t.lang)
    t.add(*opt_figs)
    t.show(opts_payload)
    _bank_cards_beat(t, opts_payload)
    closed: ClosedOptions = t.call("funding.closed", tk.closed_options, t.lang)
    t.show(closed)
    maybe_topic(t, "T-WEBANK-ROLE")
    wall = t.call("plan.wall", tk.wall, st)
    if st.funding.setaside_share > wall:
        st.funding.setaside_share = wall
    _simulate_and_show(t, intro=True)


def _bank_cards_beat(t: Turn, payload: FundingOptions) -> None:
    """WeBank's "yes" at home, from the bank cards code built; the home working-capital line only when its
    card is shown (the feed's balance is below the usual level)."""
    ids = {c.id for c in payload.bank_cards}
    if not ids:
        return
    t.say("webank_yes_home" if "webank_home_wc" in ids else "webank_yes")


def _simulate_and_show(t: Turn, intro: bool = False) -> None:
    st = t.state
    assert st.funding is not None
    result = t.call("plan.simulate", tk.simulate, st)
    st.plan = result
    figs = tk.plan_figs(result)
    t.add(*figs)
    if intro:
        t.say("slider_intro")
    payload = SetasideSlider(
        share=float(st.funding.setaside_share),
        wall=float(result.wall_share),
        preview_url="/api/preview/setaside",
        chart=tk.chart(result, st.start_date, t.lang),
        open_likely="plan.open_likely",
        open_p95="plan.open_p95",
        floor_risk="plan.floor_risk",
        monthly_amount="plan.setaside_monthly",
        opened_share="plan.opened_share",
    )
    t.show(payload)
    _show_compare(t)
    if intro:
        maybe_topic(t, "T-SAFETY-FLOOR")
    if result.open_likely_week is None or result.open_p95_week is None:
        t.say("not_within_horizon")
    else:
        t.say("slider_set")
        _window_check(t, result)
    t.ask("funding", "lever", "levers_ask", O.levers(t.lang), default="looks_good")


def _show_compare(t: Turn) -> None:
    """Compare funding plans, under the slider: each column one full solve at the share just committed, so it
    always matches the slider. No beat of its own: the cards and the figures say it."""
    payload, figs = t.call("plan.simulate", tk.funding_compare, t.state, t.lang)
    t.add(*figs)
    t.show(payload)


def _window_check(t: Turn, result: Any) -> None:
    """Code compares the likely opening with when the owner hoped to open; the model only says it."""
    st = t.state
    assert st.funding is not None
    hoped = st.profile.opening_window_months
    if hoped is None or result.open_likely_week is None:
        return
    if result.open_likely_week * 12 / 52 <= hoped + 0.5:
        return
    label = next((o.label for o in O.window(t.lang) if O.WINDOW_MONTHS.get(o.value) == hoped), None)
    at_limit = st.funding.setaside_share >= Decimal(str(result.wall_share))
    t.say(
        "window_miss",
        facts={
            "hoped_for": label or "",
            "set_aside_at_safe_limit": "yes" if at_limit else "no",
        },
    )


def funding_slot(t: Turn, slot: str, value: str) -> None:
    st = t.state
    assert st.funding is not None
    st.pending = None
    if slot == "lever":
        if value == "looks_good":
            _funding_review(t)
        elif value == "add_savings":
            t.ask("funding", "savings", "ask_savings", O.savings(t.lang), default="none")
        elif value == "rent_free":
            t.ask("funding", "rent_free", "ask_rent_free", O.rent_free(t.lang), default="1")
        elif value == "partner":
            st.raised_topics = [x for x in st.raised_topics if x != "T-PARTNER"]
            maybe_topic(t, "T-PARTNER")
            t.ask("funding", "partner", "levers_ask", O.partner(t.lang), default="skip")
    elif slot == "savings":
        had = st.funding.own_savings_cny > 0
        st.funding.own_savings_cny = O.SAVINGS_CNY.get(
            value, Decimal(value) if value.replace(".", "").isdigit() else Decimal(0)
        )
        if (st.funding.own_savings_cny > 0) != had:
            _reshow_options(t)  # own savings opens (or closes) to this owner: the ranking changes
        _simulate_and_show(t)
    elif slot == "rent_free":
        st.funding.rent_free_months = Decimal(value)
        _simulate_and_show(t)
    elif slot == "partner":
        had = st.funding.partner_equity_share > 0
        st.funding.partner_equity_share = Decimal("0.30") if value == "include" else Decimal("0")
        st.funding.partner_considered = value == "include"
        if (st.funding.partner_equity_share > 0) != had:
            _reshow_options(t)
        _simulate_and_show(t)
    elif slot == "share":
        _commit_share(t, Decimal(value))


def _reshow_options(t: Turn) -> None:
    """The options card again, re-ranked, when what the owner said opens or closes a route to them."""
    opts, figs = t.call("funding.options", tk.funding_options, t.state, t.lang)
    t.add(*figs)
    t.show(opts)


def _share(value: object) -> Decimal | None:
    """A set-aside share from the slider: a number between 0 and 1, else None."""
    from decimal import InvalidOperation

    try:
        share = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return share if Decimal(0) <= share <= Decimal(1) else None


def _commit_share(t: Turn, share: Decimal) -> None:
    st = t.state
    assert st.funding is not None
    wall = t.call("plan.wall", tk.wall, st)
    if share > wall:
        _rule_card(t, "R5")
        share = wall
    st.funding.setaside_share = share
    _simulate_and_show(t)


def _funding_review(t: Turn) -> None:
    st = t.state
    assert st.funding is not None
    violations = t.call("rules.check_plan", tk.check_plan, st)
    if violations:
        for rid in violations[:2]:
            _rule_card(t, rid)
        t.ask("funding", "lever", "levers_ask", O.levers(t.lang), default="add_savings")
        return
    figs, segs, total = tk.mix(st)
    t.add(*figs)
    t.say("mix_intro")
    t.show(FundingMix(total=total, segments=[MixSegment(**s) for s in segs]))
    st.funding.confirmed = True
    t.say("done")
    goto(t, "goal_plan")


def funding_event(t: Turn, ev: WidgetEvent) -> bool:
    st = t.state
    assert st.funding is not None
    if ev.event == "slider_commit":
        share = _share(ev.value)
        if share is None:
            t.mark("ignored_event", reason="bad_share")
            return True
        _commit_share(t, share)
        return True
    if ev.event == "toggle_option" and isinstance(ev.data.get("options"), list):
        _choose_funding(t, ev)
        return True
    if ev.event == "toggle_option":
        oid = str(ev.data.get("id", ev.value))
        status = tk.option_status(oid)
        if status is None:
            t.mark("ignored_event", reason="unknown_option")
            return True
        if status == "closed":
            for rid in tk.option_rules(oid)[:1]:
                _rule_card(t, rid)
            return True
        if not tk.option_in_plan(oid):
            # a bank card is never switched into the Singapore plan; counting home working capital is R1
            closing = tk.never_in_plan_rule(oid)
            if closing is not None and ev.data.get("on", True) is True:
                _rule_card(t, closing)
            else:
                t.mark("ignored_event", reason="not_a_plan_route", option=oid)
            return True
        tk.toggle_option(st.funding, oid, ev.data.get("on", True) is True)
        _simulate_and_show(t)
        return True
    if ev.event == "confirm":
        if ev.value == "edit":
            t.ask("funding", "lever", "levers_ask", O.levers(t.lang), default="looks_good")
            return True
        violations = t.call("rules.check_plan", tk.check_plan, st)
        if violations:
            for rid in violations[:2]:
                _rule_card(t, rid)
            return True
        st.funding.confirmed = True
        t.say("done")
        goto(t, "goal_plan")
        return True
    return False


def _choose_funding(t: Turn, ev: WidgetEvent) -> None:
    """"Choose this funding" on the compare view: that column's toggle_option actions in one go (own
    savings with the amount the owner typed), then the slider's share through the same wall check as the
    slider. Only the savings and the partner switch here; every action is checked before anything changes."""
    st = t.state
    assert st.funding is not None
    items = ev.data.get("options")
    assert isinstance(items, list)
    allowed = {"own_savings", "partner_equity"}
    toggles: list[tuple[str, bool, Decimal | None]] = []
    for item in items:
        ok = isinstance(item, dict) and str(item.get("id")) in allowed and isinstance(item.get("on"), bool)
        if not ok:
            t.mark("ignored_event", reason="bad_compare_choice")
            return
        oid, on = str(item["id"]), bool(item["on"])
        amount = None
        if oid == "own_savings" and on:
            amount = tk.savings_in_range(st, item.get("amount"))
            if amount is None:
                t.mark("ignored_event", reason="bad_savings")
                return
        partner_open = st.funding.partner_considered or st.funding.partner_equity_share > 0
        if oid == "partner_equity" and on and not partner_open:
            t.mark("ignored_event", reason="partner_not_open")  # the owner hasn't said a partner is possible
            return
        toggles.append((oid, on, amount))
    share = _share(ev.data.get("share")) if "share" in ev.data else st.funding.setaside_share
    if share is None:
        t.mark("ignored_event", reason="bad_share")
        return
    before = (st.funding.own_savings_cny > 0, st.funding.partner_equity_share > 0)
    for oid, on, amount in toggles:
        tk.toggle_option(st.funding, oid, on and amount != 0)
        if oid == "own_savings" and amount is not None:
            st.funding.own_savings_cny = amount
    if (st.funding.own_savings_cny > 0, st.funding.partner_equity_share > 0) != before:
        _reshow_options(t)  # a route opens or closes to this owner: the ranking changes
    _commit_share(t, share)


# ------------------------------------------------------------------ goal plan


def goal_plan_enter(t: Turn) -> None:
    st = t.state
    if st.funding is None or not st.funding.confirmed:
        # no plan without a funding plan the rules passed and the owner confirmed (the Skill's `requires`)
        t.mark("ignored_event", reason="funding_not_confirmed", target="goal_plan")
        goto(t, "funding")
        return
    if st.goal_id:
        st.plan = t.call("plan.simulate", t.services.replan_for_revision, st, skill=t.skills["funding"])
    elif st.plan is None:
        st.plan = t.call("plan.simulate", tk.simulate, st, skill=t.skills["funding"])
    figs, payload = t.call("timeline.build", tk.timeline_payload, st, t.lang)
    t.add(*figs)
    t.say("timeline_intro")
    t.show(payload)
    maybe_topic(t, "T-LENDER-CONSENT")
    gfigs, sentence, fig_ids, assumptions = t.call("goal.summary", tk.goal_sentence, st, t.lang)
    t.add(*gfigs)
    t.say("summary_intro")
    t.show(GoalSummary(sentence=t.text(sentence), figures=fig_ids, assumptions=assumptions))
    st.goal_prefs = {}
    goal_plan_next(t)


def goal_plan_next(t: Turn) -> None:
    """Defaults are shown on the approval card; changing them is optional."""
    st = t.state
    prefs = st.goal_prefs
    prefs.setdefault("checkin_frequency", t.services.user_pref(st.owner_id, "checkin_frequency", "monthly"))
    prefs.setdefault("email_amounts", bool(t.services.user_pref(st.owner_id, "email_amounts", False)))
    prefs.setdefault("recurring_setaside", False)
    _approval(t)
    t.ask("goal-plan", "extras", "extras_ask", O.goal_extras(t.lang, st.host_mode.value == "embedded",
                                                              bool(prefs["recurring_setaside"])),
          default=None, say_line=False)


def _approval(t: Turn) -> None:
    st = t.state
    action = "revise_goal" if st.goal_id else "create_goal"
    payload = tk.goal_payload(st)
    wid = st.next_widget_id()
    from agent.approval import new_card

    card = new_card(action, st.owner_id, payload, wid)  # type: ignore[arg-type]
    st.cards[wid] = card
    title = (
        t.skills["goal-plan"].label("approve_title", t.lang)
        if action == "create_goal"
        else t.skills["goal-keeper"].label("revise_title", t.lang)
    )
    prefs = st.goal_prefs
    labels = {o.value: o.label for o in O.frequency(t.lang)}
    freq = labels.get(str(prefs.get("checkin_frequency", "monthly")), "")
    t.say(
        "approve_intro",
        skill="goal-plan",
        facts={
            "reminders": freq,
            "amounts_in_emails": "yes" if prefs.get("email_amounts") else "no",
            "monthly_transfer": "yes" if prefs.get("recurring_setaside") else "no",
        },
    )
    t.show(
        ApprovalCard(
            action=action,
            title=title,
            lines=[ApprovalLine(**ln) for ln in tk.approval_lines(st, t)],
            card_hash=card.card_hash,
            nonce=card.nonce,
            expires_at=card.expires_at.isoformat(),
        ),
        wid=wid,
    )
    st.pending = None


def goal_plan_slot(t: Turn, slot: str, value: str) -> None:
    st = t.state
    st.pending = None
    if slot == "extras":
        if value == "change_reminders":
            t.ask("goal-plan", "checkin_frequency", "ask_frequency", O.frequency(t.lang), default="monthly")
            return
        if value == "add_transfer":
            st.goal_prefs["recurring_setaside"] = True
        elif value == "no_transfer":
            st.goal_prefs["recurring_setaside"] = False
        elif value == "amounts_on":
            st.goal_prefs["email_amounts"] = True
    elif slot == "checkin_frequency":
        st.goal_prefs["checkin_frequency"] = value
    goal_plan_next(t)


def approval_event(t: Turn, ev: WidgetEvent) -> bool:
    """approve/cancel on an approval card: re-authorised on the server against current state."""
    st = t.state
    card = st.cards.get(ev.widget_id)
    if card is None:
        # never issued, or already used (a replayed approval): nothing happens, and the log says so
        t.mark("approval_refused", reason="unknown_or_used_card", event=ev.event)
        return False
    if card.action == "recurring_setaside":
        return _setaside_event(t, ev, card)
    if ev.event == "cancel":
        st.cards.pop(ev.widget_id, None)
        t.mark("approval_cancelled", action=card.action)
        t.say("cancelled", skill="goal-plan")
        return True
    if ev.event != "approve":
        return False
    from agent.approval import check_approval

    rebuilt = tk.goal_payload(st)
    verdict = check_approval(card, str(ev.data.get("card_hash", "")), rebuilt, set(st.used_nonces))
    violations = tk.check_plan(st, fresh=True) if verdict.ok else []
    if not verdict.ok or violations:
        t.mark(
            "approval_refused",
            action=card.action,
            reason=verdict.reason if not verdict.ok else "rules",
            rules=violations,
        )
        st.cards.pop(ev.widget_id, None)
        t.say("refused", skill="goal-plan")
        for rid in violations[:2]:
            _rule_card(t, rid)
        if not violations:
            _approval(t)
        return True
    st.used_nonces.append(card.nonce)
    st.cards.pop(ev.widget_id, None)
    t.mark("approved", action=card.action, card_hash=card.card_hash)
    if card.action == "create_goal":
        t.call("goal.create", t.services.create_goal, st, card.card_hash, skill=t.skills["goal-plan"])
        t.say("created", skill="goal-plan")
    else:
        t.call(
            "goal.revise", t.services.revise_goal, st, card.card_hash, "owner", skill=t.skills["goal-keeper"]
        )
        t.say("revised", skill="goal-keeper")
    st.revising = False
    st.stale = []
    goto(t, "goal_keeper")
    offer_setaside(t)
    return True


# ------------------------------------------------------------------ the monthly set-aside (embedded mode)


def offer_setaside(t: Turn) -> None:
    """After the goal is approved: if the owner chose the monthly transfer, one more card prepares it
    for WeBank's signing flow. Its lines are built by code; R2's pause and R5's floor hold it back."""
    st = t.state
    sk = t.skills["goal-keeper"]
    offer = t.call("approval.prepare_recurring_setaside", t.services.setaside_offer, st, skill=sk)
    if offer is None:
        return
    if offer["blockers"]:
        _setaside_held(t, offer["blockers"])
        return
    from agent.approval import new_card

    wid = st.next_widget_id()
    card = new_card("recurring_setaside", st.owner_id, offer["terms"], wid)
    st.cards[wid] = card
    t.say("setaside_intro", skill="goal-keeper")
    t.show(
        ApprovalCard(
            action="recurring_setaside",
            title=sk.label("setaside_title", t.lang),
            lines=[ApprovalLine(**ln) for ln in offer["lines"]],
            card_hash=card.card_hash,
            nonce=card.nonce,
            expires_at=card.expires_at.isoformat(),
        ),
        skill=sk,
        wid=wid,
    )


def _setaside_held(t: Turn, rules: list[str]) -> None:
    t.mark("setaside_held", rules=rules)
    held_by = "; ".join(tk.rule(r, t.lang)["title"] for r in rules)
    t.say("setaside_held", skill="goal-keeper", facts={"held_by": held_by})


def _setaside_event(t: Turn, ev: WidgetEvent, card: Any) -> bool:
    """Approve or cancel the set-aside card. Approving records a prepared instruction in (mock) WeBank,
    pending the owner's signature there; nothing moves."""
    st = t.state
    if ev.event == "cancel":
        st.cards.pop(ev.widget_id, None)
        t.mark("approval_cancelled", action=card.action)
        t.say("setaside_cancelled", skill="goal-keeper")
        return True
    if ev.event != "approve":
        return False
    from agent.approval import check_approval

    rebuilt = t.services.setaside_terms(st)
    verdict = check_approval(card, str(ev.data.get("card_hash", "")), rebuilt, set(st.used_nonces))
    blockers = t.services.setaside_blockers(st) if verdict.ok else []
    st.cards.pop(ev.widget_id, None)
    if not verdict.ok or blockers:
        t.mark("approval_refused", action=card.action, reason=verdict.reason if not verdict.ok else "rules",
               rules=blockers)
        if blockers:
            _setaside_held(t, blockers)
        else:
            t.say("setaside_refused", skill="goal-keeper")
            offer_setaside(t)
        return True
    st.used_nonces.append(card.nonce)
    t.mark("approved", action=card.action, card_hash=card.card_hash)
    t.call("webank.prepare_setaside", t.services.prepare_setaside, st, card.card_hash, skill=t.skills["goal-keeper"])  # noqa: E501
    t.say("setaside_prepared", skill="goal-keeper")
    return True


# ------------------------------------------------------------------ links from emails


def open_link(t: Turn, kind: str, value: str) -> None:
    """A link from an email, read once by the web app: the check-in email's "Something changed"
    (`?checkin=<signed token>`) opens the check-in form for that goal and period; the alert email's
    (`?alert=<id>`) opens that alert with its repairs. Anything invalid or expired: a plain notice."""
    st = t.state
    if kind == "checkin" and value in ("recorded", "already"):  # where the one-tap link lands
        t.mark("email_link", link=kind, ok=True, result=value)
        t.notice(f"checkin_{value}")
        return
    if kind == "checkin":
        period = t.services.checkin_link(st, value)
        t.mark("email_link", link=kind, ok=period is not None, period=period)
        if period is None:
            t.notice("link_invalid")
            return
        st.step = "goal_keeper"
        t.services.show_checkin(t, period)
        return
    if kind == "alert":
        ok = bool(st.goal_id) and t.services.alert_view(st, value, t.lang) is not None
        t.mark("email_link", link=kind, ok=ok, alert_id=value[:40])
        if not ok:
            t.notice("link_invalid")
            return
        st.step = "goal_keeper"
        _show_alert(t, value)
        return
    t.mark("email_link", link=kind[:20], ok=False)
    t.notice("link_invalid")


# ------------------------------------------------------------------ goal keeper


def goal_keeper_enter(t: Turn) -> None:
    t.say("hello")
    if t.state.goal_id:
        _show_goal_timeline(t)


def goal_keeper_event(t: Turn, ev: WidgetEvent) -> bool:
    st = t.state
    if ev.event == "checkin":
        outs = t.call("goalkeeper.check", t.services.owner_checkin, st, ev.data)
        _show_check(t, outs)
        return True
    if ev.event in ("see_repairs",):
        alert_id = str(ev.value or st.last_alert_id or "")
        _show_alert(t, alert_id)
        return True
    if ev.event == "select_repair":
        t.call(
            "repairs.find",
            t.services.apply_repair_to_state,
            st,
            str(ev.data.get("alert_id") or st.last_alert_id),
            str(ev.value),
        )
        _show_timeline(t)
        _approval(t)
        return True
    if ev.event == "open_milestone":
        tk.milestone_detail(t, str(ev.value))
        return True
    if ev.event == "mark_milestone_done":
        mark_done(t, str(ev.value), via="tap")
        return True
    return False


def goal_keeper_slot(t: Turn, slot: str, value: str) -> None:
    st = t.state
    st.pending = None
    if slot != "milestone_done":
        return
    mid, st.pending_milestone = st.pending_milestone, None
    if mid is None:
        return
    if value == "yes":
        _record_done(t, mid)
    else:
        t.say("milestone_not_yet", vars={"step": tk.milestone_label(mid, t.lang)})


def mark_done(t: Turn, mid: str, via: str) -> None:
    """The owner says a step is done (a timeline tap, or typed text read by the model). Code checks it
    is one of this goal's steps and that every step before it in legal order is done. A money step,
    or anything typed, is recorded only after the owner confirms (SPEC §7.4)."""
    from tools import timeline as TL

    st = t.state
    if not st.goal_id:
        return
    goal = t.services.gk.goal(st.goal_id)
    ok, reason, missing = TL.can_mark_done(goal.milestones, mid)
    t.mark("milestone_done_request", milestone=mid, via=via, ok=ok, reason=reason)
    if not ok:
        if reason == "unknown":
            t.say("unclear", skill="journey")
            return
        step = tk.milestone_label(mid, t.lang)
        if reason == "already_done":
            t.say("milestone_already_done", vars={"step": step})
        else:
            t.say("milestone_out_of_order", vars={"step": step, "before": tk.milestone_label(missing[0], t.lang)})  # noqa: E501
        _show_goal_timeline(t)
        return
    money = TL.is_money_step(mid)
    if money or via != "tap":
        st.pending_milestone = mid
        t.ask(
            "goal-keeper",
            "milestone_done",
            "confirm_money_done" if money else "confirm_done",
            O.confirm_done(t.lang, money),
            default="no",
            vars={"step": tk.milestone_label(mid, t.lang)},
            allow_text=False,
        )
        return
    _record_done(t, mid)


def _record_done(t: Turn, mid: str) -> None:
    from tools import timeline as TL

    st = t.state
    try:
        goal = t.call("goal.mark_milestone_done", t.services.mark_milestone_done, st, mid, skill=t.skills["goal-keeper"])  # noqa: E501
    except ValueError:  # the goal changed since the question was asked: say where it stands
        _show_goal_timeline(t)
        return
    nxt = TL.next_open(goal.milestones)
    step = tk.milestone_label(mid, t.lang)
    if nxt is None:
        t.say("milestone_done_last", vars={"step": step})
    else:
        t.say("milestone_done", vars={"step": step, "next_step": tk.milestone_label(nxt.id, t.lang)})
    _show_goal_timeline(t)


def _show_goal_timeline(t: Turn) -> None:
    st = t.state
    assert st.goal_id
    goal = t.services.gk.goal(st.goal_id)
    figs, payload = t.call(
        "timeline.build", tk.timeline_for_goal, goal, t.services.gk.elapsed(goal), t.lang, skill=t.skills["goal-keeper"]  # noqa: E501
    )
    t.add(*figs)
    t.show(payload, skill=t.skills["goal-keeper"])


def _show_timeline(t: Turn) -> None:
    figs, payload = t.call(
        "timeline.build", tk.timeline_payload, t.state, t.lang, skill=t.skills["goal-plan"]
    )
    t.add(*figs)
    t.show(payload, skill=t.skills["goal-plan"])


def _show_check(t: Turn, result: dict[str, Any]) -> None:
    figs, status_payload, alert_id = result["figs"], result["status"], result.get("alert_id")
    t.add(*figs)
    t.say(result["line"])
    t.show(status_payload)
    if result.get("r2_pause"):
        t.say("r2_pause")
    if alert_id:
        _show_alert(t, alert_id)


def _show_alert(t: Turn, alert_id: str) -> None:
    st = t.state
    data = t.services.alert_view(st, alert_id, t.lang)
    if data is None:
        return
    t.add(*data["figs"])
    st.last_alert_id = alert_id
    t.say("alert_intro")
    t.show(data["alert"])
    if data["repairs"].repairs:
        t.say("repairs_intro")
        t.show(data["repairs"])
    else:
        t.say("no_repairs")


# ------------------------------------------------------------------ guard


def _rule_card(t: Turn, rule_id: str) -> None:
    st = t.state
    meta = tk.rule(rule_id, t.lang)
    lawful = tk.lawful_options(st, rule_id, t.lang)
    st.guard_hits[rule_id] = st.guard_hits.get(rule_id, 0) + 1
    t.show(
        RuleCard(
            rule_id=rule_id,
            title=meta["title"],
            message=meta["message"],
            consequence=meta["consequence"],
            source=SourceNote(**meta["source"]),
            options=lawful,
        ),
        skill=t.skills["guard"],
    )


def guard(t: Turn, rule_ids: list[str]) -> None:
    st = t.state
    repeat = any(st.guard_hits.get(r, 0) > 0 for r in rule_ids)
    t.say("repeat" if repeat else "lead", skill="guard")
    t.mark("guard", rules=rule_ids, repeat=repeat)
    for rid in rule_ids[:2]:
        _rule_card(t, rid)
    if "R4" in rule_ids:
        st_topic = "T-ODI"
        if st_topic not in st.raised_topics:
            st.raised_topics.append(st_topic)
            show_topic(t, st_topic)


def _funding_reachable(t: Turn) -> bool:
    """The funding step is current, or was reached (so the reopen flow can go back to it)."""
    st = t.state
    return st.funding is not None and (st.step == "funding" or "funding" in st.done or "funding" in st.stale)


def _apply_lever(t: Turn, value: str) -> None:
    """A plan-changing alternative, at the funding step. A share change runs the full simulation; the rest ask
    the owner for the amount, as the levers do."""
    st = t.state
    assert st.funding is not None
    if value in ("raise_share", "lower_share"):
        step = Decimal("0.10") if value == "raise_share" else Decimal("-0.05")
        wall = t.call("plan.wall", tk.wall, st, skill=t.skills["funding"])
        _commit_share(t, max(Decimal(0), min(st.funding.setaside_share + step, wall)))
    elif value == "add_savings":
        t.ask("funding", "savings", "ask_savings", O.savings(t.lang), default="none")
    elif value == "rent_free":
        t.ask("funding", "rent_free", "ask_rent_free", O.rent_free(t.lang), default="1")
    elif value == "partner":
        st.raised_topics = [x for x in st.raised_topics if x != "T-PARTNER"]
        maybe_topic(t, "T-PARTNER")
        t.ask("funding", "partner", "levers_ask", O.partner(t.lang), default="skip")
    elif value == "staged_contractor":
        tk.toggle_option(st.funding, "staged_contractor", True)
        _simulate_and_show(t)


def _show_funding_cards(t: Turn) -> None:
    """The funding screen's cards again (WeBank at home, after opening), then the levers question."""
    st = t.state
    opts, figs = t.call("funding.options", tk.funding_options, st, t.lang, skill=t.skills["funding"])
    t.add(*figs)
    t.show(opts, skill=t.skills["funding"])
    _bank_cards_beat(t, opts)
    t.ask("funding", "lever", "levers_ask", O.levers(t.lang), default="looks_good")


def guard_option(t: Turn, value: str) -> None:
    """A lawful option picked from a rule card, at any step (rules/rules.yaml `alternatives`).

    A lever or a cards view acts at the funding step; from a later step it reopens funding (the reopen flow
    marks later steps stale and re-confirms) and applies there; before funding is reached it says it comes at
    that step. A topic shows anywhere. Anything else is ignored."""
    st = t.state
    a = tk.alternative(value)
    if a is None:
        t.mark("ignored_event", reason="unknown_option", option=value)
        t.reask()
        return
    t.mark("guard_option", option=value, action=a["action"])
    if a["action"] == "topic":
        show_topic(t, str(a["topic"]))
        t.reask()
        return
    if not _funding_reachable(t):
        t.say("alternative_later", skill="funding", facts={"option": a[f"label_{t.lang}"]})
        t.reask()
        return
    if st.step != "funding":
        if value in ("raise_share", "lower_share"):
            # pre-apply the share change; funding_enter clamps it to the wall and simulates it
            assert st.funding is not None
            step = Decimal("0.10") if value == "raise_share" else Decimal("-0.05")
            st.funding.setaside_share = max(Decimal(0), st.funding.setaside_share + step)
        elif value == "staged_contractor":
            assert st.funding is not None
            tk.toggle_option(st.funding, "staged_contractor", True)
        reopen(t, "funding")  # reachable (checked above), so this re-enters funding with the change applied
        if a["action"] == "lever" and value not in ("raise_share", "lower_share", "staged_contractor"):
            _apply_lever(t, value)
        return
    if a["action"] == "cards":
        _show_funding_cards(t)
        return
    _apply_lever(t, value)


# ------------------------------------------------------------------ dispatch tables

ENTER = {
    "welcome": welcome_enter,
    "profile": profile_enter,
    "site": site_enter,
    "cost": cost_enter,
    "funding": funding_enter,
    "goal_plan": goal_plan_enter,
    "goal_keeper": goal_keeper_enter,
}
SLOT = {
    "welcome": welcome_slot,
    "profile": profile_slot,
    "site-finder": site_slot,
    "cost": cost_slot,
    "funding": funding_slot,
    "goal-plan": goal_plan_slot,
    "goal-keeper": goal_keeper_slot,
}
EVENT = {
    "welcome": welcome_event,
    "profile": profile_event,
    "site": site_event,
    "cost": cost_event,
    "funding": funding_event,
    "goal_plan": lambda t, ev: False,
    "goal_keeper": goal_keeper_event,
}
