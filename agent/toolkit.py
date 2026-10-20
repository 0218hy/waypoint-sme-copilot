"""Adapter between step handlers and the computation tools (tools/, rules/, mock_webank/).

Every function here is code: it calls tools, turns results into Figures and widget payloads, and
never invents a number. `TOOL_NAMES` lists the tool ids Skills may put on their allowlists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from agent import options as O
from agent.render import Lang, money, month_label
from agent.widgets import (
    ApprovalLine,
    Benchmark,
    BusinessGlance,
    ChartSeries,
    ClosedOptions,
    ClosedRoute,
    CompareColumn,
    CompareTerms,
    CompareToggle,
    CostBreakdown,
    CostGroupRow,
    CostLineRow,
    CoverageRow,
    EconLine,
    ExtractedRow,
    Factor,
    FundingCard,
    FundingCompare,
    FundingOptions,
    MilestoneTimeline,
    Option,
    PnlRow,
    ProfileField,
    RankWhy,
    RatioRow,
    SourceNote,
    TimelineItem,
    UnitEconomics,
    UnitRow,
    UploadPrompt,
)
from tools import compare as CMP
from tools import costs as C
from tools import data as D
from tools import funding as F
from tools import params as P
from tools import plan as PL
from tools import ratios as R
from tools import unit_econ as UE
from tools.figtools import derived
from tools.figures import Figure
from tools.models import (
    Area,
    AreaScore,
    CostCard,
    ExtractedQuote,
    FeedSnapshot,
    FundingPlan,
    PlanResult,
    Priority,
    Profile,
    Shortlist,
    Unit,
)

if TYPE_CHECKING:
    from agent.state import JourneyState
    from agent.turn import Turn

ROOT = Path(__file__).resolve().parents[1]

TOOL_NAMES: tuple[str, ...] = (
    "feed.read",
    "profile.from_feed",
    "profile.floor",
    "ratios.chain",
    "unit_econ.card",
    "sites.rank_areas",
    "sites.area_profile",
    "sites.list_units",
    "sites.compare_units",
    "sites.break_even",
    "costs.estimate",
    "costs.missing_items",
    "reader.read_document",
    "funding.floor",
    "funding.gap",
    "funding.options",
    "funding.closed",
    "funding.mix",
    "plan.simulate",
    "plan.wall",
    "plan.lawful_options",
    "rules.check_plan",
    "rules.check_intent",
    "timeline.build",
    "goal.summary",
    "goal.create",
    "goal.revise",
    "approval.prepare_create_goal",
    "approval.prepare_revise_goal",
    "email.send",
    "goalkeeper.check",
    "repairs.find",
    "topics.lookup",
    "drafts.consent_request",
    "drafts.checklist",
    "goal.mark_milestone_done",
    "approval.prepare_recurring_setaside",
    "webank.prepare_setaside",
)


# ------------------------------------------------------------------ topics, rules, figures from params


@cache
def _topics() -> dict[str, Any]:
    return dict(yaml.safe_load((ROOT / "data" / "topics.yaml").read_text(encoding="utf-8"))["topics"])


def topic(topic_id: str, lang: Lang) -> dict[str, Any]:
    tp = _topics()[topic_id]
    return {
        "title": tp["title"][lang],
        "say": tp["say"][lang],
        "more": tp["more"][lang],
        "source": {
            "label": tp["source"]["label"],
            "url": tp["source"].get("url"),
            "as_of": tp["source"].get("as_of"),
        },
    }


PARAM_UNITS: dict[str, str] = {
    "ep_min_salary_sgd": "SGD",
    "cpf_employer_rate": "pct",
    "gst_rate": "pct",
    "pre_investment_cap_share": "pct",
    "floor_risk_limit": "pct",
    "deposit_months": "months",
    "fx_cny_per_sgd": "count",
}


def resolve_fig(fig_id: str) -> Figure | None:
    """`param:<key>` figures come straight from data/params.yaml with its source and date."""
    if not fig_id.startswith("param:"):
        return None
    key = fig_id.split(":", 1)[1]
    unit = PARAM_UNITS.get(key)
    if unit is None:
        return None
    try:
        return P.param_fig(key, key.replace("_", " "), unit, fig_id=fig_id)  # type: ignore[arg-type]
    except KeyError:
        return None


@cache
def _rules() -> dict[str, Any]:
    return dict(D.load_rules_yaml())


def rule(rule_id: str, lang: Lang) -> dict[str, Any]:
    r = _rules()["rules"][rule_id]
    return {
        "title": r[f"title_{lang}"],
        "message": r[f"message_{lang}"],
        "consequence": r[f"consequence_{lang}"],
        "source": {"label": r["source"], "url": r.get("url"), "kind": r.get("kind")},
    }


# ------------------------------------------------------------------ consent text


def consent_reads(lang: Lang) -> list[str]:
    if lang == "zh":
        return ["近期经营收入与利润", "现金余额", "工资与还款", "微业贷用款情况"]
    return [
        "Recent sales and profit",
        "Cash balance",
        "Payroll and loan repayments",
        "How much of your WeBank business loan is drawn",
    ]


def consent_never(lang: Lang) -> list[str]:
    if lang == "zh":
        return ["你的对话和各种假设不会用于授信决策", "不会移动任何资金", "演示中的账户数据为模拟数据"]
    return [
        "Your chats and what-ifs are never used for credit decisions",
        "Nothing moves money",
        "In this demo the account data is simulated",
    ]


def consent_withdraw(lang: Lang) -> str:
    return (
        "可随时在“账户”页撤回授权。" if lang == "zh" else "You can withdraw this any time on the Account tab."
    )


# ------------------------------------------------------------------ feed and profile


def feed(state: JourneyState) -> FeedSnapshot:
    from mock_webank import feed as mw

    return mw.get_feed(state.owner_id, state.start_date)


def source_for(state: JourneyState) -> FeedSnapshot | Profile:
    """The planner's input: the (mock) feed when consented, else the owner-typed profile."""
    if state.consent_feed:
        fs = feed(state)
        p = state.profile
        if p.sources.get("spare_cash") == "owner" and p.spare_cash_cny is not None:
            return fs.model_copy(update={"owner_spare_cash_cny": p.spare_cash_cny})
        return fs
    return state.profile


def profile_from_feed(fs: FeedSnapshot) -> Profile:
    """The owner's profile as the (mock) feed shows it; every field marked as coming from the feed."""
    from tools.models import MoneyRange

    recent = [m.operating_profit_cny for m in fs.profit_history[-12:]]
    avg = sum(recent, Decimal(0)) / len(recent) if recent else None
    spare = F.spare_cash(fs).value
    p = Profile(
        business_type=fs.business_type,
        shops=fs.shops,
        monthly_profit_cny=MoneyRange(low=avg, high=avg) if avg is not None else None,
        spare_cash_cny=spare,
        cash_balance_cny=fs.cash_balance_cny,
        monthly_payroll_cny=fs.monthly_payroll_cny,
        monthly_loan_repayment_cny=fs.monthly_loan_repayment_cny,
        owner_drawings_monthly_cny=fs.owner_drawings_monthly_cny,
        best_shop_cups_per_day=fs.best_shop_cups_per_day,
        avg_shop_cups_per_day=fs.avg_shop_cups_per_day,
    )
    p.sources = {
        k: "feed"
        for k in ("shops", "monthly_profit", "spare_cash", "best_shop_cups_per_day", "avg_shop_cups_per_day")
    }
    return p


FEED_FIELDS = ("shops", "monthly_profit", "spare_cash", "best_shop_cups_per_day", "avg_shop_cups_per_day")


def _figure_of(p: Profile, key: str) -> Decimal | None:
    """One profile figure as a number to compare (a profit range by its high end)."""
    if key == "monthly_profit":
        return p.monthly_profit_cny.high if p.monthly_profit_cny is not None else None
    v = {
        "shops": p.shops,
        "spare_cash": p.spare_cash_cny,
        "best_shop_cups_per_day": p.best_shop_cups_per_day,
        "avg_shop_cups_per_day": p.avg_shop_cups_per_day,
    }[key]
    return None if v is None else Decimal(v)


def _set_from(dst: Profile, src: Profile, key: str) -> None:
    attr = {"monthly_profit": "monthly_profit_cny", "spare_cash": "spare_cash_cny"}.get(key, key)
    setattr(dst, attr, getattr(src, attr))


def hold_to_feed(state: JourneyState) -> list[str]:
    """With the feed connected, a figure the feed provides is never used above the feed's figure (prereg
    addendum 2026-10-20 (13)). An owner's lower figure is used (some of the money is spoken for); a higher
    one is kept as an unverified claim and the profile goes back to the feed's figure. Returns the fields
    held back."""
    if not state.consent_feed:
        return []
    p = state.profile
    bank = profile_from_feed(feed(state))
    held: list[str] = []
    for key in FEED_FIELDS:
        if p.sources.get(key) != "owner":
            continue
        mine, theirs = _figure_of(p, key), _figure_of(bank, key)
        if mine is None or theirs is None or mine <= theirs:
            p.unverified.pop(key, None)
            continue
        p.unverified[key] = str(mine)
        _set_from(p, bank, key)
        p.sources[key] = "feed"
        held.append(key)
    return held


def spare_cash_used(state: JourneyState) -> Decimal:
    """The spare cash the plan uses (never above the feed's figure): what a goal moves to the pot."""
    return F.spare_cash(source_for(state)).value or Decimal(0)


UNVERIFIED_LABELS = {
    "shops": ("Shops you said (not verified, not used)", "你说的门店数（未核实，未采用）"),
    "monthly_profit": ("Monthly profit you said (not verified, not used)", "你说的月利润（未核实，未采用）"),
    "spare_cash": ("Spare cash you said (not verified, not used)", "你说的闲置资金（未核实，未采用）"),
    "best_shop_cups_per_day": ("Best shop's cups a day you said (not verified, not used)", "你说的最好门店日杯量（未核实，未采用）"),  # noqa: E501
    "avg_shop_cups_per_day": ("Average shop's cups a day you said (not verified, not used)", "你说的平均门店日杯量（未核实，未采用）"),  # noqa: E501
}


def unverified_lines(p: Profile, lang: Lang) -> list[ApprovalLine]:
    """The owner's figures held back because they are above the feed's: shown, labelled, never used."""
    zh = lang == "zh"
    out = []
    for key, raw in p.unverified.items():
        label = UNVERIFIED_LABELS[key][1 if zh else 0]
        value = money(Decimal(raw), "CNY", lang) if key in ("monthly_profit", "spare_cash") else raw
        out.append(ApprovalLine(label=label, value=value))
    return out


def complete_profile(p: Profile) -> Profile:
    """Fill computed fields (spare cash, floor inputs) where the feed didn't give them."""
    if p.spare_cash_cny is None:
        fig = F.spare_cash(p)
        if fig.value is not None:
            p.spare_cash_cny = fig.value
            p.sources["spare_cash"] = "computed"
    return p


