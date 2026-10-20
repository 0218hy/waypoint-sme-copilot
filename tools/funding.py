"""Funding tools (SPEC §6.4, §6.5): floor and buffer, spare cash, the gap, options, closed routes, mix."""

from __future__ import annotations

import dataclasses
import math
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from tools import params as P
from tools.data import CatalogueEntry, load_catalogue, load_rules_yaml
from tools.figtools import derived, sourced
from tools.figures import Figure, Source, SourceKind, q0
from tools.models import CostCard, FeedSnapshot, FundingOption, FundingPlan, PlanResult, Profile

if TYPE_CHECKING:
    from tools.plan import PlanInputs

TOOL = "funding"
Src = FeedSnapshot | Profile


class FloorResult(BaseModel):
    floor_cny: Decimal
    buffer_cny: Decimal
    payroll_monthly_cny: Decimal
    payroll_estimated: bool
    repayments_known: bool
    figures: list[Figure]


class FundingOptionResult(BaseModel):
    option: FundingOption
    amount: Figure | None = None


class ClosedRouteView(BaseModel):
    id: str
    label: str
    rule_id: str
    reason: str
    source: str
    source_url: str | None = None
    source_kind: Literal["law", "design", "law+design"] | None = None


class MixPart(BaseModel):
    key: str
    label: str
    amount: Figure


class RankedRoute(BaseModel):
    """A plan route's place for this owner: open to them or not yet (and why), and, when ranked, its words and
    the measure behind each word. Never a score: the order and the words are all the owner sees."""

    id: str
    eligible: bool
    ranked: bool = False  # False for `timing` routes and for routes not open to this owner yet
    words: list[str] = []
    why_not: str | None = None  # the catalogue's `eligible_when_*` text, when not open yet
    cost: Figure | None = None  # share of the Singapore profit given up (0 for own cash and landlord terms)
    weeks: Figure | None = None  # weeks from the plan start until the route's money is in hand
    dilution: Figure | None = None  # share of the Singapore company given up
    floor_change: Figure | None = None  # floor risk with the route minus without it, on the same runs


class MixResult(BaseModel):
    total: Figure
    parts: list[MixPart]
    setaside_months: Figure | None = None


# ------------------------------------------------------------------ helpers


def _feed_source(feed: FeedSnapshot, ref: str) -> Source:
    return Source(
        kind=SourceKind.FEED,
        ref=f"webank_feed:{ref}",
        as_of=feed.as_of,
        note="simulated feed" if feed.simulated else None,
    )


def _owner_source(ref: str) -> Source:
    return Source(kind=SourceKind.OWNER, ref=ref)


def average_monthly_profit(src: Src) -> Decimal | None:
    if isinstance(src, FeedSnapshot):
        hist = src.profit_history[-12:]
        if not hist:
            return None
        return sum((m.operating_profit_cny for m in hist), Decimal(0)) / len(hist)
    return None if src.monthly_profit_cny is None else src.monthly_profit_cny.mid


def _payroll(src: Src) -> tuple[Decimal | None, bool]:
    if src.monthly_payroll_cny is not None:
        return src.monthly_payroll_cny, False
    profit = average_monthly_profit(src)
    if profit is None:
        return None, False
    return q0(profit * P.num("payroll_to_profit_ratio_default")), True


# ------------------------------------------------------------------ floor, buffer, spare cash (§6.5)


def safety_floor(src: Src) -> FloorResult | None:
    """Floor = 8 weeks of payroll + the next 2 loan repayments; buffer = 4 weeks of payroll."""
    payroll, estimated = _payroll(src)
    if payroll is None:
        return None
    wpm = P.num("weeks_per_month")
    repay = src.monthly_loan_repayment_cny
    repay_part = Decimal(0) if repay is None else repay * P.num("floor_loan_repayments")
    floor = q0(payroll / wpm * P.num("floor_payroll_weeks") + repay_part)
    buffer = q0(payroll / wpm * P.num("buffer_payroll_weeks"))
    if isinstance(src, FeedSnapshot):
        pay_src = _feed_source(src, "payroll")
    else:
        pay_src = (
            _owner_source("monthly_payroll_cny")
            if not estimated
            else Source(
                kind=SourceKind.PARAM, ref="payroll_to_profit_ratio_default", note="estimated from profit"
            )
        )
    pay_fig = sourced("home.payroll_monthly", "Monthly payroll", "CNY", payroll, pay_src)
    note = None if repay is not None else "Loan repayments unknown: not included yet"
    figs = [
        pay_fig,
        derived(
            "home.floor",
            "Safety floor",
            "CNY",
            floor,
            tool="safety_floor",
            inputs=[pay_fig],
            assumptions=("floor_payroll_weeks", "floor_loan_repayments", "weeks_per_month"),
            note=note,
        ),
        derived(
            "home.buffer",
            "Payroll buffer",
            "CNY",
            buffer,
            tool="safety_floor",
            inputs=[pay_fig],
            assumptions=("buffer_payroll_weeks", "weeks_per_month"),
        ),
    ]
    return FloorResult(
        floor_cny=floor,
        buffer_cny=buffer,
        payroll_monthly_cny=payroll,
        payroll_estimated=estimated,
        repayments_known=repay is not None,
        figures=figs,
    )


