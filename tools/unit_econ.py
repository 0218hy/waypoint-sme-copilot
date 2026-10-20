"""Unit economics and payback of the new shop (judge-response memo §3a).

Per cup: contribution = net price - variable cost - delivery commission x delivery share. While the shop
is not GST-registered (a new Pte Ltd) the whole menu price is revenue, and the GST it pays on supplies,
rent, service charge, utilities, other running costs and commissions is a cost. When a level's yearly
sales exceed the compulsory-registration threshold (about S$1m), that level is treated as registered: the
menu price includes GST and input GST is claimed back.

A month: EBITDA = cups x contribution x days - fixed costs, rent = max(base rent, turnover rent). Tax:
17% each year on EBITDA less the investment spread over the lease, with partial exemption only (SUTE does
not apply to a wholly foreign-owned subsidiary) and losses carried forward. Ramp-up (an estimate):
cups in month m = steady cups x (1 - (1 - s0) exp(-(m - 1) / tau)).

Investment = the cost card total less the running reserve (and the reserve's GST), so the ramp-up losses
the reserve covers are not counted twice. Payback = the first month whose cumulative cash (after tax, with
the fit-out deposit back at opening) reaches the investment; none within the lease is "not within the
lease". NPV over the lease (36 months) at the discount rate, with the security deposit (less reinstatement)
and the opening stock back at the end. "Likely" pairs the likely investment with the likely ramp; "if things
go badly" the P90 investment with the slow ramp. Every number comes from the cost card and params.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, cast

import numpy as np

from tools import params as P
from tools.costs import ManagerPlan, monthly_wages
from tools.data import load_cost_key
from tools.figtools import derived
from tools.figures import Figure, Source, SourceKind
from tools.figures import Unit as FigUnit
from tools.models import CostCard, Unit

TOOL = "unit_economics"
Case = Literal["likely", "bad"]

# ------------------------------------------------------------------ per cup and per month


@dataclass(frozen=True)
class Shop:
    """The running costs of one unit, at one menu price, registered for GST or not."""

    price: float  # what the customer pays
    registered: bool
    wages: float
    base_rent: float
    service: float
    utilities: float
    other: float
    gto: float  # turnover rent share of sales, 0 if none
    days: float

    @property
    def gst(self) -> float:
        """The factor GST adds to a cost the shop can't claim back (1 once registered)."""
        return 1.0 if self.registered else 1 + P.fnum("gst_rate")

    @property
    def net_price(self) -> float:
        return self.price / (1 + P.fnum("gst_rate")) if self.registered else self.price

    @property
    def variable_cost(self) -> float:
        return P.fnum("variable_cost_per_cup_sgd") * self.gst

    @property
    def delivery_cost(self) -> float:
        return self.price * P.fnum("delivery_share") * P.fnum("delivery_commission") * self.gst

    @property
    def contribution(self) -> float:
        return self.net_price - self.variable_cost - self.delivery_cost

    def rent(self, cups: float) -> float:
        return max(self.base_rent, self.gto * cups * self.net_price * self.days)

    def fixed(self, cups: float) -> float:
        """Fixed costs in a month at `cups` a day (turnover rent depends on sales)."""
        return self.wages + (self.service + self.utilities + self.other + self.rent(cups)) * self.gst

    def revenue(self, cups: float) -> float:
        return cups * self.net_price * self.days

    def ebitda(self, cups: float) -> float:
        return cups * self.contribution * self.days - self.fixed(cups)


def shop(
    unit: Unit, manager_plan: ManagerPlan = "hire_local", price: float | None = None, registered: bool = False
) -> Shop:
    wages = float(monthly_wages(manager_plan, lambda t: np.array([t.likely]), 1, None)[0])
    return Shop(
        price=P.fnum("cup_price_sgd") if price is None else price,
        registered=registered,
        wages=wages,
        base_rent=float(unit.rent_monthly_sgd),
        service=float(unit.service_charge_monthly_sgd),
        utilities=P.tri("utilities_monthly_sgd").likely,
        other=P.fnum("other_fixed_monthly_sgd"),
        gto=float(unit.gto_pct or 0),
        days=P.fnum("opening_days_per_month"),
    )