def _p_fig(
    fid: str,
    label: str,
    unit: str,
    value: Decimal | None,
    src: str,
    low: Decimal | None = None,
    high: Decimal | None = None,
) -> Figure:
    from tools.figures import Source, SourceKind

    kind = {"feed": SourceKind.SIMULATED, "owner": SourceKind.OWNER, "computed": SourceKind.TOOL}.get(
        src, SourceKind.OWNER
    )
    ref = {"feed": "mock WeBank feed (simulated)", "owner": "you said", "computed": "funding.spare_cash"}.get(
        src, src
    )
    return Figure(
        id=fid, label=label, unit=unit, value=value, low=low, high=high, source=Source(kind=kind, ref=ref)
    )


def profile_fields(p: Profile, lang: Lang) -> tuple[list[Figure], list[ProfileField]]:
    zh = lang == "zh"
    figs: list[Figure] = []
    fields: list[ProfileField] = []

    def src(key: str) -> str:
        return p.sources.get(key, "missing")

    fields.append(
        ProfileField(
            key="business_type",
            label="生意" if zh else "Business",
            text=("茶饮" if zh else "Tea shops") if p.business_type == "tea" else p.business_type,
            source="feed" if p.sources.get("shops") == "feed" else "owner",
            editable=False,
        )
    )
    if p.shops is not None:
        figs.append(_p_fig("prof.shops", "Shops", "count", Decimal(p.shops), src("shops")))
        fields.append(
            ProfileField(
                key="shops",
                label="门店数" if zh else "Shops",
                figure="prof.shops",
                source=src("shops"),
                input="count",
            )
        )
    if p.monthly_profit_cny is not None:
        r = p.monthly_profit_cny
        figs.append(
            _p_fig(
                "prof.profit",
                "Monthly operating profit",
                "CNY",
                None if r.low != r.high else r.low,
                src("monthly_profit"),
                r.low if r.low != r.high else None,
                r.high if r.low != r.high else None,
            )
        )
        fields.append(
            ProfileField(
                key="monthly_profit",
                label="月经营利润" if zh else "Monthly operating profit",
                figure="prof.profit",
                source=src("monthly_profit"),
                input="money_cny",
            )
        )
    if p.spare_cash_cny is not None:
        figs.append(_p_fig("prof.spare", "Spare cash", "CNY", p.spare_cash_cny, src("spare_cash")))
        fields.append(
            ProfileField(
                key="spare_cash",
                label="闲置资金" if zh else "Spare cash",
                figure="prof.spare",
                source=src("spare_cash"),
                input="money_cny",
                editable=src("spare_cash") != "computed",
            )
        )
    for line in unverified_lines(p, lang):
        fields.append(ProfileField(key="unverified", label=line.label, text=line.value, source="owner", editable=False))  # noqa: E501
    if p.best_shop_cups_per_day is not None:
        figs.append(
            _p_fig(
                "prof.cups",
                "Best shop's cups a day",
                "cups_per_day",
                Decimal(p.best_shop_cups_per_day),
                src("best_shop_cups_per_day") if "best_shop_cups_per_day" in p.sources else "feed",
            )
        )
        fields.append(
            ProfileField(
                key="best_shop_cups_per_day",
                label="最好门店日杯量" if zh else "Best shop, cups a day",
                figure="prof.cups",
                source="feed",
                input="count",
            )
        )
    if p.avg_shop_cups_per_day is not None:
        figs.append(
            _p_fig(
                "prof.avg_cups",
                "Average shop's cups a day",
                "cups_per_day",
                Decimal(p.avg_shop_cups_per_day),
                src("avg_shop_cups_per_day") if "avg_shop_cups_per_day" in p.sources else "feed",
            )
        )
        fields.append(
            ProfileField(
                key="avg_shop_cups_per_day",
                label="门店平均日杯量" if zh else "Average shop, cups a day",
                figure="prof.avg_cups",
                source="feed",
                input="count",
            )
        )
    if p.customers:
        names = {o.value: o.label for o in O.customers(lang)}
        fields.append(
            ProfileField(
                key="customers",
                label="主要顾客" if zh else "Main customers",
                text=", ".join(names.get(c.value, c.value) for c in p.customers),
                source="owner",
                input="enum",
                options=O.customers(lang),
            )
        )
    if "budget" in p.sources or p.budget_sgd is not None:
        b = p.budget_sgd
        if b is not None:
            figs.append(_p_fig("prof.budget", "Budget", "SGD", None, "owner", b.low, b.high))
        fields.append(
            ProfileField(
                key="budget",
                label="预算" if zh else "Budget",
                figure="prof.budget" if b else None,
                text=None if b else ("还不确定" if zh else "Not sure yet"),
                source="owner",
                input="enum",
                options=O.budget(lang),
            )
        )
    return figs, fields


# ------------------------------------------------------------------ business at a glance (tools/ratios.py)

_RowSpec = tuple[str, str, str | None, tuple[str, str], tuple[str, str] | None, tuple[str, str], bool]
_GLANCE_ROWS: tuple[_RowSpec, ...] = (
    # key, figure, compare figure, (label en, zh), (compare label en, zh), (note en, zh), caveat
    ("margin", "ratio.op_margin_ttm", None, ("Operating margin, last 12 months", "近12个月经营利润率"), None,
     ("Operating profit / revenue", "经营利润 / 营业收入"), False),
    ("trend", "ratio.margin_recent_3m", "ratio.margin_year_ago_3m",
     ("Margin, last 3 months", "近3个月利润率"), ("Same months a year earlier", "去年同期"),
     ("Against the same months a year earlier: sales are seasonal, so never month on month",
      "与去年同期相比：生意有季节性，不做环比"), False),
    ("per_shop", "ratio.revenue_per_shop_month", None, ("Revenue per shop a month", "单店月营业收入"), None,
     ("Last 12 months' revenue / 12 / shops", "近12个月营业收入 / 12 / 门店数"), False),
    ("runway", "ratio.cash_runway", None, ("Cash runway", "现金可支撑"), None,
     ("Overstated: home rent and suppliers aren't in the feed, only payroll, loan repayments and listed "
      "commitments", "偏高：数据里没有国内的房租和供应商货款，只有工资、还款和已列出的支出"), True),
    ("dscr", "ratio.dscr", "ratio.dscr_after_drawings", ("Debt-service coverage", "偿债覆盖倍数"),
     ("After your drawings", "扣除您的个人支取后"),
     ("A month's operating profit / the monthly loan repayment", "月均经营利润 / 每月还款额"), False),
)
_SG_ROWS: tuple[_RowSpec, ...] = (
    ("sg_share", "ratio.sg_investment_share", "ratio.sg_investment_share_bad",
     ("Singapore investment, share of a year's profit", "新加坡投入占一年利润"),
     ("If costs go badly", "情况不理想时"),
     ("The opening investment (cost card less the running reserve) / the last 12 months' operating profit",
      "开业投入（成本卡减去运营备用金）/ 近12个月经营利润"), False),
    ("sg_vs_home", "ratio.sg_vs_home_shops", None,
     ("The Singapore shop, in home shops", "新加坡店相当于几家国内店"), None,
     ("Its steady monthly operating profit at your figure (or the middle level) / a home shop's",
      "按您的杯量（或中间档）稳定后的月经营利润 / 一家国内店的"), False),
)


def _ratio_rows(spec: tuple[_RowSpec, ...], have: set[str], lang: Lang) -> list[RatioRow]:
    i = 1 if lang == "zh" else 0
    return [
        RatioRow(key=key, label=label[i], figure=fid, compare=cmp if cmp in have else None,
                 compare_label=cl[i] if cl and cmp in have else None, note=note[i], caveat=caveat)
        for key, fid, cmp, label, cl, note, caveat in spec
        if fid in have
    ]


def business_glance(
    fs: FeedSnapshot, lang: Lang, singapore: list[Figure] | None = None
) -> tuple[list[Figure], BusinessGlance]:
    """The at-a-glance card from the feed alone; the Singapore rows only once they are computed."""
    figs = R.chain_ratios(fs) + list(singapore or [])
    have = {f.id for f in figs}
    zh = lang == "zh"
    return figs, BusinessGlance(
        rows=_ratio_rows(_GLANCE_ROWS, have, lang),
        singapore=_ratio_rows(_SG_ROWS, have, lang),
        as_of=fs.as_of.isoformat(),
        simulated_feed=fs.simulated,
        note=(
            ("根据您授权读取的账户数据计算（模拟数据）" if zh
             else "Worked out from the accounts you shared (simulated feed)")
            if fs.simulated
            else ("根据您授权读取的账户数据计算" if zh else "Worked out from the accounts you shared")
        ),
    )


def profile_summary(p: Profile, lang: Lang) -> list[ApprovalLine]:
    zh = lang == "zh"
    out = []
    if p.shops is not None:
        out.append(ApprovalLine(label="门店" if zh else "Shops", value=str(p.shops)))
    if p.monthly_profit_cny is not None:
        r = p.monthly_profit_cny
        v = (
            money(r.low, "CNY", lang)
            if r.low == r.high
            else f"{money(r.low, 'CNY', lang)}–{money(r.high, 'CNY', lang)}"
        )
        out.append(ApprovalLine(label="月利润" if zh else "Monthly profit", value=v))
    if p.spare_cash_cny is not None:
        out.append(
            ApprovalLine(label="闲置资金" if zh else "Spare cash", value=money(p.spare_cash_cny, "CNY", lang))
        )
    out += unverified_lines(p, lang)
    if p.customers:
        names = {o.value: o.label for o in O.customers(lang)}
        out.append(ApprovalLine(label="主要顾客" if zh else "Customers", value=names[p.customers[0].value]))
    if p.budget_sgd is not None:
        out.append(
            ApprovalLine(
                label="预算" if zh else "Budget",
                value=f"{money(p.budget_sgd.low, 'SGD', lang)}–{money(p.budget_sgd.high, 'SGD', lang)}",
            )
        )
    if p.opening_window_months is not None:
        wins = {12: "6_12", 18: "12_18", 24: "18_24", 30: "no_rush"}
        names = {o.value: o.label for o in O.window(lang)}
        out.append(
            ApprovalLine(
                label="开业时间" if zh else "Opening",
                value=names.get(wins.get(p.opening_window_months, ""), ""),
            )
        )
    return out


def edit_profile_field(p: Profile, key: str, value: Any) -> None:
    from agent.parse import amounts, money_range

    if key == "shops":
        n = amounts(str(value))
        if n:
            p.shops = int(n[0])
            p.sources["shops"] = "owner"
    elif key == "monthly_profit":
        r = money_range(str(value))
        if r:
            from tools.models import MoneyRange

            p.monthly_profit_cny = MoneyRange(low=r[0], high=r[1])
            p.sources["monthly_profit"] = "owner"
    elif key == "spare_cash":
        n = amounts(str(value))
        if n:
            p.spare_cash_cny = n[0]
            p.sources["spare_cash"] = "owner"
    elif key == "customers":
        from tools.models import CustomerGroup

        p.customers = [CustomerGroup(str(value))]
    elif key == "budget":
        from tools.models import MoneyRange

        if str(value) in O.BUDGET_BANDS_SGD:
            lo, hi = O.BUDGET_BANDS_SGD[str(value)]
            p.budget_sgd = MoneyRange(low=lo, high=hi)
        elif str(value) == "not_sure":
            p.budget_sgd = None
    elif key == "best_shop_cups_per_day":
        n = amounts(str(value))
        if n:
            p.best_shop_cups_per_day = int(n[0])
            p.sources["best_shop_cups_per_day"] = "owner"
    elif key == "avg_shop_cups_per_day":
        n = amounts(str(value))
        if n:
            p.avg_shop_cups_per_day = int(n[0])
            p.sources["avg_shop_cups_per_day"] = "owner"