def spare_cash(src: Src) -> Figure:
    """Cash above floor + buffer (never negative). Missing when it can't be computed (missing != zero)."""
    fl = safety_floor(src)
    if isinstance(src, FeedSnapshot):
        if fl is None:
            return derived("home.spare_cash", "Spare cash", "CNY", None, tool="spare_cash")
        cash = sourced("home.cash", "Cash balance", "CNY", src.cash_balance_cny, _feed_source(src, "cash"))
        val = max(src.cash_balance_cny - fl.floor_cny - fl.buffer_cny, Decimal(0))
        if src.owner_spare_cash_cny is not None and src.owner_spare_cash_cny < val:
            # never more than the bank data shows; less when the owner says some of it is spoken for
            return sourced(
                "home.spare_cash", "Spare cash", "CNY", src.owner_spare_cash_cny,
                _owner_source("spare_cash_cny"),
            )
        return derived(
            "home.spare_cash",
            "Spare cash",
            "CNY",
            val,
            tool="spare_cash",
            inputs=[cash, *fl.figures],
            assumptions=("floor_payroll_weeks", "buffer_payroll_weeks"),
        )
    if src.spare_cash_cny is not None:
        return sourced(
            "home.spare_cash", "Spare cash", "CNY", src.spare_cash_cny, _owner_source("spare_cash_cny")
        )
    if src.cash_balance_cny is not None and fl is not None:
        cash = sourced(
            "home.cash", "Cash balance", "CNY", src.cash_balance_cny, _owner_source("cash_balance_cny")
        )
        val = max(src.cash_balance_cny - fl.floor_cny - fl.buffer_cny, Decimal(0))
        return derived(
            "home.spare_cash", "Spare cash", "CNY", val, tool="spare_cash", inputs=[cash, *fl.figures]
        )
    return derived("home.spare_cash", "Spare cash", "CNY", None, tool="spare_cash")


def loan_excess_cny(feed: FeedSnapshot) -> Decimal:
    """How far WeBank borrowing is above the owner's own normal level for this calendar month."""
    normal = feed.normal_loan_balance_by_month_cny.get(feed.as_of.month)
    if normal is None:
        return Decimal(0)
    return max(feed.loan_balance_cny - normal, Decimal(0))


def r2_paused(feed: FeedSnapshot) -> bool:
    """R2: set-asides and transfers pause while borrowing is above normal (beyond the tolerance)."""
    return loan_excess_cny(feed) > P.num("r2_tolerance_cny")


# ------------------------------------------------------------------ gap and options (§6.4)


def funding_gap(card: CostCard, spare: Figure, cost_figs: list[Figure] | None = None) -> Figure:
    """Gap = the cost needed by opening (likely, RMB at the dated FX) − spare cash. Missing if spare is."""
    need = card.total_likely_sgd * card.fx_cny_per_sgd
    ins = [spare] + [f for f in (cost_figs or []) if f.id == "cost.total.likely_cny"]
    if spare.value is None:
        return derived("funding.gap", "Funding gap", "CNY", None, tool="funding_gap", inputs=ins)
    return derived(
        "funding.gap",
        "Funding gap",
        "CNY",
        q0(max(need - spare.value, Decimal(0))),
        tool="funding_gap",
        inputs=ins,
        assumptions=("fx_cny_per_sgd",),
    )