def registered_at(
    unit: Unit, cups: float, manager_plan: ManagerPlan = "hire_local", price: float | None = None
) -> bool:
    """Compulsory GST registration: steady yearly sales (at the menu price) above the threshold."""
    s = shop(unit, manager_plan, price)
    return s.revenue(cups) * 12 > P.fnum("gst_registration_threshold_sgd")


def shop_at(
    unit: Unit, cups: float, manager_plan: ManagerPlan = "hire_local", price: float | None = None
) -> Shop:
    return shop(unit, manager_plan, price, registered_at(unit, cups, manager_plan, price))


def break_even_cups(unit: Unit, manager_plan: ManagerPlan = "hire_local") -> float:
    """Cups a day at which a month's EBITDA is zero (not registered). Fixed point under turnover rent."""
    s = shop(unit, manager_plan)
    per_day = s.contribution * s.days
    cups = s.fixed(0) / per_day
    for _ in range(P.inum("breakeven_max_iter")):
        nxt = s.fixed(cups) / per_day
        if abs(nxt - cups) < 1e-6:
            return nxt
        cups = nxt
    return cups


# ------------------------------------------------------------------ investment


@dataclass(frozen=True)
class Investment:
    total: float  # cash put in before opening (card total less the reserve and its GST)
    reserve: float  # the running reserve and its GST, left out
    sunk: float  # spread over the lease for tax
    refund_opening: float  # the landlord's fit-out deposit, back once the fit-out is done
    refund_end: float  # the security deposit, back at the end of the lease (before reinstatement)
    working_capital: float  # the opening stock, recovered at the end


def investment(card: CostCard, case: Case) -> Investment:
    kinds = {kl.key: kl for kl in load_cost_key().lines}
    total = reserve = sunk = r_open = r_end = wc = 0.0
    for ln in card.lines:
        v = float(ln.likely_sgd if case == "likely" else ln.bad_sgd)
        kl = kinds.get(ln.key)
        kind = kl.kind if kl is not None else "sunk"
        if kind == "reserve":
            reserve += v
            continue
        total += v
        if kind == "refundable" and kl is not None:
            if kl.refund_at == "opening":
                r_open += v
            else:
                r_end += v
        elif kind == "working_capital":
            wc += v
        else:
            sunk += v
    # the GST line on services also carries the reserve's rent and running costs: leave that part out too
    months = P.fnum("reserve_months")
    rent = float(card.rent_monthly_sgd or 0)
    supplies = P.tri("utilities_monthly_sgd").likely + P.fnum("other_fixed_monthly_sgd")
    reserve_gst = P.fnum("gst_rate") * months * (rent + supplies)
    total -= reserve_gst
    sunk -= reserve_gst
    return Investment(
        total=total,
        reserve=reserve + reserve_gst,
        sunk=sunk,
        refund_opening=r_open,
        refund_end=r_end,
        working_capital=wc,
    )


# ------------------------------------------------------------------ the lease, month by month


def ramp(case: Case, months: int) -> list[float]:
    """Share of steady-state cups in months 1..n (an estimate, params ramp_curve)."""
    r = P.table("ramp_curve")[case]
    s0, tau = float(r["s0"]), float(r["tau_months"])
    return [1 - (1 - s0) * math.exp(-(m - 1) / tau) for m in range(1, months + 1)]


def lease_months(unit: Unit) -> int:
    return unit.lease_years * 12


def corporate_tax(chargeable: float) -> float:
    """17% with partial exemption only (IRAS bands, params sg_partial_exemption)."""
    if chargeable <= 0:
        return 0.0
    exempt, prev = 0.0, 0.0
    for band in P.items("sg_partial_exemption"):
        top = float(band["up_to_sgd"])
        exempt += max(0.0, min(chargeable, top) - prev) * float(band["exempt_share"])
        prev = top
    return P.fnum("sg_cit_rate") * (chargeable - exempt)


@dataclass(frozen=True)
class Lease:
    cash: list[float]  # after-tax operating cash in months 1..n (fit-out deposit back in month 1)
    tax: list[float]
    end_refund: float  # security deposit - reinstatement + opening stock, at the end of month n
    payback_month: int | None


