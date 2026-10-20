"""Compare funding plans (SPEC §6.4): side-by-side columns, each one run of the plan model.

Each column is a set of plan routes from the catalogue's `compare:` block (set-aside only; set-aside plus
the owner's savings; set-aside plus a local partner), run once through `tools.plan.simulate_plan` at the
slider's set-aside share, with the same seed and runs as the slider's full solve and everything else in the
owner's plan (spare cash, landlord terms, the chosen unit) unchanged. Every row is a code-computed Figure. The
pros and cons are the ranking words of `tools.funding.ranking_words`, worked out across the columns, plus each
route's own cost and conditions from the catalogue: no new copy is written here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from tools import params as P
from tools import plan as PL
from tools.data import CompareEntry, load_catalogue
from tools.figtools import derived
from tools.figures import Figure, dec, q0
from tools.funding import RankedRoute, Src, ranking_words
from tools.models import CostCard, FundingPlan, PlanResult
from tools.stats import wilson_upper

TOOL = "compare_plans"
# ranking words that read as a pro, and as a con; `floor_risk_unchanged` is neither
PROS = ("cheapest", "no_cost", "fastest", "keeps_ownership", "lowers_floor_risk")
CONS = ("slowest", "costs_profit_share", "gives_up_ownership", "raises_floor_risk")


class RouteTerms(BaseModel):
    """A route's own cost and conditions, as the catalogue words them."""

    id: str
    label: str
    cost: str
    conditions: str


class CompareColumn(BaseModel):
    id: str
    title: str
    blurb: str
    routes: list[str]
    toggles: dict[str, bool]  # the toggle_option actions that apply this column
    open: bool = True  # False: the partner column before the owner says a partner is possible
    why_not: str | None = None
    chosen: bool = False  # the owner's current plan is this column
    savings: Figure | None = None
    monthly: Figure | None = None
    open_likely: Figure | None = None
    open_p95: Figure | None = None
    floor_risk: Figure | None = None
    floor_risk_upper: Figure | None = None
    ownership: Figure | None = None
    profit_share: Figure | None = None  # partner column: the share of the Singapore profit the partner takes
    pros: list[str] = []
    cons: list[str] = []
    terms: list[RouteTerms] = []
    result: PlanResult | None = None

    def figures(self) -> list[Figure]:
        figs = (
            self.savings,
            self.monthly,
            self.open_likely,
            self.open_p95,
            self.floor_risk,
            self.floor_risk_upper,
            self.ownership,
            self.profit_share,
        )
        return [f for f in figs if f is not None]


def partner_share(plan: FundingPlan) -> Decimal:
    """The partner's share in the partner column: the owner's own, else the least local share EFS asks."""
    return plan.partner_equity_share if plan.partner_equity_share > 0 else P.num("partner_min_local_share")


def partner_open(plan: FundingPlan) -> bool:
    return plan.partner_considered or plan.partner_equity_share > 0


def default_savings(plan: FundingPlan, presets: list[Decimal]) -> Decimal:
    """The savings column starts at what the owner has put in, else the smallest amount they're offered."""
    if plan.own_savings_cny > 0:
        return plan.own_savings_cny
    offered = sorted(v for v in presets if v > 0)
    return offered[0] if offered else Decimal(0)


def savings_max(card: CostCard) -> Figure:
    """The most the savings column takes: the likely total in RMB (more would sit unused in the pot)."""
    total = q0(card.total_likely_sgd * card.fx_cny_per_sgd)
    return derived(
        "funding.compare.savings_max", "Most savings the plan can use", "CNY", total,
        tool=TOOL, assumptions=("fx_cny_per_sgd",),
    )


def column_plan(entry: CompareEntry, plan: FundingPlan, savings: Decimal) -> FundingPlan:
    """The owner's plan with this column's routes: only the savings and the partner change."""
    on = entry.toggles
    return plan.model_copy(
        update={
            "own_savings_cny": savings if on.get("own_savings") else Decimal(0),
            "partner_equity_share": partner_share(plan) if on.get("partner_equity") else Decimal(0),
        }
    )


def _terms(entry: CompareEntry, common: set[str], lang: str) -> list[RouteTerms]:
    """The cost and conditions of the routes that set this column apart (those not in every column); a column
    with none of its own (set-aside only) lists its routes, less the spare cash every plan starts from."""
    cat = load_catalogue()
    own = [r for r in entry.routes if r not in common] or [r for r in entry.routes if r != "spare_cash"]
    out = []
    for rid in own:
        e = cat.get(rid)
        if e is None:
            continue
        out.append(
            RouteTerms(
                id=rid,
                label=e.text("label", lang),
                cost=e.text("cost", lang),
                conditions=e.text("conditions", lang),
            )
        )
    return out