def _amount(option_id: str, src: Src, card: CostCard, plan: FundingPlan, spare: Figure) -> Figure | None:
    fx = card.fx_cny_per_sgd
    total_cny = card.total_likely_sgd * fx
    fid = f"funding.option.{option_id}"
    if option_id == "spare_cash":
        return derived(fid, "Spare cash", "CNY", spare.value, tool=TOOL, inputs=[spare])
    if option_id == "setaside":
        prof = average_monthly_profit(src)
        val = None if prof is None else q0(prof * plan.setaside_share)
        return derived(fid, "Monthly set-aside", "CNY", val, tool=TOOL)
    if option_id == "own_savings":
        return derived(fid, "Own savings", "CNY", plan.own_savings_cny, tool=TOOL)
    if option_id == "landlord_terms" and card.rent_monthly_sgd is not None:
        val = q0(card.rent_monthly_sgd * plan.rent_free_months * (1 + P.num("gst_rate")) * fx)
        return derived(
            fid,
            "Rent saved by rent-free months",
            "CNY",
            val,
            tool=TOOL,
            assumptions=("gst_rate", "fx_cny_per_sgd"),
        )
    if option_id == "staged_contractor":
        fit = sum((ln.likely_sgd for ln in card.lines if ln.key == "fitout"), Decimal(0))
        val = q0(fit * (1 - P.num("staged_contractor_upfront_share")) * fx)
        return derived(
            fid,
            "Fit-out paid later in stages",
            "CNY",
            val,
            tool=TOOL,
            assumptions=("staged_contractor_upfront_share",),
        )
    if option_id == "pre_investment":
        return derived(
            fid,
            "前期费用 cap",
            "CNY",
            q0(total_cny * P.num("pre_investment_cap_share")),
            tool=TOOL,
            assumptions=("pre_investment_cap_share",),
        )
    if option_id == "partner_equity":
        return derived(fid, "Partner's share", "CNY", q0(total_cny * plan.partner_equity_share), tool=TOOL)
    return None


def _option(e: CatalogueEntry, lang: str, on: bool = False) -> FundingOption:
    note = None
    if e.note_rule is not None:
        note = load_rules_yaml()["rules"][e.note_rule]["message_zh" if lang == "zh" else "message_en"]
    product = e.product_zh if lang == "zh" else e.product_en
    return FundingOption(
        id=e.id,
        label=e.text("label", lang),
        status=e.status,
        covers=e.text("covers", lang),
        available_from=e.text("available_from", lang),
        cost=e.text("cost", lang),
        conditions=e.text("conditions", lang),
        rule_ids=e.rule_ids,
        on=on,
        source=e.source,
        source_url=e.source_url,
        source_kind=e.source_kind,
        card=e.card,
        as_of=e.as_of,
        subject_to_approval=e.subject_to_approval,
        product=product,
        product_url=e.product_url,
        note=note,
        note_rule=e.note_rule,
    )


def funding_options(
    src: Src, card: CostCard, plan: FundingPlan | None = None, lang: str = "en"
) -> list[FundingOptionResult]:
    """Open and optional plan routes as cards, each with what it covers, when, its cost, conditions and
    amount. Bank cards (`bank_cards`) are not plan routes and never appear here."""
    plan = plan or FundingPlan()
    spare = spare_cash(src)
    out: list[FundingOptionResult] = []
    for e in load_catalogue().options:
        if e.status == "closed" or not e.in_plan:
            continue
        on = (
            e.id in plan.options_on
            or e.id in ("spare_cash", "setaside")
            or (e.id == "own_savings" and plan.own_savings_cny > 0)
        )
        amount = _amount(e.id, src, card, plan, spare)
        out.append(FundingOptionResult(option=_option(e, lang, on), amount=amount))
    return out


def home_loan_headroom(src: Src) -> Figure | None:
    """WeBank working capital for home needs that keeps borrowing at or below the owner's usual level this
    month: the usual level minus the current balance, from the feed. None without a feed or when not below
    usual."""
    if not isinstance(src, FeedSnapshot):
        return None
    normal = src.normal_loan_balance_by_month_cny.get(src.as_of.month)
    if normal is None or src.loan_balance_cny >= normal:
        return None
    bal = sourced(
        "home.loan_balance", "WeBank loan balance", "CNY", src.loan_balance_cny, _feed_source(src, "loan")
    )
    usual = sourced(
        "home.loan_usual", "Usual WeBank borrowing this month", "CNY", normal, _feed_source(src, "loan_usual")
    )
    return derived(
        "funding.webank.home_headroom",
        "Room below your usual WeBank borrowing",
        "CNY",
        q0(normal - src.loan_balance_cny),
        tool="home_loan_headroom",
        inputs=[bal, usual],
    )