def run_lease(
    unit: Unit,
    card: CostCard,
    steady_cups: float,
    case: Case,
    manager_plan: ManagerPlan = "hire_local",
    price: float | None = None,
) -> Lease:
    inv = investment(card, case)
    n = lease_months(unit)
    s = shop_at(unit, steady_cups, manager_plan, price)
    shares = ramp(case, n)
    ebitda = [s.ebitda(steady_cups * k) for k in shares]
    dep = inv.sunk / n
    tax = [0.0] * n
    loss = 0.0
    for y in range(0, n, 12):
        chargeable = sum(ebitda[y : y + 12]) - dep * len(ebitda[y : y + 12]) - loss
        loss = max(0.0, -chargeable)
        tax[min(y + 11, n - 1)] = corporate_tax(chargeable)
    cash = [e - t for e, t in zip(ebitda, tax, strict=True)]
    cash[0] += inv.refund_opening
    cum, pay = -inv.total, None
    for m, c in enumerate(cash, start=1):
        cum += c
        if cum >= 0:
            pay = m
            break
    end = inv.refund_end - P.fnum("reinstatement_sgd") + inv.working_capital
    return Lease(cash=cash, tax=tax, end_refund=end, payback_month=pay)


def npv(
    unit: Unit,
    card: CostCard,
    steady_cups: float,
    case: Case,
    rate: float,
    manager_plan: ManagerPlan = "hire_local",
) -> float:
    lease = run_lease(unit, card, steady_cups, case, manager_plan)
    i = (1 + rate) ** (1 / 12) - 1
    flows = list(lease.cash)
    flows[-1] += lease.end_refund
    pv = sum(c / float((1 + i) ** m) for m, c in enumerate(flows, start=1))
    return float(pv - investment(card, case).total)


def cups_needed(
    unit: Unit,
    card: CostCard,
    case: Case,
    manager_plan: ManagerPlan = "hire_local",
    price: float | None = None,
) -> int | None:
    """Fewest steady cups a day that pay the investment back within the lease (bisection); None if even
    the top of the search range doesn't."""
    rng = P.table("econ_cups_search")
    lo, hi = int(rng["low"]), int(rng["high"])

    def ok(c: int) -> bool:
        return run_lease(unit, card, c, case, manager_plan, price).payback_month is not None

    if not ok(hi):
        return None
    if ok(lo):
        return lo
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ok(mid):
            hi = mid
        else:
            lo = mid
    return hi


# ------------------------------------------------------------------ Figures


def _cups_fig(
    fid: str,
    label: str,
    cups: float | None,
    inputs: Sequence[Figure] = (),
    assumptions: tuple[str, ...] = (),
    note: str | None = None,
) -> Figure:
    return derived(
        fid,
        label,
        "cups_per_day",
        None if cups is None else round(cups),
        tool=TOOL,
        inputs=inputs,
        assumptions=assumptions,
        note=note,
    )


_PER_CUP = ("cup_price_sgd", "variable_cost_per_cup_sgd", "delivery_share", "delivery_commission", "gst_rate")
_FIXED = (
    "staff_plan",
    "local_manager_wage_sgd",
    "pwm_counter_attendant_wage_sgd",
    "cpf_employer_rate",
    "utilities_monthly_sgd",
    "other_fixed_monthly_sgd",
    "gst_rate",
)
_TAX = ("sg_cit_rate", "sg_partial_exemption")
_RAMP = ("ramp_curve",)
_ESTIMATE = "estimate: depends on build-team assumptions (ramp-up, delivery share, price)"


@dataclass(frozen=True)
class Level:
    key: str  # "300", or "owner" for the owner's own figure
    cups: int
    owner: bool
    registered: bool


@dataclass(frozen=True)
class Card:
    figures: list[Figure]
    levels: list[Level]
    reference: str  # the level key the sensitivities are for
    ramp_likely: list[float]
    ramp_bad: list[float]
    benchmarks: list[tuple[str, str, str, int | None]]  # figure id, en label, zh label, page