# ------------------------------------------------------------------ sites


def area_names() -> dict[str, str]:
    return {a.id: a.name for a in D.load_areas()}


def area(area_id: str) -> Area:
    return D.areas_by_id()[area_id]


def unit(unit_id: str) -> Unit:
    return D.unit_by_id(unit_id)


@cache
def _listed_areas() -> frozenset[str]:
    return frozenset(u.area_id.upper() for u in D.load_units())


def has_listings(area_id: str) -> bool:
    """Whether any unit is listed for lease in the area (the next step costs a unit there)."""
    return area_id.upper() in _listed_areas()


def rank(profile: Profile, priority: Priority | None, ruled_out: list[str]) -> list[AreaScore]:
    from tools import sites as S

    return S.rank_areas(list(D.load_areas()), profile, priority or Priority.NEAR_CUSTOMERS, ruled_out)


REASONS: dict[str, dict[str, str]] = {
    "many_young_adults": {"en": "Many residents aged twenty to thirty-nine", "zh": "二三十岁的居民多"},
    "many_students": {"en": "Lots of students nearby", "zh": "附近学生多"},
    "many_families": {"en": "Many families live here", "zh": "家庭住户多"},
    "many_office_workers": {"en": "A big daytime workforce", "zh": "白天上班人群多"},
    "high_income": {"en": "Higher household incomes", "zh": "家庭收入较高"},
    "busy_stations": {"en": "Busy train stations", "zh": "地铁站繁忙"},
    "many_stations": {"en": "Several train stations", "zh": "地铁站多"},
    "rent_in_budget": {"en": "Rents fit your budget", "zh": "租金符合预算"},
    "many_food_outlets": {"en": "A busy food scene (more competition too)", "zh": "餐饮聚集（竞争也更多）"},
    "large_population": {"en": "A large resident population", "zh": "常住人口多"},
    "many_tourists": {"en": "Lots of visitors", "zh": "游客多"},
    "daytime_crowd": {"en": "A big daytime crowd of workers and visitors", "zh": "白天上班和到访人群多"},
    "low_rent": {"en": "Lower rents than most areas", "zh": "租金低于多数区域"},
}


def reason_lines(codes: list[str], lang: Lang) -> list[str]:
    return [REASONS[c][lang] if c in REASONS else c.replace("_", " ") for c in codes]


_SOURCE_SKIP = {"id", "name", "region", "centroid"}  # geometry bookkeeping, not facts the owner reads


def area_sources(a: Area | None = None) -> list[SourceNote]:
    """One short line per dataset behind the card's facts (title and edition), not one per field."""
    if a is None or not a.sources:
        return [SourceNote(label="SingStat; URA; LTA; SFA via data.gov.sg", url="https://data.gov.sg")]
    out: dict[str, SourceNote] = {}
    for k, v in sorted(a.sources.items()):
        if k in _SOURCE_SKIP or not v:
            continue
        url = None
        m = re.search(r"\((https?://[^)\s]+)\)", v)
        if m:
            url, v = m.group(1), v.replace(m.group(0), "")
        parts = [x.strip() for x in v.split(";")[0].split("·")]
        if parts and re.fullmatch(r"(d_[0-9a-f]+|[a-z]+:[\w-]+)", parts[0]):
            parts = parts[1:]  # dataset id
        label = " · ".join(parts[:2]) if parts else k
        if url is None and re.match(r"d_[0-9a-f]+", v.strip()):
            url = f"https://data.gov.sg/datasets/{v.strip().split()[0]}/view"
        out.setdefault(label, SourceNote(label=label, url=url))
    return list(out.values()) or [SourceNote(label="data.gov.sg", url="https://data.gov.sg")]


def area_card_data(
    a: Area, score: AreaScore | None, profile: Profile, lang: Lang
) -> tuple[list[Figure], list[str], list[Factor], dict[str, float]]:
    from tools import sites as S

    ap = S.area_profile(a, profile)
    figs = list(ap.figures)
    ids = [f.id for f in figs]
    factors: list[Factor] = []
    if score is not None:
        labels = {
            "customer_fit": ("Customer fit", "客群匹配"),
            "traffic": ("Station traffic", "地铁客流"),
            "affordability": ("Rent vs budget", "租金与预算"),
            "competition": ("Food outlets nearby", "附近餐饮"),
            "population": ("Residents", "居民数量"),
        }
        weights = {k: float(v) for k, v in P.table("area_weights").get(_priority_of(profile), {}).items()}
        # a factor with no data drops out and the rest are reweighted (tools/sites.py), so each
        # factor's maximum is its share of the weights that were actually used
        used = sum(weights.get(k, 0.0) for k in score.contributions) or 1.0
        weights = {k: 100.0 * weights.get(k, 0.0) / used for k in score.contributions}
        for k, pts in score.contributions.items():
            en, zh = labels.get(k, (k, k))
            factors.append(
                Factor(
                    key=k,
                    label=zh if lang == "zh" else en,
                    points=round(pts, 1),
                    max_points=round(weights.get(k, 0.0), 1),
                    detail="",
                )
            )
    return figs, ids, factors, dict(ap.age_bands or a.age_shares)


_PRIORITY: dict[str, str] = {}


def _priority_of(profile: Profile) -> str:
    return _PRIORITY.get("current", "near_customers")


def units(area_id: str, profile: Profile, shortlist: Shortlist) -> tuple[list[Unit], bool]:
    """Units in the area within budget; if none, the closest ones (flagged over budget)."""
    from tools import sites as S

    pr = shortlist.priority or Priority.NEAR_CUSTOMERS
    _PRIORITY["current"] = pr.value
    within = list(S.list_units([area_id], shortlist.size_range_sqft, profile.budget_sgd, pr))
    if within or profile.budget_sgd is None:
        return within, False
    return list(S.list_units([area_id], shortlist.size_range_sqft, None, Priority.LOW_RENT)), True


def unit_row(u: Unit, profile: Profile, lang: Lang) -> tuple[list[Figure], UnitRow]:
    from tools import sites as S

    row = S.compare_units([u.id], profile)[0]
    figs = [
        f
        for f in (row.rent_total, row.breakeven, row.early_cost, row.best_shop, row.avg_shop)
        if f is not None
    ]
    return figs, UnitRow(
        id=u.id,
        mall=u.mall,
        unit_no=u.unit_no,
        area_name=row.area_name,
        size_sqft=u.size_sqft,
        rent=row.rent_total.id,
        gto_pct=float(u.gto_pct) if u.gto_pct is not None else None,
        breakeven=row.breakeven.id,
        best_shop_cups=row.best_shop.id if row.best_shop else None,
        avg_shop_cups=row.avg_shop.id if row.avg_shop else None,
        early_cost=row.early_cost.id,
        lat=u.lat,
        lng=u.lng,
        simulated=u.simulated,
    )


def unit_summary(u: Unit, t: Turn) -> list[ApprovalLine]:
    zh = t.lang == "zh"
    d = t.figs

    def disp(fid: str) -> str:
        f = d.get(fid)
        from agent.render import fmt_figure

        return fmt_figure(f, t.lang, t.state.start_date) if f else ""

    return [
        ApprovalLine(
            label="面积" if zh else "Size",
            value=f"{u.size_sqft:,} sq ft" if not zh else f"{u.size_sqft:,}平方英尺",
        ),
        ApprovalLine(
            label="月租（含服务费）" if zh else "Rent with service charge",
            value=disp(f"unit.{u.id}.rent_total"),
        ),
        ApprovalLine(label="保本杯量" if zh else "Break-even", value=disp(f"unit.{u.id}.breakeven")),
        ApprovalLine(
            label="初步成本" if zh else "Early cost estimate", value=disp(f"unit.{u.id}.early_cost")
        ),
    ]


# ------------------------------------------------------------------ costs


def overrides_from(card: CostCard | None) -> dict[str, Decimal]:
    if card is None:
        return {}
    return {ln.key: ln.likely_sgd for ln in card.lines if ln.source.startswith("owner")}


def estimate(
    u: Unit,
    profile: Profile,
    level: str,
    mgr: str,
    quotes: list[ExtractedQuote],
    overrides: dict[str, Decimal],
    rent_free_months: Decimal | None = None,
) -> CostCard:
    accepted = [
        q.model_copy(update={"lines": [ln for ln in q.lines if ln.status == "accepted"]}) for q in quotes
    ]
    card = C.estimate_costs(
        u,
        profile,
        level,  # type: ignore[arg-type]
        mgr,  # type: ignore[arg-type]
        [q for q in accepted if q.lines],
        rent_free_months=rent_free_months,
    )
    if overrides:
        lines = []
        for ln in card.lines:
            if ln.key in overrides:
                v = overrides[ln.key]
                ln = ln.model_copy(
                    update={
                        "likely_sgd": v,
                        "mode_sgd": v,
                        "bad_sgd": max(v, ln.bad_sgd * v / ln.likely_sgd if ln.likely_sgd else v),
                        "source": "owner",
                        "flags": [],
                    }
                )
            lines.append(ln)
        card = card.model_copy(
            update={
                "lines": lines,
                "total_likely_sgd": sum((ln.likely_sgd for ln in lines), Decimal(0)),
                "total_bad_sgd": max(card.total_bad_sgd, sum((ln.likely_sgd for ln in lines), Decimal(0))),
            }
        )
    return card


def set_override(card: CostCard, key: str, value: Any) -> None:
    from agent.parse import amounts

    vals = amounts(str(value))
    if not vals:
        return
    for i, ln in enumerate(card.lines):
        if ln.key == key:
            card.lines[i] = ln.model_copy(
                update={"likely_sgd": vals[0], "mode_sgd": vals[0], "source": "owner", "flags": []}
            )


GROUP_LABELS = {
    "lease": ("Deposit and lease", "押金与租约"),
    "fitout": ("Fit-out and equipment", "装修与设备"),
    "setup": ("Company setup and licences", "公司设立与执照"),
    "people": ("People before opening", "开业前人工"),
    "reserve": ("Running-cost reserve", "运营储备金"),
    "gst": ("GST", "消费税"),
}


