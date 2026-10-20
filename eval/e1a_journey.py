# ruff: noqa: E501
"""E1a: scripted simulated owners reach a confirmed goal (results/prereg.md, SPEC §3, §11).

Pre-registered: rule-based persona drivers (no model) run the full chat through the orchestrator. The
personas vary host mode (embedded/standalone), language (EN/ZH), how they answer (taps vs typed free text,
including ranges in Chinese), detours (side questions), one guard trigger each, and going back once.
60 personas (fixed list, seed 20261019). Pass marks: >= 90% reach a confirmed goal; median <= 25 owner
turns; drop-off by step reported.

The fixed persona list (built by `personas()` from seed 20261019):
- 2 host modes x 2 languages x 3 answer styles (taps / typed / mixed) x 5 = 60.
- Typed answers are what an owner would type for each question, in their language (e.g. "我有12家店",
  "每月大概20-25万", "about 200-250k a month", "标准的就行"). If a typed answer is not understood (the same
  question comes back), the persona taps an option instead. Cards with buttons (consent, confirm,
  approval, accepting quote lines) are always tapped.
- Detours: 0, 1 or 2 side questions (seeded), each at a seeded step, from the topic library's subjects.
- One guard trigger each, at a seeded step: a request the guard should block (e.g. using the WeBank loan
  for the deposit). The persona then carries on.
- Going back once: at a seeded step after the profile, the persona goes back one step (typed "go back" or
  a tap on the progress strip, seeded), then carries on (re-confirming that step).
- Standalone owners type in their own numbers; their bands are drawn from the in-scope profitable-SME
  range (monthly profit RMB 100k-500k, spare cash RMB 200k-2m), comparable to the embedded persona's
  feed. Other choices (customers, budget, opening window, priority, unit, fit-out, manager, quotes,
  check-in frequency, email amounts, recurring set-aside) are seeded per persona.
- If the funding review refuses the plan, the persona tries the levers in order: add savings, rent-free
  months, a local partner; it picks a lawful option on a rule card when no question is pending.
- A persona stops after 80 owner turns, or when it has nothing it can do (stuck); either is a drop-off at
  the step where it stopped. An owner turn is one message or one tap.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from eval import common as C
from eval import drive as DR

STEPS = ("welcome", "profile", "site", "cost", "funding", "goal_plan", "goal_keeper")
MAX_TURNS = 80

GUARD_TEXT = {
    "en": [
        "Can I just use my WeBank loan to pay the Singapore deposit?",
        "My Shenzhen company can guarantee the Singapore lease.",
        "Let's route the money through Hong Kong instead.",
        "I'll take a personal loan and put it in as my savings.",
        "Let's sign the lease now before someone else takes the unit.",
    ],
    "zh": [
        "能不能先用微业贷付新加坡的押金？",
        "让深圳公司给新加坡的租约做担保。",
        "钱先走香港转一下吧。",
        "我申请个人贷款，当作自己的积蓄投进去。",
        "先签租约吧，免得铺位被别人抢走。",
    ],
}
DETOUR_TEXT = {
    "en": [
        "Do I need a resident director?",
        "Is GST charged on the fit-out?",
        "Is station traffic the same as mall footfall?",
        "What is the ODI filing?",
        "Why can't I sign the lease yet?",
        "What happens to the unit at the end of the lease?",
        "What is the safety line?",
    ],
    "zh": [
        "我需要本地董事吗？",
        "装修要交消费税吗？",
        "地铁站人流就是商场客流吗？",
        "ODI备案是什么？",
        "为什么现在还不能签约？",
        "租约到期铺位要复原吗？",
        "安全线是什么意思？",
    ],
}
BACK_TEXT = {
    "en": ["Can we go back to the previous step?", "Go back please"],
    "zh": ["我想返回上一步", "回到上一步"],
}
PREV = {"site": "profile", "cost": "site", "funding": "cost", "goal_plan": "funding"}


@dataclass
class Persona:
    pid: str
    host_mode: str
    lang: str
    style: str  # tap | typed | mixed
    detours: list[str]
    guard_step: str
    guard_text: str
    back_from: str
    back_mode: str  # typed | tap
    prefs: dict[str, str] = field(default_factory=dict)
    numbers: dict[str, Any] = field(default_factory=dict)
    seed: int = 0


def personas(seed: int = C.SEED, n: int = 60) -> list[Persona]:
    rng = np.random.default_rng(seed)
    out: list[Persona] = []
    cells = [
        (h, lg, s)
        for h in ("embedded", "standalone")
        for lg in ("en", "zh")
        for s in ("tap", "typed", "mixed")
    ]
    journey = ["profile", "site", "cost", "funding", "goal_plan"]
    i = 0
    while len(out) < n:
        h, lg, s = cells[i % len(cells)]
        nd = int(rng.integers(0, 3))
        detours = [journey[int(rng.integers(0, 5))] for _ in range(nd)]
        prefs = {
            "customers": ["young_adults", "students", "office_workers", "families", "tourists"][
                int(rng.integers(0, 5))
            ],
            "budget": ["b1", "b2", "b3", "not_sure"][int(rng.integers(0, 4))],
            "window": ["6_12", "12_18", "18_24", "no_rush"][int(rng.integers(0, 4))],
            "priority": ["near_customers", "foot_traffic", "low_rent"][int(rng.integers(0, 3))],
            "fitout": ["basic", "standard", "premium"][int(rng.integers(0, 3))],
            "manager": ["hire_local", "send_own"][int(rng.integers(0, 2))],
            "quotes": ["demo_quote", "no_quotes"][int(rng.integers(0, 2))],
            "checkin_frequency": ["monthly", "fortnightly", "weekly"][int(rng.integers(0, 3))],
            "email_amounts": ["no", "yes"][int(rng.integers(0, 2))],
            "recurring_setaside": ["no", "yes"][int(rng.integers(0, 2))],
            "lever": "looks_good",
            "area_rank": str(int(rng.integers(0, 3))),
            "unit_rank": str(int(rng.integers(0, 3))),
        }
        numbers = {
            "shops": int(rng.integers(3, 30)),
            "profit_k": int(rng.integers(100, 500)),
            "spare_k": int(rng.integers(200, 2000)),
            "budget_k": int(rng.integers(250, 600)),
            "fmt": int(rng.integers(0, 3)),
        }
        prefs["monthly_profit"] = (
            "p2" if numbers["profit_k"] < 200 else "p3" if numbers["profit_k"] < 300 else "p4"
        )
        prefs["spare_cash"] = (
            "s2" if numbers["spare_k"] < 500 else "s3" if numbers["spare_k"] < 1000 else "s4"
        )
        prefs["shops"] = "3" if numbers["shops"] < 6 else "10" if numbers["shops"] <= 15 else "20"
        out.append(
            Persona(
                pid=f"P{len(out) + 1:02d}",
                host_mode=h,
                lang=lg,
                style=s,
                detours=detours,
                guard_step=journey[int(rng.integers(0, 5))],
                guard_text=GUARD_TEXT[lg][int(rng.integers(0, 5))],
                back_from=["site", "cost", "funding", "goal_plan"][int(rng.integers(0, 4))],
                back_mode=["typed", "tap"][int(rng.integers(0, 2))],
                prefs=prefs,
                numbers=numbers,
                seed=int(rng.integers(0, 2**31 - 1)),
            )
        )
        i += 1
    return out


# ------------------------------------------------------------------ typed answers


def typed_answer(
    p: Persona,
    slot: str,
    options: list[dict[str, Any]],
    rng: np.random.Generator,
    avoid: list[str] | None = None,
) -> str | None:
    zh = p.lang == "zh"
    nb = p.numbers
    f = nb["fmt"]
    lo = nb["profit_k"]
    hi = lo + 50
    if slot == "lang":
        return "中文" if zh else "English please"
    if slot == "start":
        return "好的，开始吧" if zh else "ok, let's start"
    if slot == "shops":
        return (
            [f"我有{nb['shops']}家店", f"{nb['shops']}家", f"一共{nb['shops']}家门店"][f]
            if zh
            else [f"We have {nb['shops']} shops", f"{nb['shops']} shops", f"about {nb['shops']}"][f]
        )
    if slot == "monthly_profit":
        if zh:
            return [
                f"每月大概{lo // 10}-{hi // 10}万",
                f"一个月{lo // 10}万左右",
                f"利润每月{lo // 10}到{hi // 10}万",
            ][f]
        return [f"about {lo}-{hi}k a month", f"RMB {lo}k", f"{lo},000 to {hi},000"][f]
    if slot == "spare_cash":
        s = nb["spare_k"]
        return (
            [f"大概{s // 10}万", f"闲钱有{s // 10}万左右", f"{s // 10}万"][f]
            if zh
            else [f"around RMB {s}k", f"{s}k spare", f"about {s},000"][f]
        )
    if slot == "customers":
        m = {
            "young_adults": ("主要是年轻人", "mostly young people"),
            "students": ("学生为主", "students mainly"),
            "office_workers": ("上班族", "office workers"),
            "families": ("家庭客人", "families with kids"),
            "tourists": ("游客", "tourists"),
        }[p.prefs["customers"]]
        return m[0] if zh else m[1]
    if slot == "budget":
        if p.prefs["budget"] == "not_sure":
            return "还不确定" if zh else "not sure yet"
        b = nb["budget_k"]
        return f"{b // 10}万新元左右" if zh else f"around S${b}k"
    if slot == "window":
        m = {
            "6_12": ("一年内", "within a year"),
            "12_18": ("一年到一年半", "in a year to eighteen months"),
            "18_24": ("大约两年", "in about two years"),
            "no_rush": ("不着急", "no rush"),
        }[p.prefs["window"]]
        return m[0] if zh else m[1]
    if slot == "priority":
        m = {
            "near_customers": ("靠近顾客", "being near my customers"),
            "foot_traffic": ("人流量大", "lots of foot traffic"),
            "low_rent": ("租金低", "low rent matters most"),
        }[p.prefs["priority"]]
        return m[0] if zh else m[1]
    if slot in ("area", "unit"):
        opts = [o for o in options if str(o["value"]) not in (avoid or [])] or options
        k = min(int(p.prefs[f"{slot}_rank"]), len(opts) - 1)
        label = str(opts[k]["label"])
        if slot == "unit":
            label = label.split(" #")[0]  # owners type the mall, not the unit number
        return f"{label}吧" if zh else f"{label} please"
    if slot == "fitout":
        m = {
            "basic": ("简单一点", "basic is fine"),
            "standard": ("标准的就行", "standard like my shops"),
            "premium": ("高端一点", "premium, a flagship look"),
        }[p.prefs["fitout"]]
        return m[0] if zh else m[1]
    if slot == "manager":
        m = {
            "hire_local": ("在本地招一个", "I'll hire locally"),
            "send_own": ("派我自己的店长", "send my own manager"),
        }[p.prefs["manager"]]
        return m[0] if zh else m[1]
    if slot == "quotes":
        m = {
            "demo_quote": ("用示例报价", "use the sample quote"),
            "no_quotes": ("暂时没有", "no quotes yet"),
        }[p.prefs["quotes"]]
        return m[0] if zh else m[1]
    if slot == "lever":
        return "可以" if zh else "looks good"
    if slot == "savings":
        return "加四十万积蓄" if zh else "add 400k of my savings"
    if slot == "rent_free":
        return "两个月" if zh else "two months"
    if slot == "partner":
        return "看看有合伙人的方案" if zh else "show it with a partner"
    if slot == "checkin_frequency":
        m = {
            "monthly": ("每月", "monthly please"),
            "fortnightly": ("两周一次", "every fortnight"),
            "weekly": ("每周", "every week"),
        }[p.prefs["checkin_frequency"]]
        return m[0] if zh else m[1]
    if slot in ("email_amounts", "recurring_setaside"):
        yes = p.prefs[slot] == "yes"
        return ("要" if yes else "不要") if zh else ("yes" if yes else "no thanks")
    return None


# ------------------------------------------------------------------ the persona loop


@dataclass
class Ctx:
    guard_done: bool = False
    back_done: bool = False
    detours_left: list[str] = field(default_factory=list)
    lever_plan: list[str] = field(
        default_factory=lambda: [
            "looks_good",
            "add_savings",
            "looks_good",
            "rent_free",
            "looks_good",
            "partner",
            "looks_good",
        ]
    )
    last_typed: tuple[str, str] | None = None  # (slot, widget id) of the last typed answer
    tried_areas: list[str] = field(default_factory=list)  # areas picked that had no units
    log: list[str] = field(default_factory=list)


def _rule_cards_last(d: C.Driver) -> list[Any]:
    return d.widgets("rule_card")


def step_once(d: C.Driver, p: Persona, ctx: Ctx, rng: np.random.Generator) -> bool:
    """One owner action. False if the persona has nothing it can do."""
    st = d.state
    step = st.step
    # scheduled detours, guard trigger and going back happen when a question is pending in that step
    if st.pending is not None and step in ctx.detours_left:
        ctx.detours_left.remove(step)
        d.run(text=DETOUR_TEXT[p.lang][int(rng.integers(0, len(DETOUR_TEXT[p.lang])))])
        ctx.log.append(f"detour@{step}:topic_card={bool(d.widgets('topic_card'))}")
        return True
    if not ctx.guard_done and step == p.guard_step and st.pending is not None:
        ctx.guard_done = True
        d.run(text=p.guard_text)
        ctx.log.append(f"guard@{step}:rule_card={bool(d.widgets('rule_card'))}")
        return True
    if not ctx.back_done and step == p.back_from and (st.pending is not None or step == "goal_plan"):
        ctx.back_done = True
        if p.back_mode == "typed":
            d.run(text=BACK_TEXT[p.lang][int(rng.integers(0, 2))])
        else:
            d.run(event=DR._ev("", "reopen_step", PREV[step]))
        ctx.log.append(f"back@{step}->{d.state.step}")
        return True
    if step == "goal_plan" and st.cards:  # the approval card carries the defaults: the owner approves it
        return DR.tap_once(d, p.prefs, p.lang)
    if step == "cost" and any(ln.status in ("pending", "check") for q in st.quotes for ln in q.lines):
        return DR.tap_once(d, p.prefs, p.lang)  # "Accept all"
    if st.pending is not None:
        pend = st.pending
        slot = pend.slot
        typed = p.style == "typed" or (p.style == "mixed" and rng.random() < 0.5)
        if slot == "lever":
            value = ctx.lever_plan.pop(0) if ctx.lever_plan else "looks_good"
            if typed and value == "looks_good":
                d.run(text=typed_answer(p, slot, pend.options, rng))
            else:
                values = [str(o["value"]) for o in pend.options]
                d.reply(value if value in values else values[0])
            return True
        if slot == "savings":
            values = [str(o["value"]) for o in pend.options]
            d.reply("v6" if "v6" in values else values[-1])
            return True
        if slot == "rent_free":
            values = [str(o["value"]) for o in pend.options]
            d.reply("3" if "3" in values else values[-1])
            return True
        if slot == "partner":
            d.reply(
                "include"
                if "include" in [str(o["value"]) for o in pend.options]
                else pend.options[0]["value"]
            )
            return True
        retry = ctx.last_typed == (slot, pend.widget_id)
        if typed and not retry:
            txt = typed_answer(p, slot, pend.options, rng, ctx.tried_areas if slot == "area" else None)
            if txt:
                ctx.last_typed = (slot, pend.widget_id or "")
                area_before = d.state.selected_area
                d.run(text=txt)
                if (
                    slot == "area"
                    and d.state.selected_area != area_before
                    and d.state.pending is not None
                    and d.state.pending.slot == "area"
                    and d.state.selected_area
                ):
                    ctx.tried_areas.append(d.state.selected_area)  # typed area came back with no units
                    ctx.last_typed = None
                if d.state.pending is not None and d.state.pending.slot == slot:
                    # not understood: next time tap (the widget id changes on a re-ask, so key on slot)
                    ctx.last_typed = (slot, d.state.pending.widget_id or "")
                return True
        ctx.last_typed = None
        if slot in ("area", "unit"):
            values = [str(o["value"]) for o in pend.options]
            if slot == "area":
                # an area already picked that came back with no units: the owner tries another one
                values = [v for v in values if v not in ctx.tried_areas] or values
            k = min(int(p.prefs[f"{slot}_rank"]), len(values) - 1)
            d.reply(values[k])
            if slot == "area" and d.state.pending is not None and d.state.pending.slot == "area":
                ctx.tried_areas.append(values[k])  # it came back with no units
            return True
        if slot == "lang":
            d.reply(p.lang)
            return True
        d.reply(DR.pick(pend.options, p.prefs, slot))
        return True
    # no pending question: a card is waiting
    if step == "funding":
        cards = _rule_cards_last(d)
        if cards and cards[-1].payload.options:
            opts = [o.value for o in cards[-1].payload.options]
            d.run(
                event=DR._ev(
                    cards[-1].id, "select_option", "add_savings" if "add_savings" in opts else opts[0]
                )
            )
            return True
    if step == "cost" and st.quotes:
        for q in st.quotes:
            for ln in q.lines:
                if ln.status in ("pending", "check"):
                    d.event("upload_prompt", "accept_line", ln.id)
                    return True
    return DR.tap_once(d, p.prefs, p.lang)


def run_persona(svc: Any, p: Persona) -> dict[str, Any]:
    rng = np.random.default_rng(p.seed)
    d = C.Driver(svc, p.host_mode, tag=p.pid.lower())
    ctx = Ctx(detours_left=list(p.detours))
    d.state.lang = p.lang  # the interface language the owner picked; the chat greets in it
    d.run(init=True)
    reached = {d.state.step}
    stuck = False
    delivered: list[str] = []
    seen_sigs: dict[tuple[Any, ...], int] = {}
    while d.state.goal_id is None and d.owner_turns < MAX_TURNS:
        ok = step_once(d, p, ctx, rng)
        delivered += [t for t in d.texts() if t]
        reached.add(d.state.step)
        if not ok:
            stuck = True
            break
        sig = (
            d.state.step,
            d.state.pending.slot if d.state.pending else None,
            d.state.widget_seq,
            str([(ln.id, ln.status) for q in d.state.quotes for ln in q.lines]),
            str(d.state.cost_asked),
        )
        seen_sigs[sig] = seen_sigs.get(sig, 0) + 1
        if seen_sigs[sig] >= 4:  # nothing changes however it acts
            stuck = True
            break
    done = d.state.goal_id is not None
    return {
        "persona": asdict(p),
        "completed": done,
        "owner_turns": d.owner_turns,
        "end_step": d.state.step,
        "reached": sorted(reached, key=STEPS.index),
        "stuck": stuck,
        "hit_turn_cap": (not done) and d.owner_turns >= MAX_TURNS,
        "errors": d.errors,
        "log": ctx.log,
        "delivered": delivered,
        "transcript": d.transcript,
    }


def run(
    n: int = 60, seed: int = C.SEED, workdir: Any = None, recorder: Any = None, only: set[str] | None = None
) -> dict[str, Any]:
    """Run the personas (or `only` those ids, for a shard). Returns the payload E2 audits (transcripts and
    the render recorder)."""
    work = workdir or C.setup_env()
    svc = C.make_services(work, "e1a")
    voice = DR.install_test_voice()
    plist = [p for p in personas(seed, n) if only is None or p.pid in only]
    rows = []
    if recorder is not None:
        recorder.install()
    try:
        for p in plist:
            if recorder is not None:
                with recorder.persona(p.pid):
                    rows.append(run_persona(svc, p))
            else:
                rows.append(run_persona(svc, p))
    finally:
        if recorder is not None:
            recorder.uninstall()
    return {
        "n": len(rows),
        "rows": rows,
        "voice": voice,
        "recorder": recorder,
        "delivered": {r["persona"]["pid"]: r["delivered"] for r in rows},
    }


def evaluate(payload: dict[str, Any], seed: int = C.SEED, runtime_s: float | None = None) -> dict[str, Any]:
    rows = payload["rows"]
    n = len(rows)
    comp = sum(1 for r in rows if r["completed"])
    comp_w = C.wilson(comp, n)
    turns_done = [r["owner_turns"] for r in rows if r["completed"]]
    turns_all = [r["owner_turns"] if r["completed"] else float(MAX_TURNS) for r in rows]
    med = C.bootstrap_ci(turns_all)
    dropoff = {s: sum(1 for r in rows if not r["completed"] and r["end_step"] == s) for s in STEPS[:-1]}
    reached = {s: sum(1 for r in rows if s in r["reached"]) for s in STEPS}

    def grp(key: str, val: str) -> dict[str, Any]:
        rs = [r for r in rows if r["persona"][key] == val]
        return {
            "completed": C.wilson(sum(1 for r in rs if r["completed"]), len(rs)),
            "median_turns_completers": float(np.median([r["owner_turns"] for r in rs if r["completed"]]))
            if any(r["completed"] for r in rs)
            else None,
        }

    guard_ok = sum(1 for r in rows if any(x.startswith("guard@") and x.endswith("True") for x in r["log"]))
    guard_n = sum(1 for r in rows if any(x.startswith("guard@") for x in r["log"]))
    det_ok = sum(1 for r in rows for x in r["log"] if x.startswith("detour@") and x.endswith("True"))
    det_n = sum(1 for r in rows for x in r["log"] if x.startswith("detour@"))
    back_ok = sum(
        1
        for r in rows
        for x in r["log"]
        if x.startswith("back@") and x.split("->")[0][5:] != x.split("->")[1]
    )
    back_n = sum(1 for r in rows for x in r["log"] if x.startswith("back@"))
    err_rows = [r for r in rows if r["errors"]]
    scripted = {t for lg in ("en", "zh") for t in [*GUARD_TEXT[lg], *DETOUR_TEXT[lg], *BACK_TEXT[lg]]}

    def kinds(r: dict[str, Any]) -> dict[str, int]:
        k = {"detour_guard_back": 0, "accept_quote_line": 0, "typed_not_understood": 0}
        own = [x for x in r["transcript"] if x["who"] == "owner" and (x["text"] or x["event"])]
        for x in own:
            ev = x["event"] or {}
            if x["text"] in scripted or ev.get("event") == "reopen_step":
                k["detour_guard_back"] += 1
            elif ev.get("event") == "accept_line":
                k["accept_quote_line"] += 1
        # typed answers followed by a tap on the same question
        tr = r["transcript"]
        for i, x in enumerate(tr):
            if x["who"] == "owner" and x["text"] and x["text"] not in scripted:
                nxt = [y for y in tr[i + 1 :] if y["who"] == "bot" and y.get("text")]
                if nxt and nxt[0]["text"].startswith("unclear"):
                    k["typed_not_understood"] += 1
        return k

    kk = [kinds(r) for r in rows]
    core_turns = [
        r["owner_turns"] - k["detour_guard_back"] for r, k in zip(rows, kk, strict=True) if r["completed"]
    ]
    metrics_turns = {
        "median_turns_on_detours_guard_and_going_back": float(
            np.median([k["detour_guard_back"] for k in kk])
        ),
        "median_quote_line_taps": float(np.median([k["accept_quote_line"] for k in kk])),
        "typed_answers_not_understood_total": sum(k["typed_not_understood"] for k in kk),
        "median_turns_completers_excluding_detours_guard_back_turns": float(np.median(core_turns))
        if core_turns
        else None,
    }
    metrics = {
        "turn_breakdown": metrics_turns,
        "personas": n,
        "completed": comp_w,
        "median_owner_turns_all": med,
        "median_owner_turns_completers": float(np.median(turns_done)) if turns_done else None,
        "owner_turns_quartiles_completers": [float(np.percentile(turns_done, q)) for q in (25, 50, 75)]
        if turns_done
        else None,
        "dropoff_by_step": dropoff,
        "reached_by_step": reached,
        "stuck": sum(1 for r in rows if r["stuck"] and not r["completed"]),
        "hit_turn_cap": sum(1 for r in rows if r["hit_turn_cap"]),
        "by_host_mode": {h: grp("host_mode", h) for h in ("embedded", "standalone")},
        "by_language": {lg: grp("lang", lg) for lg in ("en", "zh")},
        "by_style": {s: grp("style", s) for s in ("tap", "typed", "mixed")},
        "guard_trigger_blocked": C.wilson(guard_ok, guard_n),
        "detour_topic_shown": C.wilson(det_ok, det_n),
        "going_back_moved_back": C.wilson(back_ok, back_n),
        "personas_with_unhandled_exceptions": len(err_rows),
        "exception_examples": sorted({e for r in err_rows for e in r["errors"]})[:8],
        "not_completed": [
            {
                "pid": r["persona"]["pid"],
                "end_step": r["end_step"],
                "turns": r["owner_turns"],
                "stuck": r["stuck"],
                "errors": r["errors"][:2],
                "log": r["log"],
            }
            for r in rows
            if not r["completed"]
        ][:20],
        "voice": payload.get("voice"),
    }
    med_v = med["value"]
    notes = [
        f"60 rule-based personas (fixed list from seed {seed}); real orchestrator; text voice: {payload.get('voice')}. "
        "Typed answers are parsed by code only (no model).",
        f"Reached a confirmed goal: {C.wfmt(comp_w)}. Median owner turns {med_v} (bootstrap 95% CI {med['lo']}–{med['hi']}; "
        f"non-completers counted at the {MAX_TURNS}-turn cap); completers only: median {metrics['median_owner_turns_completers']}, "
        f"quartiles {metrics['owner_turns_quartiles_completers']}.",
        f"Where the turns go (descriptive): median {metrics_turns['median_turns_on_detours_guard_and_going_back']} turns on the "
        f"scheduled side questions, guard trigger and going-back message itself (not counting the re-confirmations going back "
        f"causes); median {metrics_turns['median_quote_line_taps']} taps accepting quote lines one by one; "
        f"{metrics_turns['typed_answers_not_understood_total']} typed answers in all were not understood. Completers' median "
        f"without the detour/guard/back messages: {metrics_turns['median_turns_completers_excluding_detours_guard_back_turns']}.",
        "Drop-off by step (where non-completers stopped): "
        + ", ".join(f"{k} {v}" for k, v in dropoff.items())
        + ".",
        "Reached each step: " + ", ".join(f"{k} {v}" for k, v in reached.items()) + ".",
        "By host mode: "
        + "; ".join(
            f"{k} {C.wfmt(v['completed'])} (median turns {v['median_turns_completers']})"
            for k, v in metrics["by_host_mode"].items()
        )
        + ".",
        "By language: "
        + "; ".join(
            f"{k} {C.wfmt(v['completed'])} (median turns {v['median_turns_completers']})"
            for k, v in metrics["by_language"].items()
        )
        + ".",
        "By answer style: "
        + "; ".join(
            f"{k} {C.wfmt(v['completed'])} (median turns {v['median_turns_completers']})"
            for k, v in metrics["by_style"].items()
        )
        + ".",
        f"Guard trigger shown a rule card: {C.wfmt(metrics['guard_trigger_blocked'])}; side questions answered with a topic card: "
        f"{C.wfmt(metrics['detour_topic_shown'])}; going back moved the journey back: {C.wfmt(metrics['going_back_moved_back'])}.",
    ]
    if err_rows:
        notes.append(
            f"Personas that hit an unhandled exception (turn discarded, persona carried on): {len(err_rows)}; "
            f"e.g. {metrics['exception_examples'][:3]}."
        )
    if metrics["not_completed"]:
        notes.append(
            "Non-completers: "
            + "; ".join(
                f"{x['pid']} stopped at {x['end_step']} after {x['turns']} turns"
                + (" (stuck)" if x["stuck"] else "")
                for x in metrics["not_completed"][:10]
            )
            + "."
        )
    return C.entry(
        "run",
        n=n,
        title="Scripted simulated owners reach a confirmed goal",
        metrics=metrics,
        pass_marks={
            "reached a confirmed goal": C.mark(">= 90%", C.pct(comp_w["p"]), (comp_w["p"] or 0) >= 0.90),
            "median owner turns": C.mark("<= 25", med_v, med_v is not None and med_v <= 25),
        },
        seed=seed,
        notes=notes,
        runtime_s=runtime_s,
    )
