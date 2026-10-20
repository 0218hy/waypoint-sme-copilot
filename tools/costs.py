"""Cost tools (SPEC §6.3): the cost card for one unit, quotes, missing items, and cost Figures.

Each line comes from `data/cost_key.yaml` (formula + parameter inputs). The total is simulated with
correlated overruns across the overrun group (Gaussian copula, ρ from params). The likely total is the
median (P50, param) of the simulated total and the bad case its P90 (param), not the worst case on every
line. Each line's likely and bad values are its average over the samples whose total lies at that
quantile, so the lines add up to the totals. The sum of every input's most likely value is kept as the
base estimate (`total_base_sgd`); it sits below the median because the cost ranges are skewed upwards.

An accepted quote replaces a line's estimate only when it covers the whole line; a quote for part of a
line sets a floor under the estimate. A quoted line keeps a variation allowance (param), so it can still
overrun.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

import numpy as np
from pydantic import BaseModel

from tools import params as P
from tools.data import CostKeyLine, load_cost_key
from tools.figtools import derived, sourced
from tools.figures import Figure, Source, SourceKind, Taint, q0, q2
from tools.models import CostCard, CostLine, ExtractedQuote, Profile, Unit
from tools.params import Tri
from tools.stats import F64, copula_uniforms, tri_ppf

Level = Literal["basic", "standard", "premium"]
ManagerPlan = Literal["send_own", "hire_local"]
Pick = Callable[[Tri], F64]
TOOL = "estimate_costs"


@dataclass(frozen=True)
class CostContext:
    rent_monthly: float  # base rent + service charge, S$/month
    size_sqft: int
    lease_years: int
    level: Level
    manager_plan: ManagerPlan
    rent_free_months: float
    wage_date: date | None


class MissingItem(BaseModel):
    key: str
    label: str
    kind: Literal["no_quote", "excluded", "partial", "below_estimate", "conflict"]
    detail: str


@dataclass(frozen=True)
class QuoteUse:
    """How accepted quotes apply to one cost line."""

    cover: Literal["whole", "part"]
    amount: float  # S$: the quote for the whole line, or the floor its quoted parts set
    doc_id: str
    conflict: bool = False  # documents covering the whole line disagree


RESERVE_SUPPLIES = "_reserve_supplies"  # the reserve's utilities and other running costs (GST base)


# ------------------------------------------------------------------ wages (shared with sites.break_even)


def crew_wage_base(on: date | None) -> float:
    """PWM counter-attendant wage in force on `on` (the latest scheduled rate if no date)."""
    if on is None:
        tab = P.table("pwm_counter_attendant_wage_sgd")
        return float(tab[max(tab, key=lambda k: date.fromisoformat(str(k)))])
    return float(P.dated("pwm_counter_attendant_wage_sgd", on))


def monthly_wages(manager_plan: ManagerPlan, pick: Pick, n: int, wage_date: date | None) -> F64:
    """Monthly wage bill incl. employer CPF for locals (S$)."""
    staff = P.table("staff_plan")
    cpf = P.fnum("cpf_employer_rate")
    if manager_plan == "send_own":
        mgr: F64 = np.full(n, P.fnum("ep_min_salary_sgd") * float(staff["managers"]))  # no CPF for EP
    else:
        mgr = pick(P.tri("local_manager_wage_sgd")) * (1 + cpf) * float(staff["managers"])
    premium = pick(P.tri("crew_wage_market_premium"))
    crew: F64 = crew_wage_base(wage_date) * (1 + premium) * (1 + cpf) * float(staff["crew_fte"])
    out: F64 = mgr + crew
    return out


# ------------------------------------------------------------------ line formulas


def _rent_months(ctx: CostContext, ln: CostKeyLine, pick: Pick, n: int, v: dict[str, F64]) -> F64:
    return np.full(n, P.fnum(ln.inputs["months"]) * ctx.rent_monthly)


def _stamp_duty(ctx: CostContext, ln: CostKeyLine, pick: Pick, n: int, v: dict[str, F64]) -> F64:
    return np.full(n, P.fnum(ln.inputs["rate"]) * ctx.rent_monthly * 12 * ctx.lease_years)


def _tri(ctx: CostContext, ln: CostKeyLine, pick: Pick, n: int, v: dict[str, F64]) -> F64:
    return pick(P.tri(ln.inputs["amount"]))


def _fixed_param(ctx: CostContext, ln: CostKeyLine, pick: Pick, n: int, v: dict[str, F64]) -> F64:
    return np.full(n, P.fnum(ln.inputs["amount"]))


def _fitout_psf(ctx: CostContext, ln: CostKeyLine, pick: Pick, n: int, v: dict[str, F64]) -> F64:
    out: F64 = pick(P.tri(ln.inputs["psf"], ctx.level)) * ctx.size_sqft
    return out


def _pre_opening_rent(ctx: CostContext, ln: CostKeyLine, pick: Pick, n: int, v: dict[str, F64]) -> F64:
    months = pick(P.tri(ln.inputs["weeks"])) / P.weeks_per_month() - ctx.rent_free_months
    out: F64 = np.maximum(months, 0.0) * ctx.rent_monthly
    return out


def _stock_import_gst(ctx: CostContext, ln: CostKeyLine, pick: Pick, n: int, v: dict[str, F64]) -> F64:
    out: F64 = pick(P.tri(ln.inputs["amount"])) * (1 + P.fnum(ln.inputs["gst"]))
    return out


def _pre_opening_wages(ctx: CostContext, ln: CostKeyLine, pick: Pick, n: int, v: dict[str, F64]) -> F64:
    staff = P.table(ln.inputs["staff"])
    weeks = P.table(ln.inputs["weeks"])
    wpm = P.weeks_per_month()
    cpf = P.fnum(ln.inputs["cpf"])
    if ctx.manager_plan == "send_own":
        mgr_m: F64 = np.full(n, P.fnum("ep_min_salary_sgd"))
    else:
        mgr_m = pick(P.tri("local_manager_wage_sgd")) * (1 + cpf)
    crew_m = crew_wage_base(ctx.wage_date) * (1 + pick(P.tri("crew_wage_market_premium"))) * (1 + cpf)
    out: F64 = (
        mgr_m * float(staff["managers"]) * float(weeks["manager"]) / wpm
        + crew_m * float(staff["crew_fte"]) * float(weeks["crew"]) / wpm
    )
    return out


def _work_pass(ctx: CostContext, ln: CostKeyLine, pick: Pick, n: int, v: dict[str, F64]) -> F64:
    managers = float(P.table("staff_plan")["managers"])
    return np.full(n, P.fnum(ln.inputs["fee"]) * managers)


def _reserve(ctx: CostContext, ln: CostKeyLine, pick: Pick, n: int, v: dict[str, F64]) -> F64:
    months = P.fnum(ln.inputs["months"])
    supplies = pick(P.tri(ln.inputs["utilities"])) + P.fnum(ln.inputs["other"])
    v[RESERVE_SUPPLIES] = months * supplies
    wages = monthly_wages(ctx.manager_plan, pick, n, ctx.wage_date)
    out: F64 = months * (ctx.rent_monthly + wages + supplies)
    return out


def _gst_on(ctx: CostContext, ln: CostKeyLine, pick: Pick, n: int, v: dict[str, F64]) -> F64:
    base: F64 = np.zeros(n)
    for k in ln.gst_on:
        if k in v:
            base = base + v[k]
    if ln.plus_reserve_rent:
        base = base + P.fnum("reserve_months") * ctx.rent_monthly
    if ln.plus_reserve_supplies and RESERVE_SUPPLIES in v:
        base = base + v[RESERVE_SUPPLIES]
    out: F64 = base * P.fnum(ln.inputs["rate"])
    return out


Formula = Callable[[CostContext, CostKeyLine, Pick, int, dict[str, F64]], F64]
FORMULAS: dict[str, Formula] = {
    "rent_months": _rent_months,
    "stamp_duty": _stamp_duty,
    "tri": _tri,
    "fixed_param": _fixed_param,
    "fitout_psf": _fitout_psf,
    "pre_opening_rent": _pre_opening_rent,
    "stock_import_gst": _stock_import_gst,
    "pre_opening_wages": _pre_opening_wages,
    "work_pass": _work_pass,
    "reserve": _reserve,
    "gst_on": _gst_on,
}


# ------------------------------------------------------------------ evaluation


def _active_lines(ctx: CostContext) -> list[CostKeyLine]:
    return [ln for ln in load_cost_key().lines if ln.only_when is None or ln.only_when == ctx.manager_plan]


def _evaluate(
    ctx: CostContext,
    lines: Sequence[CostKeyLine],
    picks: dict[str, Pick],
    n: int,
    quoted: dict[str, QuoteUse],
) -> dict[str, F64]:
    """Evaluate every line in order (derived GST lines read earlier lines). A quote for the whole line
    replaces its estimate, plus the variation allowance drawn with the line's own (overrun) draw; quoted
    parts only set a floor under the estimate."""
    values: dict[str, F64] = {}
    for ln in lines:
        use = quoted.get(ln.key)
        if use is not None and use.cover == "whole":
            values[ln.key] = use.amount * (1.0 + picks[ln.key](P.tri("quote_variation_allowance")))
            continue
        est = FORMULAS[ln.formula](ctx, ln, picks[ln.key], n, values)
        values[ln.key] = est if use is None else np.maximum(est, use.amount)
    return values


def _const_pick(which: Literal["low", "likely", "high"]) -> Pick:
    def pick(t: Tri) -> F64:
        return np.array([getattr(t, which)], dtype=np.float64)

    return pick


def _context(
    unit: Unit,
    level: Level,
    manager_plan: ManagerPlan,
    rent_free_months: Decimal | None,
    wage_date: date | None,
) -> CostContext:
    rf = P.fnum("rent_free_months") if rent_free_months is None else float(rent_free_months)
    return CostContext(
        rent_monthly=float(unit.rent_monthly_sgd + unit.service_charge_monthly_sgd),
        size_sqft=unit.size_sqft,
        lease_years=unit.lease_years,
        level=level,
        manager_plan=manager_plan,
        rent_free_months=rf,
        wage_date=wage_date,
    )


def quote_uses(quotes: Sequence[ExtractedQuote]) -> dict[str, QuoteUse]:
    """How accepted quote lines apply, by cost key. Unmatched lines (no key yet) are left out.

    A document covers a cost line in full when one of its accepted lines for that key is not marked as a
    part (it named the whole line, or the owner said the quote covers all of it); then all its lines for
    that key add up to the quote. A document with only part lines sets a floor (the largest such document).
    When documents that each cover the whole line disagree, the higher one is used and the line is flagged
    as a conflict: the order the documents came in never decides it."""
    fx = float(P.fx())
    whole: dict[str, dict[str, float]] = {}
    part: dict[str, dict[str, float]] = {}
    for q in quotes:
        per_doc: dict[str, float] = {}
        covers: set[str] = set()
        for ln in q.lines:
            if ln.status != "accepted" or ln.matched_key is None or ln.amount is None:
                continue
            amt = float(ln.amount) / fx if ln.currency == "CNY" else float(ln.amount)
            per_doc[ln.matched_key] = per_doc.get(ln.matched_key, 0.0) + amt
            if not ln.part:
                covers.add(ln.matched_key)
        for k, a in per_doc.items():
            (whole if k in covers else part).setdefault(k, {})[q.doc_id] = a
    out: dict[str, QuoteUse] = {}
    for k, docs in whole.items():
        doc = max(docs, key=lambda d: docs[d])
        distinct = {q0(Decimal(repr(a))) for a in docs.values()}
        out[k] = QuoteUse("whole", docs[doc], doc, conflict=len(distinct) > 1)
    for k, docs in part.items():
        if k not in out:
            doc = max(docs, key=lambda d: docs[d])
            out[k] = QuoteUse("part", docs[doc], doc)
    return out


def _simulate(
    ctx: CostContext, lines: Sequence[CostKeyLine], quoted: dict[str, QuoteUse], seed: int
) -> dict[str, F64]:
    """Every line over the seeded samples (correlated overruns via the Gaussian copula)."""
    n = P.inum("cost_mc_samples")
    rng = np.random.default_rng(seed)
    over = [ln.key for ln in lines if ln.overrun]
    rest = [ln.key for ln in lines if not ln.overrun]
    u_over = copula_uniforms(rng, n, len(over), P.fnum("cost_overrun_rho"))
    u_rest = rng.random((n, len(rest)))
    u_by_key = {k: u_over[:, i] for i, k in enumerate(over)} | {k: u_rest[:, i] for i, k in enumerate(rest)}

    def sample_pick(key: str) -> Pick:
        return lambda t: tri_ppf(t, u_by_key[key])

    return _evaluate(ctx, lines, {ln.key: sample_pick(ln.key) for ln in lines}, n, quoted)


def simulated_totals(
    unit: Unit,
    fitout_level: Level = "standard",
    manager_plan: ManagerPlan = "hire_local",
    quotes: Sequence[ExtractedQuote] = (),
    seed: int | None = None,
) -> F64:
    """The simulated totals behind a cost card (S$), for checks and the evidence."""
    ctx = _context(unit, fitout_level, manager_plan, None, None)
    lines = _active_lines(ctx)
    samples = _simulate(ctx, lines, quote_uses(quotes), P.default_seed() if seed is None else seed)
    out: F64 = np.sum(np.stack([samples[ln.key] for ln in lines]), axis=0)
    return out


def estimate_costs(
    unit: Unit,
    profile: Profile | None = None,
    fitout_level: Level = "standard",
    manager_plan: ManagerPlan = "hire_local",
    quotes: Sequence[ExtractedQuote] = (),
    seed: int | None = None,
    *,
    rent_free_months: Decimal | None = None,
    wage_date: date | None = None,
) -> CostCard:
    """The cost card for `unit`. Seeded; the seed is stored on the card."""
    seed = P.default_seed() if seed is None else seed
    ctx = _context(unit, fitout_level, manager_plan, rent_free_months, wage_date)
    lines = _active_lines(ctx)
    quoted = quote_uses(quotes)
    samples = _simulate(ctx, lines, quoted, seed)
    point = {
        w: _evaluate(ctx, lines, {ln.key: _const_pick(w) for ln in lines}, 1, quoted)
        for w in ("low", "likely", "high")
    }
    estimate_low = _evaluate(ctx, lines, {ln.key: _const_pick("low") for ln in lines}, 1, {})
    total = np.sum(np.stack([samples[ln.key] for ln in lines]), axis=0)
    w = P.fnum("cost_bad_window")

    def at(quantile: float) -> np.ndarray:  # samples whose total lies at this quantile (+/- the window)
        lo, hi = np.quantile(total, [max(quantile - w, 0.0), min(quantile + w, 1.0)])
        return np.asarray((total >= lo) & (total <= hi))

    m_likely, m_bad = at(P.fnum("likely_quantile")), at(P.fnum("bad_case_quantile"))

    def dq(x: float) -> Decimal:
        return q0(Decimal(repr(x)))

    out: list[CostLine] = []
    for ln in lines:
        use = quoted.get(ln.key)
        whole = use is not None and use.cover == "whole"
        likely = dq(float(np.mean(samples[ln.key][m_likely])))
        bad = max(dq(float(np.mean(samples[ln.key][m_bad]))), likely)
        flags: list[Literal["partial", "below_estimate", "conflict"]] = []
        if use is not None and not whole:
            flags.append("partial")
        if use is not None and whole and use.amount < float(estimate_low[ln.key][0]):
            flags.append("below_estimate")
        if use is not None and use.conflict:
            flags.append("conflict")
        note = ln.likely_basis
        if whole:
            note = "Accepted quote plus a variation allowance (quote_variation_allowance)"
        elif use is not None:
            note = f"{ln.likely_basis}; at least the quoted parts"
        out.append(
            CostLine(
                key=ln.key,
                group=ln.group,
                label=ln.label_en,
                label_zh=ln.label_zh,
                likely_sgd=likely,
                bad_sgd=bad,
                mode_sgd=dq(float(point["likely"][ln.key][0])),
                low_sgd=dq(float(point["low"][ln.key][0])),
                high_sgd=dq(float(point["high"][ln.key][0])),
                due=ln.due,
                source=f"quote:{use.doc_id}" if whole and use is not None else f"cost_key:{ln.key}",
                from_quote=whole,
                overrun=ln.overrun,
                note=note,
                quote_sgd=None if use is None else dq(use.amount),
                quote_cover=None if use is None else use.cover,
                flags=flags,
            )
        )
    card = CostCard(
        unit_id=unit.id,
        fitout_level=fitout_level,
        manager_plan=manager_plan,
        lines=out,
        total_likely_sgd=sum((ln.likely_sgd for ln in out), Decimal("0")),
        total_bad_sgd=sum((ln.bad_sgd for ln in out), Decimal("0")),
        total_base_sgd=sum((ln.mode_sgd or ln.likely_sgd for ln in out), Decimal("0")),
        fx_cny_per_sgd=P.fx(),
        rent_monthly_sgd=unit.rent_monthly_sgd + unit.service_charge_monthly_sgd,
        rent_free_months=Decimal(repr(ctx.rent_free_months)),
        size_sqft=unit.size_sqft,
        bad_quantile=P.num("bad_case_quantile"),
        seed=seed,
    )
    card.missing = [m.key for m in missing_items(card, quotes)]
    return card


def quick_cost_likely(
    unit: Unit, fitout_level: Level = "standard", manager_plan: ManagerPlan = "hire_local"
) -> Decimal:
    """Likely total for unit cards and budget filters: the same simulated median as the cost card (no quotes,
    default seed), so the early cost and the card agree."""
    return estimate_costs(unit, None, fitout_level, manager_plan).total_likely_sgd


def apply_quotes(
    card: CostCard, unit: Unit, quotes: Sequence[ExtractedQuote], seed: int | None = None
) -> CostCard:
    """Rebuild the card with accepted quote lines (whole lines replace estimates; parts set a floor)."""
    return estimate_costs(
        unit,
        None,
        card.fitout_level,
        card.manager_plan,
        quotes,
        card.seed if seed is None else seed,
        rent_free_months=card.rent_free_months,
    )


# ------------------------------------------------------------------ missing items


def missing_items(
    card: CostCard, quotes: Sequence[ExtractedQuote] = (), lang: str = "en"
) -> list[MissingItem]:
    """Quotable lines no accepted quote covers in full, quotes to check (below the estimate's low end, or
    two quotes that disagree), plus phrases a quote says are excluded (e.g. 拆除另计)."""
    key = load_cost_key()
    labels = {ln.key: (ln.label_zh if lang == "zh" else ln.label_en) for ln in key.lines}
    out: list[MissingItem] = []
    on_card = {ln.key for ln in card.lines}
    zh = lang == "zh"
    details = {
        "no_quote": "还没有报价覆盖这一项" if zh else "No quote covers this yet",
        "partial": "报价只覆盖了这一项的一部分；在有报价覆盖全部之前，仍按估算计"
        if zh
        else "Your quote prices only part of this; the estimate stays until a quote covers all of it",
        "below_estimate": "报价低于我们估算的下限：请核对它漏了什么"
        if zh
        else "The quote is below the low end of our estimate: check what it leaves out",
        "conflict": "两份报价对这一项的金额不同；在你填入要用的金额之前，按较高的那份计"
        if zh
        else "Two quotes differ on this; the card uses the higher one until you enter the one you go with",
    }
    for ln in key.lines:
        if ln.key not in on_card or not ln.quotable:
            continue
        line = next(c for c in card.lines if c.key == ln.key)
        kinds: list[Literal["no_quote", "partial", "below_estimate", "conflict"]] = [*line.flags]
        if not line.from_quote and "partial" not in kinds:
            kinds.insert(0, "no_quote")
        for kind in kinds:
            out.append(MissingItem(key=ln.key, label=labels[ln.key], kind=kind, detail=details[kind]))
    for q in quotes:
        for phrase in q.exclusions:
            low = phrase.lower()
            for ln in key.lines:
                if ln.key in on_card and any(kw.lower() in low for kw in [*ln.keywords, *ln.part_keywords]):
                    prefix = "报价注明不含：" if lang == "zh" else "Your quote excludes: "
                    out.append(
                        MissingItem(key=ln.key, label=labels[ln.key], kind="excluded", detail=prefix + phrase)
                    )
                    break
    return out


# ------------------------------------------------------------------ figures


def _line_source(line: CostLine, kl: CostKeyLine | None) -> tuple[Source, Taint]:
    if line.from_quote:
        return Source(
            kind=SourceKind.DOCUMENT,
            ref=line.source.removeprefix("quote:"),
            note="accepted quote plus a variation allowance (quote_variation_allowance)",
        ), (Taint.UNTRUSTED)
    note = None if kl is None else kl.source
    if line.quote_cover == "part":  # the quoted parts set a floor: a document value can reach the line
        note = f"{note}; at least the quoted parts (accepted quote lines)"
    return (
        Source(
            kind=SourceKind.TOOL,
            ref=f"{TOOL}:{line.key}",
            as_of=None if kl is None else kl.as_of,
            note=note,
            url=None if kl is None else kl.url,
        ),
        Taint.UNTRUSTED if line.quote_cover == "part" else Taint.TRUSTED,
    )


def cost_figures(card: CostCard, lang: str = "en") -> list[Figure]:
    """Figures for the cost card: each line, each group, and the totals in S$ and RMB at the dated FX."""
    key = load_cost_key()
    kl = {ln.key: ln for ln in key.lines}
    figs: list[Figure] = []
    line_figs: dict[str, tuple[Figure, Figure]] = {}
    for ln in card.lines:
        src, taint = _line_source(ln, kl.get(ln.key))
        label = ln.label_zh if lang == "zh" and ln.label_zh else ln.label
        likely = sourced(f"cost.{ln.key}.likely", label, "SGD", ln.likely_sgd, src, taint=taint)
        bad = sourced(f"cost.{ln.key}.bad", label, "SGD", ln.bad_sgd, src, taint=taint)
        line_figs[ln.key] = (likely, bad)
        figs += [likely, bad]
    fx_fig = P.param_fig("fx_cny_per_sgd", "FX CNY per SGD", "CNY", fig_id="param.fx")
    figs.append(fx_fig)
    for g, lines in card.by_group().items():
        lab = key.groups[g]["label_zh" if lang == "zh" else "label_en"]
        ins_l = [line_figs[ln.key][0] for ln in lines]
        ins_b = [line_figs[ln.key][1] for ln in lines]
        figs.append(
            derived(
                f"cost.group.{g}.likely",
                lab,
                "SGD",
                sum((f.value or Decimal(0)) for f in ins_l),
                tool=TOOL,
                inputs=ins_l,
            )
        )
        figs.append(
            derived(
                f"cost.group.{g}.bad",
                lab,
                "SGD",
                sum((f.value or Decimal(0)) for f in ins_b),
                tool=TOOL,
                inputs=ins_b,
            )
        )
    all_l = [v[0] for v in line_figs.values()]
    all_b = [v[1] for v in line_figs.values()]
    fx = card.fx_cny_per_sgd
    assume = ("fx_cny_per_sgd",)
    tl = derived(
        "cost.total.likely_sgd",
        "Total, likely",
        "SGD",
        card.total_likely_sgd,
        tool=TOOL,
        inputs=all_l,
        assumptions=("likely_quantile", "cost_overrun_rho"),
    )
    tb = derived(
        "cost.total.bad_sgd",
        "Total, if things go badly",
        "SGD",
        card.total_bad_sgd,
        tool=TOOL,
        inputs=all_b,
        assumptions=("bad_case_quantile", "cost_overrun_rho"),
    )
    figs += [
        tl,
        tb,
        derived(
            "cost.total.likely_cny",
            "Total, likely (RMB)",
            "CNY",
            q0(card.total_likely_sgd * fx),
            tool=TOOL,
            inputs=[tl, fx_fig],
            assumptions=assume,
        ),
        derived(
            "cost.total.bad_cny",
            "Total, if things go badly (RMB)",
            "CNY",
            q0(card.total_bad_sgd * fx),
            tool=TOOL,
            inputs=[tb, fx_fig],
            assumptions=assume,
        ),
    ]
    return figs


def due_totals_sgd(card: CostCard, which: Literal["likely", "bad"] = "likely") -> dict[str, Decimal]:
    """Money needed in Singapore by transfer: setup, first (R6) and opening."""
    out = {"setup": Decimal(0), "first": Decimal(0), "opening": Decimal(0)}
    for ln in card.lines:
        v = ln.likely_sgd if which == "likely" else ln.bad_sgd
        out[transfer_for(ln.due)] += v
    return {k: q2(v) for k, v in out.items()}


def transfer_for(due: str) -> Literal["setup", "first", "opening"]:
    if due in ("incorporate", "setup_transfer"):
        return "setup"
    if due in ("first_transfer", "sign_lease", "fitout"):
        return "first"
    return "opening"