def cost_breakdown(card: CostCard, lang: Lang, read_only: bool = False) -> tuple[list[Figure], CostBreakdown]:
    figs = C.cost_figures(card, lang)
    keyed = {ln.key: ln for ln in D.load_cost_key().lines}
    groups = []
    for g, lines in card.by_group().items():
        en, zh = GROUP_LABELS.get(g, (g, g))
        rows = []
        for ln in lines:
            kl = keyed.get(ln.key)
            if ln.from_quote:
                src = SourceNote(
                    label=("报价单" if lang == "zh" else "Your quote")
                    + f" ({ln.source.split(':', 1)[-1]})"
                    + ("，含变更预留" if lang == "zh" else ", plus a variation allowance")
                )
            elif ln.source == "owner":
                src = SourceNote(label="你填写的" if lang == "zh" else "You entered this")
            else:
                src = SourceNote(
                    label=kl.source if kl else ln.source,
                    url=kl.url if kl else None,
                    as_of=str(kl.as_of) if kl and kl.as_of else None,
                )
            rows.append(
                CostLineRow(
                    key=ln.key,
                    label=ln.label,
                    likely=f"cost.{ln.key}.likely",
                    bad=f"cost.{ln.key}.bad",
                    source=src,
                    from_quote=ln.from_quote,
                    editable=not read_only,
                    flags=ln.flags,
                )
            )
        groups.append(
            CostGroupRow(
                key=g,
                label=zh if lang == "zh" else en,
                likely=f"cost.group.{g}.likely",
                bad=f"cost.group.{g}.bad",
                lines=rows,
            )
        )
    return figs, CostBreakdown(
        groups=groups,
        total_likely="cost.total.likely_sgd",
        total_bad="cost.total.bad_sgd",
        total_likely_cny="cost.total.likely_cny",
        total_bad_cny="cost.total.bad_cny",
        read_only=read_only,
    )


def cost_summary(card: CostCard, t: Turn) -> list[ApprovalLine]:
    from agent.render import fmt_figure

    zh = t.lang == "zh"
    d = t.figs

    def disp(fid: str) -> str:
        f = d.get(fid)
        return fmt_figure(f, t.lang, t.state.start_date) if f else ""

    return [
        ApprovalLine(label="预计总额" if zh else "Likely total", value=disp("cost.total.likely_sgd")),
        ApprovalLine(label="情况不理想时" if zh else "If things go badly", value=disp("cost.total.bad_sgd")),
        ApprovalLine(label="折合人民币" if zh else "In RMB (likely)", value=disp("cost.total.likely_cny")),
    ]


def missing(card: CostCard, quotes: list[ExtractedQuote], lang: Lang) -> list[Option]:
    """What to ask the contractor whose quote the owner accepted: what the quote excludes, then lines in
    the cost groups it touched that no quote covers. Nothing without a quote (the cost card already shows
    every estimate and its source); the full list stays on `card.missing` for the tools."""
    items = C.missing_items(card, quotes, lang)
    included = {m.split(":", 1)[1] for m in card.missing if m.startswith("included:")}
    quoted = {ln.group for ln in card.lines if ln.from_quote}
    group_of = {ln.key: ln.group for ln in card.lines}
    owner_set = {ln.key for ln in card.lines if ln.source == "owner"}
    keep = [m for m in items if m.key not in included]
    # quotes to check (part only, below the estimate, two that disagree) always; then what is excluded;
    # then lines with no quote in the groups a quote touched. An owner's own figure settles a line.
    to_check = ("partial", "below_estimate", "conflict")
    checks = [m for m in keep if m.kind in to_check and m.key not in owner_set]
    keep = (
        checks
        + [m for m in keep if m.kind == "excluded"]
        + [
            m
            for m in keep
            if m.kind == "no_quote" and group_of.get(m.key) in quoted and m.key not in owner_set
        ]
    )
    by_key: dict[str, Option] = {}
    for m in keep:  # one item per cost line (the widget keys items by line)
        if m.key in by_key:
            o = by_key[m.key]
            by_key[m.key] = o.model_copy(update={"detail": f"{o.detail}. {m.detail}"})
        else:
            by_key[m.key] = Option(value=m.key, label=m.label, detail=m.detail)
    return list(by_key.values())


def match_line(label: str) -> tuple[str | None, bool]:
    """The quotable cost line a quote line names, by keywords (code, not the model): the longest keyword
    found wins, a whole-line keyword before a part keyword of the same length. (key, part); (None, False)
    when nothing matches: the line stays unmatched for the owner to assign, never a default line."""
    lab = label.lower()
    best: tuple[int, int, str] | None = None
    for kl in D.load_cost_key().lines:
        if not kl.quotable:
            continue
        for whole, kws in ((1, kl.keywords), (0, kl.part_keywords)):
            for k in kws:
                if k.lower() in lab and (best is None or (len(k), whole) > best[:2]):
                    best = (len(k), whole, kl.key)
    if best is None:
        return None, False
    return best[2], best[1] == 0


def match_quote(q: ExtractedQuote) -> ExtractedQuote:
    """Match each extracted line to a cost-key line by keywords. Unmatched lines stay unmatched."""
    lines = []
    for ln in q.lines:
        key, part = match_line(ln.label)
        lines.append(ln.model_copy(update={"matched_key": key, "part": part}))
    return q.model_copy(update={"lines": lines})


def assign_line(quotes: list[ExtractedQuote], line_id: str, key: str | None) -> bool:
    """The owner says which cost line a quote line is for (or none). An assigned line prices part of the
    line until the owner says the quote covers all of it. False if the line or the key is unknown."""
    keys = {kl.key for kl in D.load_cost_key().lines if kl.quotable}
    if key is not None and key not in keys:
        return False
    for q in quotes:
        for li, ln in enumerate(q.lines):
            if ln.id == line_id:
                q.lines[li] = ln.model_copy(update={"matched_key": key, "part": key is not None})
                return True
    return False


def set_coverage(quotes: list[ExtractedQuote], doc_id: str, key: str, whole: bool) -> bool:
    """The owner says whether one document covers all of a cost line or only part of it."""
    for q in quotes:
        if q.doc_id != doc_id:
            continue
        hit = False
        for li, ln in enumerate(q.lines):
            if ln.matched_key == key:
                q.lines[li] = ln.model_copy(update={"part": not whole})
                hit = True
        return hit
    return False


def doc_decided(quotes: list[ExtractedQuote], doc_id: str) -> bool:
    """True once every line of the document is accepted or rejected."""
    q = next((q for q in quotes if q.doc_id == doc_id), None)
    return q is not None and all(ln.status in ("accepted", "rejected") for ln in q.lines)


def doc_of_line(quotes: list[ExtractedQuote], line_id: str) -> str | None:
    return next((q.doc_id for q in quotes for ln in q.lines if ln.id == line_id), None)


def upload_payload(
    q: ExtractedQuote, image_url: str | None, mode: str, lang: Lang
) -> tuple[list[Figure], UploadPrompt]:
    from tools.figures import Source, SourceKind, Taint

    figs, rows = [], []
    keyed = {kl.key: kl for kl in D.load_cost_key().lines}

    def name(key: str) -> str:
        kl = keyed[key]
        return kl.label_zh if lang == "zh" else kl.label_en

    for ln in q.lines:
        fid = f"doc.{ln.id}"
        if ln.amount is not None:
            figs.append(
                Figure(
                    id=fid,
                    label=ln.label,
                    unit=ln.currency,
                    value=ln.amount,
                    source=Source(kind=SourceKind.DOCUMENT, ref=q.doc_id, note=f"read by {mode}"),
                    taint=Taint.UNTRUSTED,
                )
            )
        kl = keyed.get(ln.matched_key or "")
        rows.append(
            ExtractedRow(
                id=ln.id,
                label=ln.label,
                amount=fid if ln.amount is not None else None,
                bbox=ln.bbox,
                confidence=ln.confidence,
                status=ln.status,
                matched_label=name(kl.key) if kl else None,
                matched_key=ln.matched_key,
                part=ln.part,
            )
        )
    touched = list(dict.fromkeys(ln.matched_key for ln in q.lines if ln.matched_key is not None))
    coverage = [
        CoverageRow(key=k, label=name(k), whole=any(not ln.part for ln in q.lines if ln.matched_key == k))
        for k in touched
    ]
    assignable = [Option(value=kl.key, label=name(kl.key)) for kl in keyed.values() if kl.quotable]
    return figs, UploadPrompt(
        doc_id=q.doc_id,
        image_url=image_url,
        extracted=rows,
        exclusions=q.exclusions,
        reader_mode=mode,
        coverage=coverage,
        assignable=assignable,
    )


def accept_all_lines(quotes: list[ExtractedQuote], doc_id: str) -> bool:
    """Accept every pending line of one document (or of the latest, if no id). Lines marked "check" (read
    with low confidence) are left for the owner to confirm one by one. True once every line is decided."""
    if not quotes:
        return False
    q_idx = next((i for i, q in enumerate(quotes) if q.doc_id == doc_id), len(quotes) - 1)
    q = quotes[q_idx]
    for li, ln in enumerate(q.lines):
        if ln.status == "pending":
            q.lines[li] = ln.model_copy(update={"status": "accepted"})
    quotes[q_idx] = q
    return all(x.status in ("accepted", "rejected") for x in q.lines)


def lines_to_check(quotes: list[ExtractedQuote], doc_id: str) -> int:
    """How many lines of a document are still marked "check"."""
    q = next((q for q in quotes if q.doc_id == doc_id), quotes[-1] if quotes else None)
    return 0 if q is None else sum(1 for ln in q.lines if ln.status == "check")


def set_line_status(quotes: list[ExtractedQuote], line_id: str, status: str) -> bool:
    """Update one extracted line; True once every line of that document is decided."""
    for qi, q in enumerate(quotes):
        for li, ln in enumerate(q.lines):
            if ln.id == line_id:
                q.lines[li] = ln.model_copy(update={"status": status})
                quotes[qi] = q
                return all(x.status in ("accepted", "rejected") for x in q.lines)
    return False


# ------------------------------------------------------------------ funding and plan


@dataclass
class Basics:
    floor: Decimal
    buffer: Decimal
    figures: list[Figure]


def funding_basics(state: JourneyState) -> Basics:
    src = source_for(state)
    assert state.cost_card is not None
    fl = F.safety_floor(src)
    spare = F.spare_cash(src)
    cost_figs = C.cost_figures(state.cost_card)
    gap = F.funding_gap(state.cost_card, spare, cost_figs)
    figs = [*(fl.figures if fl else []), spare, gap, *cost_figs]
    return Basics(
        floor=fl.floor_cny if fl else Decimal(0), buffer=fl.buffer_cny if fl else Decimal(0), figures=figs
    )


def _funding_card(r: F.FundingOptionResult, figs: list[Figure]) -> FundingCard:
    o = r.option
    shown = r.amount is not None and o.status != "closed" and r.amount.value not in (None, 0)
    if shown and r.amount is not None:
        figs.append(r.amount)
    return FundingCard(
        id=o.id,
        label=o.label,
        status=o.status,
        covers=o.covers,
        available_from=o.available_from,
        cost=o.cost,
        conditions=o.conditions,
        amount=r.amount.id if shown and r.amount else None,  # no "RMB 0" on an option not taken
        on=o.on,
        rule_ids=o.rule_ids,
        source=SourceNote(label=o.source, url=o.source_url, kind=o.source_kind) if o.source else None,
        variant=o.card,
        as_of=o.as_of.isoformat() if o.as_of else None,
        subject_to_approval=o.subject_to_approval,
        product=SourceNote(label=o.product, url=o.product_url) if o.product else None,
        note=o.note,
        note_rule=o.note_rule,
    )