def bank_cards(src: Src, lang: str = "en") -> list[FundingOptionResult]:
    """What WeBank (and the bank that registers the ODI) say yes to around the plan: never counted in it.
    The home working-capital card shows only when the feed's balance is below the owner's usual level."""
    out: list[FundingOptionResult] = []
    for e in load_catalogue().options:
        if e.card not in ("webank", "partner_bank") or e.status == "closed":
            continue
        amount = None
        if e.id == "webank_home_wc":
            amount = home_loan_headroom(src)
            if amount is None:
                continue
        out.append(FundingOptionResult(option=_option(e, lang), amount=amount))
    return out


def later_cards(lang: str = "en") -> list[FundingOptionResult]:
    """What may come after opening (EFS, bank SME loans): a read-only view, never counted in the plan (R8)."""
    return [
        FundingOptionResult(option=_option(e, lang))
        for e in load_catalogue().options
        if e.card == "after_opening" and e.status == "later"
    ]


def webank_role(lang: str = "en") -> str:
    return load_catalogue().webank_role["zh" if lang == "zh" else "en"]


def closed_options(lang: str = "en") -> list[ClosedRouteView]:
    """Each closed route with the rule that closes it and the rule's source."""
    rules = load_rules_yaml()["rules"]
    out: list[ClosedRouteView] = []
    for e in load_catalogue().options:
        if e.status != "closed":
            continue
        rid = e.rule_ids[0]
        r = rules[rid]
        out.append(
            ClosedRouteView(
                id=e.id,
                label=e.text("label", lang),
                rule_id=rid,
                reason=r["message_zh" if lang == "zh" else "message_en"],
                source=r["source"],
                source_url=r.get("url"),
                source_kind=r.get("kind"),
            )
        )
    return out


# ------------------------------------------------------------------ eligibility and ranking (judge memo §1b)


def route_eligible(option_id: str, src: Src, card: CostCard, plan: FundingPlan, spare: Figure) -> bool:
    """Whether a plan route is open to this owner, from what Waypoint already knows: spare cash above zero; a
    profit to set aside from; savings the owner has put in; a partner the owner said they'd consider; a unit
    chosen (the card carries its rent) for landlord terms. Other routes are open to everyone."""
    if option_id == "spare_cash":
        return spare.value is not None and spare.value > 0
    if option_id == "setaside":
        prof = average_monthly_profit(src)
        return prof is not None and prof > 0
    if option_id == "own_savings":
        return plan.own_savings_cny > 0
    if option_id == "partner_equity":
        return plan.partner_equity_share > 0
    if option_id == "landlord_terms":
        return card.rent_monthly_sgd is not None and card.rent_free_months is not None
    return True


def _rent_adjust_sgd(card: CostCard, months: Decimal) -> float:
    """The plan model's first-transfer adjustment when the plan counts `months` rent-free (vs the card)."""
    assert card.rent_free_months is not None and card.rent_monthly_sgd is not None
    return float((card.rent_free_months - months) * card.rent_monthly_sgd * (1 + P.num("gst_rate")))


def _with_without(
    option_id: str, inp: PlanInputs, plan: FundingPlan, card: CostCard
) -> tuple[tuple[PlanInputs, float], tuple[PlanInputs, float]] | None:
    """The plan model's inputs and share with the route and without it, everything else the same."""
    share = float(plan.setaside_share)
    rep = dataclasses.replace
    if option_id == "spare_cash":
        off = rep(inp, spare=0.0, home_cash0=inp.home_cash0 + inp.spare)
        return (inp, share), (off, share)
    if option_id == "setaside":
        return (inp, share), (inp, 0.0)
    if option_id == "own_savings":
        on = rep(inp, own_savings=float(plan.own_savings_cny))
        return (on, share), (rep(on, own_savings=0.0), share)
    if option_id == "partner_equity":
        on = rep(inp, partner_share=float(plan.partner_equity_share))
        return (on, share), (rep(on, partner_share=0.0), share)
    rent_known = card.rent_monthly_sgd is not None and card.rent_free_months is not None
    if option_id == "landlord_terms" and rent_known:
        on = rep(inp, first_adjust_sgd=_rent_adjust_sgd(card, plan.rent_free_months))
        return (on, share), (rep(on, first_adjust_sgd=_rent_adjust_sgd(card, Decimal(0))), share)
    return None