def _figures(cid: str, cplan: FundingPlan, res: PlanResult, runs: int) -> dict[str, Figure | None]:
    fid = f"funding.compare.{cid}"
    note = f"seed {res.seed}, {res.runs} runs"
    assume = ("mc_runs", "default_seed", "horizon_weeks")
    breaches = int(round(float(res.floor_risk) * runs))
    partner = cplan.partner_equity_share
    return {
        "savings": derived(f"{fid}.savings", "Extra savings added", "CNY", cplan.own_savings_cny, tool=TOOL),
        "monthly": derived(
            f"{fid}.monthly", "Monthly set-aside", "CNY", res.monthly_setaside_cny, tool=TOOL, note=note
        ),
        "open_likely": derived(
            f"{fid}.open_likely", "Likely opening", "weeks", res.open_likely_week,
            tool=TOOL, assumptions=assume, note=note,
        ),
        "open_p95": derived(
            f"{fid}.open_p95", "Opening if things go badly", "weeks", res.open_p95_week,
            tool=TOOL, assumptions=assume, note=note,
        ),
        "floor_risk": derived(
            f"{fid}.floor_risk", "Chance home cash dips below the floor", "pct", res.floor_risk,
            tool=TOOL, assumptions=("floor_risk_limit", *assume), note=f"{note}; an estimate",
        ),
        "floor_risk_upper": derived(
            f"{fid}.floor_risk_upper", "Floor risk, upper bound", "pct",
            dec(wilson_upper(breaches, runs)).quantize(Decimal("0.0001")),
            tool=TOOL, assumptions=("floor_risk_limit", *assume), note=f"{note}; Wilson 95% upper bound",
        ),
        "ownership": derived(
            f"{fid}.ownership", "Ownership of the Singapore company kept", "pct", Decimal(1) - partner,
            tool=TOOL,
        ),
        "profit_share": (
            derived(
                f"{fid}.profit_share", "Share of the Singapore profit the partner takes", "pct", partner,
                tool=TOOL, assumptions=("partner_min_local_share",),
            )
            if partner > 0
            else None
        ),
    }


def _chosen(cplan: FundingPlan, plan: FundingPlan) -> bool:
    """The owner's current plan is this column: the same savings and the same partner share."""
    same_savings = cplan.own_savings_cny == plan.own_savings_cny
    return same_savings and cplan.partner_equity_share == plan.partner_equity_share


def compare_plans(
    src: Src,
    card: CostCard,
    plan: FundingPlan,
    *,
    savings_cny: Decimal,
    start_date: date | None = None,
    unit_available_from: date | None = None,
    lang: str = "en",
) -> list[CompareColumn]:
    """One column per catalogue `compare:` entry, each a full solve of the plan model at the plan's share (the
    slider's), with the same seed and runs as the slider. The partner column is run only once the owner has
    said a partner is possible; before that it carries the catalogue's `eligible_when` text instead."""
    runs, seed = P.inum("mc_runs"), P.default_seed()
    cat = load_catalogue()
    common = set.intersection(*(set(e.routes) for e in cat.compare)) if cat.compare else set()
    cols: list[CompareColumn] = []
    for entry in cat.compare:
        col = CompareColumn(
            id=entry.id,
            title=entry.text("title", lang),
            blurb=entry.text("blurb", lang),
            routes=entry.routes,
            toggles=entry.toggles,
            terms=_terms(entry, common, lang),
        )
        if entry.toggles.get("partner_equity") and not partner_open(plan):
            partner = cat.get("partner_equity")
            col.open = False
            col.why_not = partner.text("eligible_when", lang) if partner is not None else None
            cols.append(col)
            continue
        cplan = column_plan(entry, plan, savings_cny)
        res = PL.simulate_plan(
            src, card, cplan, runs=runs, seed=seed,
            start_date=start_date, unit_available_from=unit_available_from,
        )
        figs = _figures(entry.id, cplan, res, runs)
        cols.append(col.model_copy(update={**figs, "result": res, "chosen": _chosen(cplan, plan)}))
    _pros_and_cons(cols)
    return cols


def _pros_and_cons(cols: list[CompareColumn]) -> None:
    """The ranking words across the open columns: the partner's profit share as the cost, the likely opening
    as the speed, ownership given up, and the floor risk against the set-aside-only column (the first)."""
    run = [c for c in cols if c.open and c.result is not None]
    if not run:
        return
    base = run[0].floor_risk
    ranked: list[RankedRoute] = []
    for c in run:
        fid = f"funding.compare.{c.id}"
        share = c.profit_share.value if c.profit_share is not None else Decimal(0)
        change = None
        if c is not run[0] and base is not None and base.value is not None and c.floor_risk is not None:
            assert c.floor_risk.value is not None
            change = c.floor_risk.value - base.value
        ranked.append(
            RankedRoute(
                id=c.id,
                eligible=True,
                ranked=True,
                cost=derived(f"{fid}.cost", "Profit given up", "pct", share, tool=TOOL),
                weeks=c.open_likely,
                dilution=derived(f"{fid}.dilution", "Ownership given up", "pct", share, tool=TOOL),
                floor_change=(
                    None
                    if change is None
                    else derived(f"{fid}.floor_change", "Change in floor risk", "pct", change, tool=TOOL)
                ),
            )
        )
    weeks = {r.weeks.value for r in ranked if r.weeks is not None and r.weeks.value is not None}
    for c, r in zip(run, ranked, strict=True):
        words = ranking_words(r, ranked)
        wk = r.weeks.value if r.weeks is not None else None
        if wk is not None and len(weeks) > 1 and wk == max(weeks):
            words.append("slowest")
        c.pros = [w for w in PROS if w in words]
        c.cons = [w for w in CONS if w in words]