def _ranked_card(card: FundingCard, r: F.RankedRoute, figs: list[Figure]) -> FundingCard:
    """The card with this owner's ranking words, and the figures behind them."""
    if not r.eligible:
        return card.model_copy(update={"why_not": r.why_not, "amount": None})
    why = None
    if r.ranked and r.cost is not None and r.dilution is not None:
        shown = [f for f in (r.cost, r.weeks, r.dilution, r.floor_change) if f is not None]
        figs.extend(shown)
        why = RankWhy(
            cost=r.cost.id,
            weeks=r.weeks.id if r.weeks else None,
            dilution=r.dilution.id,
            floor_change=r.floor_change.id if r.floor_change else None,
        )
    return card.model_copy(update={"words": r.words, "why": why})


def funding_options(state: JourneyState, lang: Lang) -> tuple[FundingOptions, list[Figure]]:
    """The funding screen: this owner's open routes in ranked order (code ranks them on the current plan's
    full solve), then those not open to them yet with why, the bank cards and the after-opening view."""
    src = source_for(state)
    assert state.cost_card is not None and state.funding is not None
    res = {r.option.id: r for r in F.funding_options(src, state.cost_card, state.funding, lang)}
    u = _unit_from(state)
    ranking = F.rank_options(
        src,
        state.cost_card,
        state.funding,
        simulate(state),
        start_date=state.start_date,
        unit_available_from=u.available_from if u else None,
        lang=lang,
    )
    figs: list[Figure] = []
    cards = [_ranked_card(_funding_card(res[r.id], figs), r, figs) for r in ranking if r.id in res]
    banks = [_funding_card(r, figs) for r in F.bank_cards(src, lang)]
    later = [_funding_card(r, figs) for r in F.later_cards(lang)]
    return FundingOptions(
        gap="funding.gap",
        spare="home.spare_cash",
        options=[c for c in cards if c.why_not is None],
        webank_role=F.webank_role(lang),
        bank_cards=banks,
        later_cards=later,
        not_yet=[c for c in cards if c.why_not is not None],
    ), figs


def savings_presets() -> list[Decimal]:
    return list(O.SAVINGS_CNY.values())


def funding_compare(
    state: JourneyState, lang: Lang, savings: Decimal | None = None
) -> tuple[FundingCompare, list[Figure]]:
    """Compare funding plans: one full solve per column at the plan's (the slider's) share; `savings` is the
    savings column's amount (default: what the owner put in, else the smallest amount they're offered)."""
    src = source_for(state)
    assert state.cost_card is not None and state.funding is not None
    plan = state.funding
    amount = CMP.default_savings(plan, savings_presets()) if savings is None else savings
    u = _unit_from(state)
    cols = CMP.compare_plans(
        src,
        state.cost_card,
        plan,
        savings_cny=amount,
        start_date=state.start_date,
        unit_available_from=u.available_from if u else None,
        lang=lang,
    )
    cap = CMP.savings_max(state.cost_card)
    share = derived(
        "plan.setaside_share", "Set-aside share", "pct", plan.setaside_share, tool="simulate_plan"
    )
    figs: list[Figure] = [cap, share]
    out: list[CompareColumn] = []
    for c in cols:
        figs.extend(c.figures())

        def fid(f: Figure | None) -> str | None:
            return None if f is None else f.id

        out.append(
            CompareColumn(
                id=c.id,
                title=c.title,
                blurb=c.blurb,
                open=c.open,
                why_not=c.why_not,
                chosen=c.chosen,
                savings_editable=c.open and bool(c.toggles.get("own_savings")),
                savings=fid(c.savings),
                monthly=fid(c.monthly),
                open_likely=fid(c.open_likely),
                open_p95=fid(c.open_p95),
                floor_risk=fid(c.floor_risk),
                floor_risk_upper=fid(c.floor_risk_upper),
                ownership=fid(c.ownership),
                profit_share=fid(c.profit_share),
                pros=c.pros,
                cons=c.cons,
                terms=[CompareTerms(**t.model_dump()) for t in c.terms],
                toggles=[CompareToggle(id=k, on=v) for k, v in c.toggles.items()],
            )
        )
    payload = FundingCompare(
        share=float(plan.setaside_share), share_fig=share.id, columns=out, savings_max=cap.id
    )
    return payload, figs


def compare_preview(state: JourneyState, savings: Decimal, lang: Lang) -> dict[str, Any]:
    """The compare view with the savings column at another amount (the owner editing it)."""
    from agent.render import display_map

    payload, figs = funding_compare(state, lang, savings)
    fmap = {f.id: f for f in figs}
    return {
        "columns": [c.model_dump() for c in payload.columns],
        "figures": {k: v.model_dump(mode="json") for k, v in fmap.items()},
        "display": display_map(fmap, lang, state.start_date),
    }


def savings_in_range(state: JourneyState, value: object) -> Decimal | None:
    """Extra savings from the compare view: a number from 0 up to the plan's likely total, else None."""
    from decimal import InvalidOperation

    assert state.cost_card is not None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    cap = CMP.savings_max(state.cost_card).value
    if not amount.is_finite() or amount < 0 or cap is None or amount > cap:
        return None
    return amount.quantize(Decimal("1"))


def closed_options(lang: Lang) -> ClosedOptions:
    return ClosedOptions(
        options=[
            ClosedRoute(
                id=c.id,
                label=c.label,
                rule_id=c.rule_id,
                reason=c.reason,
                source=SourceNote(label=c.source, url=c.source_url, kind=c.source_kind),
            )
            for c in F.closed_options(lang)
        ]
    )


def _unit_from(state: JourneyState) -> Unit | None:
    uid = state.shortlist.chosen_unit_id
    return unit(uid) if uid else None


def simulate(state: JourneyState, share: Decimal | None = None, runs: int | None = None) -> PlanResult:
    assert state.cost_card is not None and state.funding is not None
    plan = state.funding if share is None else state.funding.model_copy(update={"setaside_share": share})
    u = _unit_from(state)
    return PL.simulate_plan(
        source_for(state),
        state.cost_card,
        plan,
        runs=runs,
        start_date=state.start_date,
        unit_available_from=u.available_from if u else None,
    )


def wall(state: JourneyState) -> Decimal:
    assert state.cost_card is not None and state.funding is not None
    u = _unit_from(state)
    inp = PL.build_inputs(
        source_for(state),
        state.cost_card,
        state.funding,
        state.start_date,
        unit_available_from=u.available_from if u else None,
    )
    return PL.find_wall(inp)


def plan_figs(result: PlanResult) -> list[Figure]:
    return PL.plan_figures(result)


def chart(result: PlanResult, start: date, lang: Lang) -> ChartSeries:
    c = result.chart
    return ChartSeries(
        weeks=c.weeks,
        month_labels=[month_label(start, w, lang) for w in c.weeks],
        pot_p10=c.pot_p10,
        pot_p50=c.pot_p50,
        pot_p90=c.pot_p90,
        need=c.need,
        home_p05=c.home_p05,
        home_p50=c.home_p50,
        floor=c.floor,
        milestones=[(w, milestone_label(m, lang)) for w, m in c.milestones],
    )


def preview(state: JourneyState, share: float, lang: Lang) -> dict[str, Any]:
    from agent.render import display_map

    assert state.cost_card is not None and state.funding is not None
    u = _unit_from(state)
    res = PL.preview(
        source_for(state),
        state.cost_card,
        state.funding,
        share,
        start_date=state.start_date,
        unit_available_from=u.available_from if u else None,
    )
    figs = {f.id: f for f in PL.plan_figures(res)}
    return {
        "share": share,
        "chart": chart(res, state.start_date, lang).model_dump(),
        "figures": {k: v.model_dump(mode="json") for k, v in figs.items()},
        "display": display_map(figs, lang, state.start_date),
        "wall": float(res.wall_share),
    }


def option_status(option_id: str) -> str | None:
    """open | optional | closed for a catalogue option, None if unknown."""
    for o in D.load_catalogue().options:
        if o.id == option_id:
            return str(o.status)
    return None


def option_rules(option_id: str) -> list[str]:
    for o in D.load_catalogue().options:
        if o.id == option_id:
            return list(o.rule_ids)
    return []


def option_in_plan(option_id: str) -> bool:
    """Only plan routes can be switched into the Singapore plan; bank cards are shown, never counted."""
    o = D.load_catalogue().get(option_id)
    return o is not None and o.in_plan


def never_in_plan_rule(option_id: str) -> str | None:
    o = D.load_catalogue().get(option_id)
    return None if o is None else o.never_in_plan


def toggle_option(plan: FundingPlan, option_id: str, on: bool) -> None:
    if not option_in_plan(option_id):
        return  # a bank card (e.g. WeBank home working capital) never counts toward Singapore
    if on and option_id not in plan.options_on:
        plan.options_on.append(option_id)
    if not on and option_id in plan.options_on:
        plan.options_on.remove(option_id)
    if option_id == "staged_contractor":
        plan.staged_contractor = on
    elif option_id in ("partner_equity", "local_partner"):
        plan.partner_equity_share = Decimal("0.30") if on else Decimal("0")
        plan.partner_considered = plan.partner_considered or on
    elif option_id in ("own_savings",) and not on:
        plan.own_savings_cny = Decimal(0)


def mix(state: JourneyState) -> tuple[list[Figure], list[dict[str, str]], str]:
    assert state.cost_card is not None and state.funding is not None
    res = F.funding_mix(state.funding, state.cost_card, state.plan, source_for(state), state.lang)
    figs = [res.total, *[p.amount for p in res.parts]]
    if res.setaside_months is not None:
        figs.append(res.setaside_months)
    return figs, [{"key": p.key, "label": p.label, "amount": p.amount.id} for p in res.parts], res.total.id


def check_plan(state: JourneyState, fresh: bool = False) -> list[str]:
    """The rules engine's blocking violations. `fresh` re-simulates from the current state (the approval
    re-check) instead of reusing the stored result."""
    from rules import engine as R

    assert state.funding is not None and state.cost_card is not None
    res = simulate(state) if fresh or state.plan is None else state.plan
    feed_snap = feed(state) if state.consent_feed else None
    return [
        v.rule_id
        for v in R.blocking(R.check_plan(state.funding, res, state.cost_card, state.profile, feed_snap))
    ]


def alternative(value: str) -> dict[str, Any] | None:
    """A lawful alternative from rules/rules.yaml (`alternatives`): its action, labels, a topic's id."""
    a = _rules().get("alternatives", {}).get(value)
    return None if a is None else dict(a)


def lawful_options(state: JourneyState, rule_id: str, lang: Lang) -> list[Option]:
    """The rule's own lawful alternatives (rules/rules.yaml), most specific first."""
    _ = state  # the same options at every step; guard_option decides what a pick does from the state
    out: list[Option] = []
    for value in _rules()["rules"][rule_id].get("alternatives", []):
        a = alternative(str(value))
        if a is not None:
            out.append(Option(value=str(value), label=a[f"label_{lang}"], detail=a.get(f"detail_{lang}")))
    return out


# ------------------------------------------------------------------ timeline and goal