def _weeks_to_money(
    e: CatalogueEntry, src: Src, card: CostCard, plan: FundingPlan, result: PlanResult
) -> Decimal | None:
    """When the route's money is in hand, in weeks from the plan start: a fixed number from the catalogue, a
    milestone's median week in the current plan, or the months of set-aside the current mix needs."""
    sw = e.speed_weeks
    if sw is None:
        return None
    if isinstance(sw, int):
        return Decimal(sw)
    if sw == "setaside":
        months = funding_mix(plan, card, result, src).setaside_months
        if months is None or months.value is None:
            return None
        return Decimal(math.ceil(months.value * P.num("weeks_per_month")))
    week = result.milestone_weeks.get(sw)
    return None if week is None else Decimal(week)


def _floor_change(option_id: str, inp: PlanInputs, plan: FundingPlan, card: CostCard) -> Decimal | None:
    """Floor risk with the route minus without it: the share of the full solve's seeded runs that dip below
    the floor, each way, on the same draws."""
    from tools import plan as PL

    pair = _with_without(option_id, inp, plan, card)
    if pair is None:
        return None
    runs, seed = P.inum("mc_runs"), P.default_seed()
    (i_on, s_on), (i_off, s_off) = pair
    on = int(PL.simulate(i_on, s_on, runs, seed).floor_breach.sum())
    off = int(PL.simulate(i_off, s_off, runs, seed).floor_breach.sum())
    return (Decimal(on - off) / Decimal(runs)).quantize(Decimal("0.0001"))


def ranking_words(r: RankedRoute, ranked: list[RankedRoute]) -> list[str]:
    """Words, never a score: cheapest and fastest only when they set a route apart from the others."""

    def vals(attr: str) -> list[Decimal]:
        out = []
        for x in ranked:
            f = getattr(x, attr)
            if f is not None and f.value is not None:
                out.append(f.value)
        return out

    def val(attr: str) -> Decimal | None:
        f = getattr(r, attr)
        return None if f is None else f.value

    words: list[str] = []
    cost, costs = val("cost"), vals("cost")
    if cost is not None and costs:
        if len(set(costs)) > 1 and cost == min(costs):
            words.append("cheapest")
        elif cost == 0:
            words.append("no_cost")
        if cost > 0:
            words.append("costs_profit_share")
    wk, wks = val("weeks"), vals("weeks")
    if wk is not None and len(set(wks)) > 1 and wk == min(wks):
        words.append("fastest")
    dil = val("dilution")
    if dil is not None:
        words.append("keeps_ownership" if dil == 0 else "gives_up_ownership")
    fc = val("floor_change")
    if fc is not None:
        words.append(
            "lowers_floor_risk" if fc < 0 else "raises_floor_risk" if fc > 0 else "floor_risk_unchanged"
        )
    return words