def unit_economics(
    unit: Unit,
    card: CostCard,
    manager_plan: ManagerPlan = "hire_local",
    owner_cups: int | None = None,
    best_shop: Figure | None = None,
) -> Card:
    """Every Figure of the unit-economics card for one unit and its cost card."""
    figs: list[Figure] = []
    add = figs.append
    s = shop(unit, manager_plan)
    price = P.param_fig("cup_price_sgd", "Menu price a cup", "SGD", "econ.price")
    add(price)
    var = derived(
        "econ.var_cost",
        "Ingredients and packaging a cup (with GST)",
        "SGD",
        round(s.variable_cost, 2),
        tool=TOOL,
        assumptions=("variable_cost_per_cup_sgd", "gst_rate"),
    )
    dlv = derived(
        "econ.delivery_cost",
        "Delivery commission a cup (averaged over all cups)",
        "SGD",
        round(s.delivery_cost, 2),
        tool=TOOL,
        assumptions=("delivery_share", "delivery_commission", "gst_rate"),
        note="build-team estimate of the delivery share",
    )
    contrib = derived(
        "econ.contribution",
        "Contribution a cup",
        "SGD",
        round(s.contribution, 2),
        tool=TOOL,
        inputs=[price, var, dlv],
        assumptions=_PER_CUP,
        note="not GST-registered: the whole price is revenue; GST on supplies is a cost",
    )
    figs += [var, dlv, contrib]

    gst_part = (s.service + s.utilities + s.other + s.base_rent) * (s.gst - 1)
    wages = derived(
        "econ.fixed.wages", "Wages with CPF a month", "SGD", round(s.wages), tool=TOOL, assumptions=_FIXED[:4]
    )
    rent = Figure(
        id="econ.fixed.rent",
        label="Rent and service charge a month",
        unit="SGD",
        value=Decimal(round(s.base_rent + s.service)),
        source=Source(
            kind=SourceKind.SIMULATED if unit.simulated else SourceKind.PUBLIC_DATA,
            ref=f"units:{unit.id}",
            note="base rent; turnover rent applies above it" if s.gto else None,
        ),
    )
    running = derived(
        "econ.fixed.running",
        "Utilities and other running costs a month",
        "SGD",
        round(s.utilities + s.other),
        tool=TOOL,
        assumptions=("utilities_monthly_sgd", "other_fixed_monthly_sgd"),
    )
    gst = derived(
        "econ.fixed.gst",
        "GST on rent, service charge and running costs (not claimable)",
        "SGD",
        round(gst_part),
        tool=TOOL,
        assumptions=("gst_rate",),
        note="a cost while the shop isn't GST-registered",
    )
    fixed = derived(
        "econ.fixed",
        "Fixed costs a month",
        "SGD",
        round(s.fixed(0)),
        tool=TOOL,
        inputs=[wages, rent, running, gst],
        assumptions=_FIXED,
    )
    figs += [wages, rent, running, gst, fixed]
    be = _cups_fig(
        "econ.breakeven",
        "Break-even cups a day",
        break_even_cups(unit, manager_plan),
        inputs=[contrib, fixed],
        assumptions=_PER_CUP + _FIXED,
    )
    add(be)

    card_l = derived("econ.card_total", "Opening cost, likely", "SGD", card.total_likely_sgd, tool=TOOL)
    card_b = derived(
        "econ.card_total_bad", "Opening cost if things go badly", "SGD", card.total_bad_sgd, tool=TOOL
    )
    inv_l, inv_b = investment(card, "likely"), investment(card, "bad")
    res = derived(
        "econ.reserve",
        "Running reserve left out (it covers the ramp-up months)",
        "SGD",
        round(inv_l.reserve),
        tool=TOOL,
        inputs=[card_l],
        assumptions=("reserve_months", "gst_rate"),
    )
    il = derived(
        "econ.investment_likely",
        "Investment, likely",
        "SGD",
        round(inv_l.total),
        tool=TOOL,
        inputs=[card_l, res],
        note="opening cost less the running reserve",
    )
    ib = derived(
        "econ.investment_bad",
        "Investment if things go badly",
        "SGD",
        round(inv_b.total),
        tool=TOOL,
        inputs=[card_b],
        note="P90 opening cost less the running reserve",
    )
    figs += [card_l, card_b, res, il, ib]

    lv_cups = [int(c) for c in P.items("econ_cups_levels")]
    levels = [Level(str(c), c, False, registered_at(unit, c, manager_plan)) for c in lv_cups]
    if owner_cups is not None and owner_cups > 0:
        levels.append(Level("owner", owner_cups, True, registered_at(unit, owner_cups, manager_plan)))
    n = lease_months(unit)
    rate = P.fnum("discount_rate_annual")
    for lv in levels:
        p = f"lvl.{lv.key}"
        sa = shop_at(unit, lv.cups, manager_plan)
        cups = (
            Figure(
                id=f"{p}.cups",
                label="Your own figure, cups a day",
                unit="cups_per_day",
                value=Decimal(lv.cups),
                source=Source(kind=SourceKind.OWNER, ref="expected_sg_cups_per_day"),
            )
            if lv.owner
            else Figure(
                id=f"{p}.cups",
                label="Cups a day",
                unit="cups_per_day",
                value=Decimal(lv.cups),
                source=P.source("econ_cups_levels"),
            )
        )
        rev = sa.revenue(lv.cups)
        e = sa.ebitda(lv.cups)
        dep = inv_l.sunk / n
        tax_m = corporate_tax(12 * (e - dep)) / 12
        lease_l = run_lease(unit, card, lv.cups, "likely", manager_plan)
        lease_b = run_lease(unit, card, lv.cups, "bad", manager_plan)
        reg_note = "GST-registered at this level (sales over the threshold)" if lv.registered else None
        r = derived(
            f"{p}.revenue", "Sales a month", "SGD", round(rev), tool=TOOL, inputs=[cups, price], note=reg_note
        )
        eb = derived(
            f"{p}.ebitda", "Store EBITDA a month", "SGD", round(e), tool=TOOL, inputs=[cups, contrib, fixed]
        )
        mg = derived(
            f"{p}.margin", "Store margin", "pct", e / rev if rev else None, tool=TOOL, inputs=[eb, r]
        )
        dp = derived(
            f"{p}.depreciation",
            "Investment spread over the lease, a month",
            "SGD",
            round(dep),
            tool=TOOL,
            inputs=[il],
            note="straight line over the lease (simplified capital allowances)",
        )
        tx = derived(
            f"{p}.tax",
            "Corporate tax a month (steady year)",
            "SGD",
            round(tax_m),
            tool=TOOL,
            inputs=[eb, dp],
            assumptions=_TAX,
            note="17% with partial exemption only; no SUTE",
        )
        nt = derived(
            f"{p}.net",
            "Profit after tax a month",
            "SGD",
            round(e - dep - tax_m),
            tool=TOOL,
            inputs=[eb, dp, tx],
        )
        pl = derived(
            f"{p}.payback_likely",
            "Payback, likely",
            "months",
            lease_l.payback_month,
            tool=TOOL,
            inputs=[il, eb],
            assumptions=_RAMP + _TAX,
            note=_ESTIMATE,
        )
        pb = derived(
            f"{p}.payback_bad",
            "Payback if things go badly",
            "months",
            lease_b.payback_month,
            tool=TOOL,
            inputs=[ib, eb],
            assumptions=_RAMP + _TAX,
            note="P90 opening cost and the slow ramp-up",
        )
        nv = derived(
            f"{p}.npv",
            f"NPV over {n} months at {rate:.0%}",
            "SGD",
            round(npv(unit, card, lv.cups, "likely", rate, manager_plan)),
            tool=TOOL,
            inputs=[il, eb],
            assumptions=("discount_rate_annual", "reinstatement_sgd") + _RAMP + _TAX,
            note=_ESTIMATE,
        )
        nvb = derived(
            f"{p}.npv_bad",
            f"NPV over {n} months at {rate:.0%}, if things go badly",
            "SGD",
            round(npv(unit, card, lv.cups, "bad", rate, manager_plan)),
            tool=TOOL,
            inputs=[ib, eb],
            assumptions=("discount_rate_annual", "reinstatement_sgd") + _RAMP + _TAX,
        )
        figs += [cups, r, eb, mg, dp, tx, nt, pl, pb, nv, nvb]

    need_l = _cups_fig(
        "econ.cups_needed_likely",
        f"Cups a day to pay back within the {n}-month lease",
        cups_needed(unit, card, "likely", manager_plan),
        inputs=[il, contrib, fixed],
        assumptions=_PER_CUP + _RAMP + _TAX,
        note=_ESTIMATE,
    )
    need_b = _cups_fig(
        "econ.cups_needed_bad",
        "Cups a day to pay back within the lease, if things go badly",
        cups_needed(unit, card, "bad", manager_plan),
        inputs=[ib, contrib, fixed],
        assumptions=_PER_CUP + _RAMP + _TAX,
        note="P90 opening cost and the slow ramp-up",
    )
    pr = P.tri("cup_price_range_sgd")
    lo_p = Figure(id="econ.price_low", label="Lower menu price", unit="SGD", value=Decimal(str(pr.low)),
                  source=P.source("cup_price_range_sgd"))
    hi_p = Figure(id="econ.price_high", label="Higher menu price", unit="SGD", value=Decimal(str(pr.high)),
                  source=P.source("cup_price_range_sgd"))
    need_lo = _cups_fig(
        "econ.cups_needed_price_low",
        "Cups a day to pay back within the lease at the lower price",
        cups_needed(unit, card, "likely", manager_plan, pr.low),
        inputs=[il, lo_p],
        assumptions=("cup_price_range_sgd",) + _RAMP + _TAX,
    )
    need_hi = _cups_fig(
        "econ.cups_needed_price_high",
        "Cups a day to pay back within the lease at the higher price",
        cups_needed(unit, card, "likely", manager_plan, pr.high),
        inputs=[il, hi_p],
        assumptions=("cup_price_range_sgd",) + _RAMP + _TAX,
    )
    figs += [need_l, need_b, lo_p, hi_p, need_lo, need_hi]
    if best_shop is not None:
        add(best_shop)

    ref = "owner" if any(lv.owner for lv in levels) else str(lv_cups[len(lv_cups) // 2])
    ref_cups = next(lv.cups for lv in levels if lv.key == ref)
    for r_ in P.items("discount_rate_sensitivity"):
        rr = float(r_)
        add(
            derived(
                f"econ.npv_at_{round(rr * 100)}",
                f"NPV over {n} months at {rr:.0%}",
                "SGD",
                round(npv(unit, card, ref_cups, "likely", rr, manager_plan)),
                tool=TOOL,
                inputs=[il],
                assumptions=("discount_rate_sensitivity", "reinstatement_sgd") + _RAMP + _TAX,
                note=f"at {ref_cups} cups a day",
            )
        )

    bench: list[tuple[str, str, str, int | None]] = []
    for b in P.items("chain_benchmarks"):
        fid = f"econ.bench.{b['id']}"
        add(
            Figure(
                id=fid,
                label=str(b["en"]),
                unit=cast(FigUnit, b["unit"]),
                value=Decimal(str(b["value"])),
                source=Source(
                    kind=SourceKind.PUBLIC_DATA,
                    ref=f"chain_benchmarks:{b['id']}",
                    url=str(b["url"]),
                    note=f"HKEX prospectus p.{b['page']}",
                    as_of=P.param("chain_benchmarks").as_of,
                ),
            )
        )
        bench.append((fid, str(b["en"]), str(b["zh"]), int(b["page"]) if b.get("page") else None))
    k = min(n, 12)
    return Card(
        figures=figs,
        levels=levels,
        reference=ref,
        ramp_likely=[round(x, 3) for x in ramp("likely", k)],
        ramp_bad=[round(x, 3) for x in ramp("bad", k)],
        benchmarks=bench,
    )


def reference_ebitda(card: Card) -> Figure | None:
    """The steady monthly EBITDA at the reference level (the owner's figure, else the middle level)."""
    return next((f for f in card.figures if f.id == f"lvl.{card.reference}.ebitda"), None)