MILESTONE_LABELS: dict[str, tuple[str, str]] = {
    "lender_consent": ("WeBank's consent as lender", "微众银行同意（贷款人）"),
    "odi_filing": ("ODI filing (DRC and Commerce Bureau)", "境外投资备案（发改委、商务局）"),
    "bank_registration": ("Bank ODI registration", "银行境外投资登记"),
    "incorporate": ("Incorporate and open the Singapore account", "注册公司并开立新加坡账户"),
    "setup_transfer": ("Setup transfer", "设立资金汇出"),
    "first_transfer": ("First main transfer", "首笔主要汇款"),
    "sign_lease": ("Accept the offer and sign the lease", "接受要约并签署租约"),
    "fitout": ("Fit-out", "装修"),
    "licence": ("Food shop licence", "食品店执照"),
    "hiring": ("Hire and train local staff", "招聘并培训本地员工"),
    "opening": ("Opening", "开业"),
}
WHO: dict[str, tuple[str, str]] = {
    "lender_consent": ("You send; WeBank decides", "你发送，微众银行审批"),
    "odi_filing": ("Your filing agent", "备案代办"),
    "bank_registration": ("Your ODI bank", "你的境外投资银行"),
    "incorporate": ("Corporate service firm; Singapore bank", "秘书公司；新加坡银行"),
    "setup_transfer": ("You release", "你本人确认汇出"),
    "first_transfer": ("You release", "你本人确认汇出"),
    "sign_lease": ("Your Singapore company", "你的新加坡公司"),
    "fitout": ("Your contractor", "装修承包商"),
    "licence": ("Your Singapore company", "你的新加坡公司"),
    "hiring": ("Your Singapore company (locals first: MOM quotas)", "你的新加坡公司（先招本地：人力部配额）"),
    "opening": ("You", "你"),
}


def milestone_label(mid: str, lang: Lang) -> str:
    en, zh = MILESTONE_LABELS.get(mid, (mid, mid))
    return zh if lang == "zh" else en


def timeline_payload(state: JourneyState, lang: Lang) -> tuple[list[Figure], MilestoneTimeline]:
    from tools import timeline as TL

    assert state.plan is not None
    ms = TL.build_timeline(state.plan)
    start = state.start_date
    figs, items = [], []
    for m in ms:
        fid = f"ms.{m.id}.likely"
        figs.append(derived(fid, milestone_label(m.id, lang), "weeks", m.likely_week, tool="timeline"))
        en, zh = WHO.get(m.id, ("", ""))
        items.append(
            TimelineItem(
                id=m.id,
                order=m.order,
                label=milestone_label(m.id, lang),
                who=zh if lang == "zh" else en,
                likely=fid,
                likely_date=month_label(start, m.likely_week, lang),
                latest_safe_date=month_label(start, m.latest_safe_week, lang),
                act_by_date=month_label(start, m.act_by_week, lang),
                status=m.status.value,
            )
        )
    return figs, MilestoneTimeline(start_date=start.isoformat(), items=items)


def goal_sentence(state: JourneyState, lang: Lang) -> tuple[list[Figure], str, list[str], list[str]]:
    assert state.plan is not None
    figs = PL.plan_figures(state.plan)
    u = _unit_from(state)
    name = f"{u.mall} {u.unit_no}" if u else ""
    if lang == "zh":
        s = (
            f"在{name}开业，预计{{{{fig:plan.open_likely}}}}；情况不理想时{{{{fig:plan.open_p95}}}}。"
            f"每月储蓄{{{{fig:plan.setaside_monthly}}}}。"
        )
        assumptions = ["利润按你近期的季节规律估算", "成本按成本卡中的范围", "汇率与办理时间为注明日期的参数"]
    else:
        s = (
            f"Open at {name} around {{{{fig:plan.open_likely}}}}; "
            f"if things go badly, by {{{{fig:plan.open_p95}}}}. "
            f"Set aside {{{{fig:plan.setaside_monthly}}}} a month."
        )
        assumptions = [
            "Profit follows your recent seasonal pattern",
            "Costs within the cost card's range",
            "FX and processing times are dated parameters",
        ]
    return figs, s, ["plan.open_likely", "plan.open_p95", "plan.setaside_monthly"], assumptions


def goal_payload(state: JourneyState) -> dict[str, Any]:
    """Canonical content an approval card covers. Rebuilt from current state at approval."""
    assert state.funding is not None and state.cost_card is not None and state.plan is not None
    return {
        "unit": state.shortlist.chosen_unit_id,
        "cost_total_likely_sgd": str(state.cost_card.total_likely_sgd),
        "setaside_share": str(state.funding.setaside_share),
        "setaside_monthly_cny": str(state.plan.monthly_setaside_cny),
        "own_savings_cny": str(state.funding.own_savings_cny),
        "rent_free_months": str(state.funding.rent_free_months),
        "partner_equity_share": str(state.funding.partner_equity_share),
        "open_likely_week": state.plan.open_likely_week,
        "open_p95_week": state.plan.open_p95_week,
        "floor_cny": str(state.funding.floor_cny),
        "spare_cash_cny": str(spare_cash_used(state)),
        "prefs": {k: state.goal_prefs.get(k) for k in sorted(state.goal_prefs)},
        "plan_seed": state.plan.seed,
    }


def approval_lines(state: JourneyState, t: Turn) -> list[dict[str, str]]:
    from agent.render import fmt_figure

    zh = t.lang == "zh"
    assert state.plan is not None and state.cost_card is not None and state.funding is not None
    figs = {f.id: f for f in PL.plan_figures(state.plan)}
    figs |= {f.id: f for f in C.cost_figures(state.cost_card, t.lang)}
    mix_res = F.funding_mix(state.funding, state.cost_card, state.plan, source_for(state), t.lang)
    figs |= {p.amount.id: p.amount for p in mix_res.parts}
    savings = state.funding.own_savings_cny
    if savings > 0:
        figs["funding.own_savings"] = derived(
            "funding.own_savings", "Own savings committed", "CNY", savings, tool="funding_plan"
        )

    def disp(fid: str) -> str:
        return fmt_figure(figs[fid], t.lang, state.start_date)

    u = _unit_from(state)
    sep = "；" if zh else " · "
    lines = [
        {"label": "铺位" if zh else "Unit", "value": f"{u.mall} {u.unit_no}" if u else ""},
        {
            "label": "预计总成本" if zh else "Total likely cost",
            "value": f"{disp('cost.total.likely_sgd')}（{disp('cost.total.likely_cny')}）"
            if zh
            else f"{disp('cost.total.likely_sgd')} ({disp('cost.total.likely_cny')})",
        },
    ]
    if savings > 0:
        lines.append(
            {
                "label": "投入的个人储蓄" if zh else "Own savings committed",
                "value": disp("funding.own_savings"),
            }
        )
    lines += [
        {
            "label": "资金来源" if zh else "Funding mix",
            "value": sep.join(f"{p.label} {disp(p.amount.id)}" for p in mix_res.parts),
        },
        {"label": "预计开业" if zh else "Likely opening", "value": disp("plan.open_likely")},
        {"label": "情况不理想时" if zh else "If things go badly", "value": disp("plan.open_p95")},
        {"label": "每月储蓄" if zh else "Monthly set-aside", "value": disp("plan.setaside_monthly")},
        {
            "label": "国内现金跌破底线的概率" if zh else "Chance home cash dips below the floor",
            "value": disp("plan.floor_risk"),
        },
        {
            "label": "提醒频率" if zh else "Check-ins",
            "value": {o.value: o.label for o in O.frequency(t.lang)}.get(
                str(state.goal_prefs.get("checkin_frequency", "monthly")), ""
            ),
        },
    ]
    if state.goal_prefs.get("recurring_setaside"):
        lines.append(
            {
                "label": "自动储蓄" if zh else "Monthly transfer",
                "value": "转入公司名下储蓄子账户（在微众银行签署确认）"
                if zh
                else "Into your company's own savings sub-account (you sign in WeBank)",
            }
        )
    lines += [ln.model_dump() for ln in unverified_lines(state.profile, t.lang)]
    lines.append(
        {
            "label": "注意" if zh else "Note",
            "value": "Waypoint 不会移动任何资金" if zh else "Waypoint never moves money",
        }
    )
    return lines


def milestone_detail(t: Turn, mid: str) -> None:
    """A tapped step: what it involves, plus its draft (lender consent) or checklist (ODI filing,
    incorporation) and, when code allows it now, a way to mark it done (SPEC §7.4)."""
    from agent import drafts

    st = t.state
    known = {d["id"] for d in P.items("timeline_milestones")}
    if mid not in known:
        t.mark("ignored_event", reason="unknown_milestone")
        return
    t.say(
        "answer_question",
        skill="journey",
        facts={
            "question": f"What does the step '{milestone_label(mid, 'en')}' involve, who does it, and what should I prepare?"  # noqa: E501
        },
    )
    sk = t.skills["goal-keeper"]
    if mid == "lender_consent" and st.goal_id:
        figs, card = t.call("drafts.consent_request", t.services.consent_draft, st, t.lang, skill=sk)
        t.add(*figs)
        t.say("consent_draft_intro", skill="goal-keeper")
        wid = t.show(card, skill=sk)
        t.say("consent_letter", skill="goal-keeper", into=wid)
    else:
        card = t.call("drafts.checklist", drafts.checklist, mid, t.lang, skill=sk)
        if card is not None:
            t.say("checklist_intro", skill="goal-keeper", vars={"step": milestone_label(mid, t.lang)})
            t.show(card, skill=sk)


# ------------------------------------------------------------------ Goal Keeper helpers


def goal_signals(
    state: JourneyState, goal: Any, today: date, owner_numbers: dict[str, Decimal] | None
) -> dict[str, Any]:
    """What the weekly check knows today: profit, money saved, R2, and whether a real drop is detected."""
    from mock_webank import feed as mw
    from tools import detect as DT

    out: dict[str, Any] = {
        "r2": False,
        "drop": False,
        "channel_shift": False,
        "profit_cny": None,
        "set_aside_cny": None,
        "loan_cny": None,
        "ratio": None,
    }
    if state.consent_feed:
        at_start = mw.get_feed(state.owner_id, goal.start_date)
        now = mw.get_feed(state.owner_id, today)
        checks = DT.check_weeks(now, DT.baseline(at_start, goal.start_date))
        det = DT.cusum(checks)
        out.update(
            r2=F.r2_paused(now),
            drop=det.alarm,
            channel_shift=det.channel_shift_weeks > 0 and not det.alarm,
            loan_cny=now.loan_balance_cny,
            ratio=DT.mean_ratio(checks),  # every week since the start, not the alarm's own (low) window
            feed_now=now,
            since=goal.start_date,
        )
        last = [w for w in now.weekly_profit if not w.feed_missing][-4:]
        out["profit_cny"] = (
            sum((w.operating_profit_cny for w in last), Decimal(0))
            * Decimal(str(P.fnum("weeks_per_month") / 4))
            if last
            else None
        )
        out["saved_cny"] = now.pot_balance_cny if now.pot_balance_cny is not None else Decimal(0)
        return out
    # standalone: the owner's check-ins
    from app.store import Store  # noqa: F401  (type only)

    prev = Decimal(str(goal.funding.own_savings_cny))
    saved = (state.profile.spare_cash_cny or Decimal(0)) + prev
    if owner_numbers:
        out["profit_cny"] = owner_numbers.get("profit_cny")
        out["set_aside_cny"] = owner_numbers.get("set_aside_cny")
        expected = goal.setaside_monthly_cny
        got = owner_numbers.get("set_aside_cny")
        if got is not None and expected and got < expected * Decimal("0.8"):
            out["drop"] = True
            out["ratio"] = float(got / expected) if expected else None
        saved += got or Decimal(0)
    out["saved_cny"] = saved
    return out