def rank_options(
    src: Src,
    card: CostCard,
    plan: FundingPlan,
    result: PlanResult,
    *,
    start_date: date | None = None,
    unit_available_from: date | None = None,
    lang: str = "en",
) -> list[RankedRoute]:
    """The plan routes for this owner, in the order to show them: the open routes ranked by effective cost
    (0 for own cash and landlord terms; the partner's profit share as a cost), weeks until the money is in
    hand, ownership given up, then the change in floor risk (lower first), ties in catalogue order; then the
    routes that only change timing (not ranked); then the routes not open to this owner yet, with why.
    `result` is the current plan's full solve (its milestone weeks and set-aside months)."""
    from tools import plan as PL

    spare = spare_cash(src)
    inp = PL.build_inputs(src, card, plan, start_date, unit_available_from)
    ranked: list[RankedRoute] = []
    timing: list[RankedRoute] = []
    not_yet: list[RankedRoute] = []
    for e in load_catalogue().options:
        if e.status == "closed" or not e.in_plan:
            continue
        if not route_eligible(e.id, src, card, plan, spare):
            not_yet.append(RankedRoute(id=e.id, eligible=False, why_not=e.text("eligible_when", lang)))
            continue
        if e.cost_kind in (None, "timing"):
            timing.append(RankedRoute(id=e.id, eligible=True, words=["changes_timing"]))
            continue
        fid = f"funding.rank.{e.id}"
        given_up = plan.partner_equity_share if e.cost_kind == "profit_share" else Decimal(0)
        diluted = plan.partner_equity_share if e.dilution == "partner_share" else Decimal(0)
        weeks = _weeks_to_money(e, src, card, plan, result)
        change = _floor_change(e.id, inp, plan, card)
        ranked.append(
            RankedRoute(
                id=e.id,
                eligible=True,
                ranked=True,
                cost=derived(
                    f"{fid}.cost", "Share of the Singapore profit given up", "pct", given_up,
                    tool="rank_options",
                ),
                weeks=derived(
                    f"{fid}.weeks", "When this route's money is in hand", "weeks", weeks, tool="rank_options",
                    note="median of the current plan's runs",
                ),
                dilution=derived(
                    f"{fid}.dilution", "Share of the Singapore company given up", "pct", diluted,
                    tool="rank_options",
                ),
                floor_change=derived(
                    f"{fid}.floor_change",
                    "Change in the chance home cash dips below the floor, with this route vs without it",
                    "pct",
                    change,
                    tool="rank_options",
                    assumptions=("mc_runs", "floor_payroll_weeks", "buffer_payroll_weeks"),
                    note="same seeded runs both ways",
                ),
            )
        )

    def key(r: RankedRoute) -> tuple[Decimal, float, Decimal, Decimal]:
        def v(f: Figure | None, missing: float) -> float:
            return missing if f is None or f.value is None else float(f.value)

        assert r.cost is not None and r.dilution is not None
        return (
            r.cost.value or Decimal(0),
            v(r.weeks, math.inf),  # not known: last on speed
            r.dilution.value or Decimal(0),
            Decimal(str(v(r.floor_change, 0.0))),
        )

    ranked.sort(key=key)  # stable: ties keep the catalogue order
    for r in ranked:
        r.words = ranking_words(r, ranked)
    return [*ranked, *timing, *not_yet]


# ------------------------------------------------------------------ mix


def funding_mix(
    plan: FundingPlan, card: CostCard, result: PlanResult | None, src: Src, lang: str = "en"
) -> MixResult:
    """How the likely total (RMB) is covered: spare cash, savings, partner, landlord terms, then set-aside.
    Only these plan routes: a bank card (WeBank home working capital, custody, FX) never covers any of it."""
    zh = lang == "zh"
    fx = card.fx_cny_per_sgd
    total = q0(card.total_likely_sgd * fx)
    spare = spare_cash(src)
    left = total
    parts: list[MixPart] = []

    def add(key: str, en: str, zh_: str, amt: Decimal, ins: list[Figure]) -> None:
        nonlocal left
        take = min(max(amt, Decimal(0)), left)
        if take > 0:
            parts.append(
                MixPart(
                    key=key,
                    label=zh_ if zh else en,
                    amount=derived(f"funding.mix.{key}", en, "CNY", q0(take), tool="funding_mix", inputs=ins),
                )
            )
            left -= take

    add("spare_cash", "Spare cash", "闲置资金", spare.value or Decimal(0), [spare])
    add("own_savings", "Own savings", "个人储蓄", plan.own_savings_cny, [])
    add("partner_equity", "Local partner", "本地合伙人", total * plan.partner_equity_share, [])
    if card.rent_free_months is not None and card.rent_monthly_sgd is not None:
        extra = plan.rent_free_months - card.rent_free_months
        add(
            "landlord_terms",
            "Extra rent-free months",
            "额外免租期",
            extra * card.rent_monthly_sgd * (1 + P.num("gst_rate")) * fx,
            [],
        )
    add("setaside", "Monthly set-aside", "每月留存", left, [])
    tot = derived(
        "funding.mix.total",
        "Total, likely (RMB)",
        "CNY",
        total,
        tool="funding_mix",
        inputs=[p.amount for p in parts],
        assumptions=("fx_cny_per_sgd",),
    )
    months = None
    if result is not None and result.monthly_setaside_cny > 0:
        sa = next((p.amount.value for p in parts if p.key == "setaside"), Decimal(0)) or Decimal(0)
        months = derived(
            "funding.setaside_months",
            "Months of set-aside",
            "months",
            (sa / result.monthly_setaside_cny).quantize(Decimal("0.1")),
            tool="funding_mix",
        )
    return MixResult(total=tot, parts=parts, setaside_months=months)


def plan_start(src: Src, start: date | None = None) -> date:
    if start is not None:
        return start
    if isinstance(src, FeedSnapshot):
        return src.as_of
    raise ValueError("a start date is needed when planning from a Profile")