def replan_source(state: JourneyState, signals: dict[str, Any]) -> FeedSnapshot | Profile:
    from tools import detect as DT

    now = signals.get("feed_now")
    if now is None:
        p = state.profile.model_copy(deep=True)
        if signals.get("drop") and signals.get("ratio") and p.monthly_profit_cny is not None:
            w = P.fnum("detect_persist_weight")
            r = Decimal(str(round(1.0 - w * (1.0 - float(signals["ratio"])), 4)))
            p.monthly_profit_cny = p.monthly_profit_cny.model_copy(
                update={"low": p.monthly_profit_cny.low * r, "high": p.monthly_profit_cny.high * r}
            )
        return p
    if signals.get("drop") and signals.get("ratio") and P.param("shock_persist_assume").value:
        w = P.fnum("detect_persist_weight")
        return DT.scaled_feed(now, 1.0 - w * (1.0 - float(signals["ratio"])), before=signals.get("since"))
    return now  # type: ignore[no-any-return]


def simulate_from(state: JourneyState, src: FeedSnapshot | Profile) -> PlanResult:
    assert state.cost_card is not None and state.funding is not None
    u = _unit_from(state)
    return PL.simulate_plan(
        src,
        state.cost_card,
        state.funding,
        start_date=state.start_date,
        unit_available_from=u.available_from if u else None,
    )


def find_repairs(state: JourneyState, src: FeedSnapshot | Profile) -> list[Any]:
    from tools import repairs as RP

    assert state.cost_card is not None and state.funding is not None
    u = _unit_from(state)
    alts = []
    for uid in state.shortlist.unit_ids:
        if uid != state.shortlist.chosen_unit_id:
            alts.append(
                C.estimate_costs(
                    unit(uid), state.profile, state.cost_card.fitout_level, state.cost_card.manager_plan
                )
            )
    avail = u.available_from if u else None
    # If the shock pushed the floor risk over the limit, every fix starts from a share back under the wall.
    wall_now = PL.find_wall(
        PL.build_inputs(src, state.cost_card, state.funding, state.start_date, unit_available_from=avail)
    )
    safe = state.funding.model_copy(update={"setaside_share": min(state.funding.setaside_share, wall_now)})
    reps = RP.find_repairs(
        src,
        state.cost_card,
        safe,
        alternatives=alts,
        start_date=state.start_date,
        unit_available_from=avail,
        feed=src if isinstance(src, FeedSnapshot) else None,
    )
    if safe.setaside_share != state.funding.setaside_share:
        reps = [
            r.model_copy(update={"params": {"setaside_share": str(safe.setaside_share), **r.params}})
            for r in reps
        ]
    return reps


def repair_text(r: Any, lang: Lang) -> tuple[str, str]:
    zh = lang == "zh"
    k, prm = r.kind, r.params
    if k == "raise_share":
        pct = f"{Decimal(prm['setaside_share']) * 100:.0f}%"
        return ("提高储蓄比例" if zh else "Set aside a bit more", f"{pct}")
    if k == "add_savings":
        return (
            "加入个人积蓄" if zh else "Add some of your savings",
            money(Decimal(prm["added_cny"]), "CNY", lang),
        )
    if k == "cheaper_unit":
        u = unit(prm["unit_id"])
        return ("换一个更便宜的铺位" if zh else "Pick the cheaper unit", f"{u.mall} {u.unit_no}")
    if k == "rent_free":
        return (
            "争取更多免租装修期" if zh else "Ask for more rent-free months",
            f"{prm['rent_free_months']}个月" if zh else f"{prm['rent_free_months']} months",
        )
    if k == "stage_contractor":
        return (
            "与承包商约定分期付款" if zh else "Stage the contractor's payments",
            "按进度付款" if zh else "Pay as work progresses",
        )
    if "setaside_share" in prm:
        pct = f"{Decimal(prm['setaside_share']) * 100:.0f}%"
        return (
            "降低储蓄比例并推迟日期" if zh else "Ease the set-aside and move the date",
            f"储蓄比例{pct}，保护门店现金" if zh else f"Set aside {pct} to keep home cash safe",
        )
    return (
        "推迟目标日期" if zh else "Move the target date",
        "按新的预计时间" if zh else "To the new likely date",
    )


def apply_repair(state: JourneyState, r: Any) -> None:
    assert state.funding is not None
    k, prm = r.kind, r.params
    if "setaside_share" in prm:
        state.funding.setaside_share = Decimal(prm["setaside_share"])
    if k == "raise_share":
        pass
    elif k == "add_savings":
        state.funding.own_savings_cny = Decimal(prm["own_savings_cny"])
    elif k == "cheaper_unit":
        state.shortlist.chosen_unit_id = prm["unit_id"]
        assert state.cost_card is not None
        state.cost_card = C.estimate_costs(
            unit(prm["unit_id"]), state.profile, state.cost_card.fitout_level, state.cost_card.manager_plan
        )
    elif k == "rent_free":
        state.funding.rent_free_months = Decimal(prm["rent_free_months"])
    elif k == "stage_contractor":
        state.funding.staged_contractor = True


def goal_text(goal: Any, lang: Lang, figs: dict[str, Figure] | None, amounts: bool = True) -> str:

    u = unit(goal.unit_id)
    name = f"{u.mall} {u.unit_no}"
    likely = month_label(goal.start_date, goal.target_open_likely_week, lang)
    p95 = month_label(goal.start_date, goal.target_open_p95_week, lang)
    amt = money(goal.setaside_monthly_cny, "CNY", lang)
    if lang == "zh":
        s = f"在{name}开业，预计{likely}（情况不理想时{p95}）"
        return s + (f"，每月储蓄{amt}。" if amounts else "。")
    s = f"Open at {name} around {likely} (by {p95} if things go badly)"
    return s + (f", setting aside {amt} a month." if amounts else ".")


def timeline_for_goal(
    goal: Any, elapsed: int, lang: Lang, interactive: bool = True
) -> tuple[list[Figure], MilestoneTimeline]:
    """The goal's timeline with done steps ticked. In the chat (`interactive`), each step the owner
    may mark done now (legal order, checked by code) carries `can_mark_done`."""
    from tools import timeline as TL

    figs, items = [], []
    for m in goal.milestones:
        fid = f"ms.{m.id}.likely"
        figs.append(derived(fid, milestone_label(m.id, lang), "weeks", m.likely_week, tool="timeline"))
        status = m.status.value if m.status.value == "done" else TL.milestone_status(m, elapsed).value
        en, zh = WHO.get(m.id, ("", ""))
        items.append(
            TimelineItem(
                done_date=(
                    (f"{m.done_at.year}年{m.done_at.month}月{m.done_at.day}日" if lang == "zh" else f"{m.done_at.day} {m.done_at:%b %Y}")  # noqa: E501
                    if m.done_at is not None
                    else None
                ),
                can_mark_done=interactive and TL.can_mark_done(goal.milestones, m.id)[0],
                money_step=TL.is_money_step(m.id),
                id=m.id,
                order=m.order,
                label=milestone_label(m.id, lang),
                who=zh if lang == "zh" else en,
                likely=fid,
                likely_date=month_label(goal.start_date, m.likely_week, lang),
                latest_safe_date=month_label(goal.start_date, m.latest_safe_week, lang),
                act_by_date=month_label(goal.start_date, m.act_by_week, lang),
                status=status,
            )
        )
    return figs, MilestoneTimeline(start_date=goal.start_date.isoformat(), items=items, step="goal_keeper")


def plan_summaries(
    goal: Any, snap: dict[str, Any], res: PlanResult, lang: Lang
) -> list[tuple[str, Any, list[Figure]]]:
    from agent.widgets import PlanSummary

    zh = lang == "zh"
    out: list[tuple[str, Any, list[Figure]]] = []
    u = unit(goal.unit_id)
    profile = Profile.model_validate(snap.get("profile") or {})
    ufigs, _row = unit_row(u, profile, lang)
    by = {f.id: f for f in ufigs}
    from agent.render import fmt_figure

    def d(fid: str) -> str:
        return fmt_figure(by[fid], lang, goal.start_date) if fid in by else ""

    site_lines = [
        ApprovalLine(label="铺位" if zh else "Unit", value=f"{u.mall} {u.unit_no}"),
        ApprovalLine(label="区域" if zh else "Area", value=area_names().get(u.area_id, u.area_id)),
        ApprovalLine(
            label="面积" if zh else "Size", value=f"{u.size_sqft:,}" + ("平方英尺" if zh else " sq ft")
        ),
        ApprovalLine(
            label="月租（含服务费）" if zh else "Rent with service charge", value=d(f"unit.{u.id}.rent_total")
        ),
        ApprovalLine(label="保本杯量" if zh else "Break-even", value=d(f"unit.{u.id}.breakeven")),
    ]
    out.append(
        (
            "site",
            PlanSummary(
                kind="site",
                title="开在哪里" if zh else "Where",
                lines=site_lines,
                figures=list(by),
                reopen_step="site",
            ),
            ufigs,
        )
    )
    card_raw = snap.get("cost_card")
    if card_raw:
        card = CostCard.model_validate(card_raw)
        cfigs = C.cost_figures(card, lang)
        cb = {f.id: f for f in cfigs}
        lines = [
            ApprovalLine(
                label=(zh and GROUP_LABELS[g][1]) or GROUP_LABELS[g][0],
                value=fmt_figure(cb[f"cost.group.{g}.likely"], lang),
            )
            for g in card.by_group()
            if f"cost.group.{g}.likely" in cb
        ]
        lines.append(
            ApprovalLine(
                label="预计总额" if zh else "Likely total",
                value=fmt_figure(cb["cost.total.likely_sgd"], lang),
            )
        )
        lines.append(
            ApprovalLine(
                label="情况不理想时" if zh else "If things go badly",
                value=fmt_figure(cb["cost.total.bad_sgd"], lang),
            )
        )
        out.append(
            (
                "cost",
                PlanSummary(
                    kind="cost",
                    title="要花多少" if zh else "What it costs",
                    lines=lines,
                    figures=["cost.total.likely_sgd", "cost.total.bad_sgd"],
                    reopen_step="cost",
                ),
                cfigs,
            )
        )
    pf = PL.plan_figures(res)
    pb = {f.id: f for f in pf}
    fund_lines = [
        ApprovalLine(
            label="储蓄比例" if zh else "Share of profit set aside",
            value=fmt_figure(pb["plan.setaside_share"], lang),
        ),
        ApprovalLine(
            label="每月储蓄" if zh else "Monthly set-aside",
            value=fmt_figure(pb["plan.setaside_monthly"], lang),
        ),
        ApprovalLine(
            label="跌破安全线概率" if zh else "Chance of dipping below your safety line",
            value=fmt_figure(pb["plan.floor_risk"], lang),
        ),
    ]
    if goal.funding.own_savings_cny:
        fund_lines.append(
            ApprovalLine(
                label="个人积蓄" if zh else "Own savings",
                value=money(goal.funding.own_savings_cny, "CNY", lang),
            )
        )
    if goal.funding.rent_free_months:
        fund_lines.append(
            ApprovalLine(
                label="免租装修期" if zh else "Rent-free months",
                value=f"{goal.funding.rent_free_months.normalize():f}",
            )
        )
    out.append(
        (
            "funding",
            PlanSummary(
                kind="funding",
                title="怎么筹钱" if zh else "How it's paid for",
                lines=fund_lines,
                figures=["plan.setaside_monthly", "plan.floor_risk"],
                reopen_step="funding",
            ),
            pf,
        )
    )
    return out


# ------------------------------------------------------------------ unit economics (tools/unit_econ.py)

_ECON_LABELS: dict[str, tuple[str, str]] = {
    "econ.breakeven": ("Break-even (a month's EBITDA is zero)", "保本杯量（月EBITDA为零）"),
    "econ.cups_needed_likely": ("To pay back within the lease", "租约内收回投资所需"),
    "econ.cups_needed_bad": ("To pay back within the lease, if things go badly", "情况不理想时租约内收回所需"),  # noqa: E501
    "econ.cups_needed_price_low": ("At the lower menu price", "按较低售价"),
    "econ.cups_needed_price_high": ("At the higher menu price", "按较高售价"),
    "econ.price_low": ("Lower menu price", "较低售价"),
    "econ.price_high": ("Higher menu price", "较高售价"),
    "profile.best_shop_cups": ("Your best shop at home", "您国内最好的门店"),
    "econ.price": ("Menu price", "售价"),
    "econ.var_cost": ("Ingredients and packaging, with GST", "原料和包装（含消费税）"),
    "econ.delivery_cost": ("Delivery commission (averaged over every cup)", "外卖平台佣金（摊到每杯）"),
    "econ.contribution": ("Contribution a cup", "每杯边际贡献"),
    "econ.fixed.wages": ("Wages with CPF", "工资（含公积金）"),
    "econ.fixed.rent": ("Rent and service charge", "租金和服务费"),
    "econ.fixed.running": ("Utilities and other running costs", "水电和其他运营费用"),
    "econ.fixed.gst": ("GST on rent and running costs (a cost while unregistered)", "租金和运营费用的消费税（未注册时为成本）"),  # noqa: E501
    "econ.fixed": ("Fixed costs a month", "每月固定成本"),
    "econ.card_total": ("Opening cost, likely", "开店成本（预计）"),
    "econ.reserve": ("Less the running reserve (it pays for the ramp-up months)", "减去运营备用金（用于爬坡期）"),  # noqa: E501
    "econ.investment_likely": ("Investment, likely", "投资额（预计）"),
    "econ.investment_bad": ("Investment if things go badly (P90 cost)", "情况不理想时的投资额（P90成本）"),
}
_PNL_FIELDS = ("revenue", "ebitda", "margin", "depreciation", "tax", "net",
               "payback_likely", "payback_bad", "npv", "npv_bad")
_ESTIMATE_IDS = {"econ.cups_needed_likely", "econ.cups_needed_bad", "econ.cups_needed_price_low",
                 "econ.cups_needed_price_high", "econ.delivery_cost"}
_ECON_NOTES: tuple[tuple[str, str], ...] = (
    ("Not GST-registered at first: the whole menu price is revenue, and the GST paid on ingredients, rent, "
     "running costs and commissions is a cost. A level whose yearly sales pass the compulsory-registration "
     "threshold is treated as registered (marked).",
     "开业初期未注册消费税：售价全部计入收入，原料、租金、运营费用和佣金上的消费税是成本。年销售额超过强制注册门槛的档位按已注册计算（已标出）。"),
    ("Tax: Singapore corporate income tax with partial exemption only. The start-up exemption doesn't apply: "
     "a company wholly owned by a foreign company doesn't qualify.",
     "税：新加坡企业所得税，只用部分免税。新公司免税计划不适用：由外国公司全资持有的公司不符合条件。"),
    ("Investment is the opening cost less the running reserve: the ramp-up months the reserve pays for are "
     "already in the monthly cash. Payback is the first month the cash after tax has paid the investment back.",  # noqa: E501
     "投资额 = 开店成本减去运营备用金：备用金覆盖的爬坡期已计入每月现金流。回收期为税后现金累计收回投资的第一个月。"),  # noqa: E501
    ("Estimates: the ramp-up curve and the share of cups sold through delivery apps are build-team "
     "assumptions. 'If things go badly' uses the P90 opening cost and a slower ramp-up.",
     "估计：爬坡曲线和外卖占比是项目团队的假设。“情况不理想时”使用P90开店成本和较慢的爬坡。"),
)


def _econ_line(fid: str, by: dict[str, Figure], lang: Lang) -> EconLine | None:
    if fid not in by:
        return None
    en, zh = _ECON_LABELS.get(fid, (by[fid].label, by[fid].label))
    return EconLine(key=fid, label=zh if lang == "zh" else en, figure=fid, estimate=fid in _ESTIMATE_IDS)


def _best_shop_fig(p: Profile) -> Figure | None:
    from tools.figtools import sourced
    from tools.figures import Source, SourceKind

    if p.best_shop_cups_per_day is None:
        return None
    kind = SourceKind.FEED if p.sources.get("best_shop_cups_per_day") == "feed" else SourceKind.OWNER
    return sourced("profile.best_shop_cups", "Your best shop", "cups_per_day", p.best_shop_cups_per_day,
                   Source(kind=kind, ref="best_shop_cups_per_day"))


def unit_economics(
    u: Unit, card: CostCard, p: Profile, lang: Lang, editable: bool = True, fs: FeedSnapshot | None = None
) -> tuple[list[Figure], UnitEconomics, UE.Card]:
    """The unit-economics card for the chosen unit and its cost card (the owner's own figure if given), and,
    with the feed, the shop against the chain."""
    econ = UE.unit_economics(u, card, card.manager_plan, p.expected_sg_cups_per_day, _best_shop_fig(p))
    chain_figs = singapore_glance_figs(fs, econ) if fs is not None else []
    figs = econ.figures + chain_figs
    by = {f.id: f for f in figs}
    zh = lang == "zh"

    def lines(ids: list[str]) -> list[EconLine]:
        return [x for x in (_econ_line(i, by, lang) for i in ids) if x is not None]

    n = UE.lease_months(u)
    rows = [
        PnlRow(key=lv.key, cups=f"lvl.{lv.key}.cups", owner=lv.owner, registered=lv.registered,
               **{k: f"lvl.{lv.key}.{k}" for k in _PNL_FIELDS})
        for lv in econ.levels
    ]
    sens: list[EconLine] = []
    rate = P.fnum("discount_rate_annual")
    ref_npv = f"lvl.{econ.reference}.npv"
    for r_ in sorted([rate, *(float(x) for x in P.items("discount_rate_sensitivity"))]):
        fid = ref_npv if r_ == rate else f"econ.npv_at_{round(r_ * 100)}"
        pct = f"{r_:.0%}"
        sens.append(EconLine(key=f"npv_{round(r_ * 100)}", figure=fid, estimate=True,
                             label=f"{n}个月净现值，折现率{pct}" if zh else f"NPV over {n} months at {pct}"))
    sens += lines(
        ["econ.price_low", "econ.cups_needed_price_low", "econ.price_high", "econ.cups_needed_price_high"]
    )
    bench = [
        Benchmark(label=bzh if zh else ben, figure=fid,
                  source=SourceNote(label=f"{'港交所招股书' if zh else 'HKEX prospectus'} p.{page}" if page
                                    else ("港交所招股书" if zh else "HKEX prospectus"),
                                    url=by[fid].source.url, as_of=str(P.param("chain_benchmarks").as_of)))
        for fid, ben, bzh, page in econ.benchmarks
    ]
    payload = UnitEconomics(
        unit_id=u.id,
        unit_name=f"{u.mall} {u.unit_no}",
        headline=lines(["econ.breakeven", "econ.cups_needed_likely", "econ.cups_needed_bad",
                        "econ.cups_needed_price_low", "profile.best_shop_cups"]),
        per_cup=lines(["econ.price", "econ.var_cost", "econ.delivery_cost", "econ.contribution"]),
        fixed=lines(
            ["econ.fixed.wages", "econ.fixed.rent", "econ.fixed.running", "econ.fixed.gst", "econ.fixed"]
        ),
        investment=lines(
            ["econ.card_total", "econ.reserve", "econ.investment_likely", "econ.investment_bad"]
        ),
        rows=rows,
        sensitivity=sens,
        ramp_likely=econ.ramp_likely,
        ramp_bad=econ.ramp_bad,
        benchmarks=bench,
        chain=_ratio_rows(_SG_ROWS, {f.id for f in chain_figs}, lang),
        notes=[zh_ if zh else en for en, zh_ in _ECON_NOTES],
        owner_cups=p.expected_sg_cups_per_day,
        editable=editable,
    )
    return figs, payload, econ


def set_owner_cups(p: Profile, value: object) -> bool:
    """The owner's own cups-a-day figure for the Singapore shop (a whole number, 1 to the search top)."""
    try:
        n = int(str(value).strip())
    except ValueError:
        return False
    if not 0 < n <= int(P.table("econ_cups_search")["high"]):
        return False
    p.expected_sg_cups_per_day = n
    p.sources["expected_sg_cups_per_day"] = "owner"
    return True


def singapore_glance_figs(fs: FeedSnapshot, econ: UE.Card) -> list[Figure]:
    by = {f.id: f for f in econ.figures}
    inv_l, inv_b = by["econ.investment_likely"], by["econ.investment_bad"]
    return R.singapore_ratios(fs, inv_l, inv_b, UE.reference_ebitda(econ))


def goal_analysis(
    state: JourneyState, snap: dict[str, Any], lang: Lang, today: date
) -> list[tuple[Any, list[Figure]]]:
    """The Goal tab's analysis cards: the business at a glance from today's feed (with consent only, with the
    Singapore shop against the chain), and the chosen unit's economics (read-only)."""
    from mock_webank import feed as mw

    out: list[tuple[Any, list[Figure]]] = []
    econ: UE.Card | None = None
    card_raw, uid = snap.get("cost_card"), snap.get("unit_id")
    if card_raw and uid:
        card = CostCard.model_validate(card_raw)
        prof = Profile.model_validate(snap.get("profile") or {})
        efigs, payload, econ = unit_economics(unit(str(uid)), card, prof, lang, editable=False)
        out.append((payload, efigs))
    if snap.get("consent_feed") or state.consent_feed:
        fs = mw.get_feed(state.owner_id, today)
        figs, glance = business_glance(fs, lang, singapore_glance_figs(fs, econ) if econ else None)
        out.insert(0, (glance, figs))
    return out


def planned_profit_series(goal: Any, n: int) -> list[float]:
    """Expected weekly operating profit (the plan's seasonal model), for the plan-vs-actual chart."""
    from tools.figures import dec  # noqa: F401

    monthly = (
        float(goal.setaside_monthly_cny / goal.funding.setaside_share) if goal.funding.setaside_share else 0.0
    )
    wpm = P.fnum("weeks_per_month")
    return [round(monthly / wpm, 2)] * n
