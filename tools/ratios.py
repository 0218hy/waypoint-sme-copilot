"""Chain ratios from the (mock) WeBank feed: "Your business at a glance" (judge-response memo §3b).

Everything is computed from one `FeedSnapshot`; no new data. Each ratio is a Figure whose inputs are the
feed Figures it was computed from. The monthly series is strongly seasonal (Chinese New Year), so the
margin trend compares the last three months with the same three months a year earlier, never month on
month. Two ratios also need the Singapore shop: the investment as a share of a year's profit, and the
shop's steady monthly profit in home shops; they are added once the cost card and unit economics exist.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from tools import params as P
from tools.figtools import derived, sourced
from tools.figures import Figure, Source, SourceKind
from tools.models import FeedSnapshot, ProfitMonth

TOOL = "chain_ratios"
TREND_MONTHS = 3  # the "last quarter" of the seasonally fair trend


def _feed_source(fs: FeedSnapshot, ref: str) -> Source:
    return Source(
        kind=SourceKind.FEED,
        ref=f"webank_feed:{ref}",
        as_of=fs.as_of,
        note="simulated feed" if fs.simulated else None,
    )


def _months(fs: FeedSnapshot) -> list[ProfitMonth]:
    return sorted(fs.profit_history, key=lambda m: m.month)


def _year_before(d: date) -> date:
    return d.replace(year=d.year - 1)


def _sum(ms: Sequence[ProfitMonth], field: str) -> Decimal:
    return sum((Decimal(getattr(m, field)) for m in ms), Decimal(0))


def _div(a: Decimal, b: Decimal) -> Decimal | None:
    return None if b == 0 else a / b


def chain_ratios(fs: FeedSnapshot) -> list[Figure]:
    """The chain's own ratios (operating margin, trend, revenue per shop, runway, debt-service cover)."""
    months = _months(fs)
    ttm = months[-12:] if len(months) >= 12 else []
    figs: list[Figure] = []

    rev = sourced(
        "feed.ttm_revenue",
        "Revenue, last 12 months",
        "CNY",
        _sum(ttm, "revenue_cny") if ttm else None,
        _feed_source(fs, "profit_history"),
    )
    prof = sourced(
        "feed.ttm_profit",
        "Operating profit, last 12 months",
        "CNY",
        _sum(ttm, "operating_profit_cny") if ttm else None,
        _feed_source(fs, "profit_history"),
    )
    shops = sourced("feed.shops", "Shops", "count", fs.shops, _feed_source(fs, "shops"))
    cash = sourced(
        "feed.cash", "Cash in the bank", "CNY", fs.cash_balance_cny, _feed_source(fs, "cash_balance")
    )
    payroll = sourced(
        "feed.payroll", "Monthly payroll", "CNY", fs.monthly_payroll_cny, _feed_source(fs, "payroll")
    )
    repay = sourced(
        "feed.repayment",
        "Monthly loan repayment",
        "CNY",
        fs.monthly_loan_repayment_cny,
        _feed_source(fs, "loan_repayment"),
    )
    commit = sourced(
        "feed.home_commitments",
        "Other monthly commitments at home",
        "CNY",
        fs.home_commitments_monthly_cny,
        _feed_source(fs, "home_commitments"),
    )
    draw = sourced(
        "feed.drawings",
        "Owner's monthly drawings",
        "CNY",
        fs.owner_drawings_monthly_cny,
        _feed_source(fs, "owner_drawings"),
    )
    figs += [rev, prof, shops, cash, payroll, repay, commit, draw]

    margin = _div(prof.value, rev.value) if ttm and rev.value is not None and prof.value is not None else None
    figs.append(
        derived(
            "ratio.op_margin_ttm",
            "Operating margin, last 12 months",
            "pct",
            margin,
            tool=TOOL,
            inputs=[prof, rev],
        )
    )

    # seasonally fair trend: the last three months against the same three months a year earlier
    recent = months[-TREND_MONTHS:]
    by_month = {m.month: m for m in months}
    year_ago = [by_month.get(_year_before(m.month)) for m in recent]
    have = len(recent) == TREND_MONTHS and all(m is not None for m in year_ago)
    ago = [m for m in year_ago if m is not None]
    hist = _feed_source(fs, "profit_history")
    q_rev = sourced(
        "feed.rev_3m", "Revenue, last 3 months", "CNY", _sum(recent, "revenue_cny") if have else None, hist
    )
    q_prof = sourced(
        "feed.profit_3m",
        "Operating profit, last 3 months",
        "CNY",
        _sum(recent, "operating_profit_cny") if have else None,
        hist,
    )
    a_rev = sourced(
        "feed.rev_3m_year_ago",
        "Revenue, same 3 months a year earlier",
        "CNY",
        _sum(ago, "revenue_cny") if have else None,
        hist,
    )
    a_prof = sourced(
        "feed.profit_3m_year_ago",
        "Operating profit, same 3 months a year earlier",
        "CNY",
        _sum(ago, "operating_profit_cny") if have else None,
        hist,
    )
    figs += [q_rev, q_prof, a_rev, a_prof]
    span = f"{recent[0].month:%b %Y} to {recent[-1].month:%b %Y}" if have else None
    figs.append(
        derived(
            "ratio.margin_recent_3m",
            "Operating margin, last 3 months",
            "pct",
            _div(q_prof.value, q_rev.value) if have and q_prof.value is not None and q_rev.value else None,
            tool=TOOL,
            inputs=[q_prof, q_rev],
            note=span,
        )
    )
    figs.append(
        derived(
            "ratio.margin_year_ago_3m",
            "Operating margin, same 3 months a year earlier",
            "pct",
            _div(a_prof.value, a_rev.value) if have and a_prof.value is not None and a_rev.value else None,
            tool=TOOL,
            inputs=[a_prof, a_rev],
            note="the series is seasonal: never compared month on month",
        )
    )

    per_shop = rev.value / 12 / Decimal(fs.shops) if rev.value is not None and fs.shops else None
    figs.append(
        derived(
            "ratio.revenue_per_shop_month",
            "Revenue per shop a month",
            "CNY",
            per_shop,
            tool=TOOL,
            inputs=[rev, shops],
            note="last 12 months / 12 / shops",
        )
    )

    outflow = fs.monthly_payroll_cny + fs.monthly_loan_repayment_cny + fs.home_commitments_monthly_cny
    figs.append(
        derived(
            "ratio.cash_runway",
            "Cash runway",
            "months",
            _div(fs.cash_balance_cny, outflow),
            tool=TOOL,
            inputs=[cash, payroll, repay, commit],
            note="overstated: home rent and suppliers are not in the feed, only payroll, loan repayments "
            "and listed commitments",
        )
    )

    monthly_profit = prof.value / 12 if prof.value is not None else None
    dscr = _div(monthly_profit, fs.monthly_loan_repayment_cny) if monthly_profit is not None else None
    dscr_after = (
        _div(monthly_profit - fs.owner_drawings_monthly_cny, fs.monthly_loan_repayment_cny)
        if monthly_profit is not None
        else None
    )
    figs.append(
        derived(
            "ratio.dscr",
            "Debt-service coverage",
            "times",
            dscr,
            tool=TOOL,
            inputs=[prof, repay],
            note="a month's operating profit (last 12 months / 12) / the monthly loan repayment",
        )
    )
    figs.append(
        derived(
            "ratio.dscr_after_drawings",
            "Debt-service coverage after drawings",
            "times",
            dscr_after,
            tool=TOOL,
            inputs=[prof, draw, repay],
            note="(a month's operating profit - the owner's drawings) / the monthly loan repayment",
        )
    )
    return figs


def singapore_ratios(
    fs: FeedSnapshot,
    investment_likely: Figure,
    investment_bad: Figure,
    sg_ebitda_monthly: Figure | None,
) -> list[Figure]:
    """The Singapore shop against the chain: the investment as a share of a year's operating profit
    (likely and if costs go badly), and the shop's steady monthly operating profit in home shops."""
    months = _months(fs)
    ttm = months[-12:] if len(months) >= 12 else []
    prof_v = _sum(ttm, "operating_profit_cny") if ttm else None
    prof = sourced(
        "feed.ttm_profit",
        "Operating profit, last 12 months",
        "CNY",
        prof_v,
        _feed_source(fs, "profit_history"),
    )
    fx = P.param_fig("fx_cny_per_sgd", "CNY per SGD", "count", "param.fx")
    rate = P.fx()

    def share(inv: Figure, fid: str, label: str) -> Figure:
        v = None if inv.value is None or not prof_v else inv.value * rate / prof_v
        return derived(
            fid,
            label,
            "pct",
            v,
            tool=TOOL,
            inputs=[inv, fx, prof],
            note="investment x FX / operating profit of the last 12 months",
        )

    out = [
        prof,
        share(
            investment_likely, "ratio.sg_investment_share", "Singapore investment, share of a year's profit"
        ),
        share(
            investment_bad,
            "ratio.sg_investment_share_bad",
            "Singapore investment if costs go badly, share of a year's profit",
        ),
    ]
    if sg_ebitda_monthly is not None:
        per_home = prof_v / 12 / Decimal(fs.shops) if prof_v is not None and fs.shops else None
        home = derived(
            "ratio.profit_per_home_shop_month",
            "Operating profit per home shop a month",
            "CNY",
            per_home,
            tool=TOOL,
            inputs=[prof],
        )
        v = (
            None
            if sg_ebitda_monthly.value is None or not per_home
            else sg_ebitda_monthly.value * rate / per_home
        )
        out += [
            home,
            derived(
                "ratio.sg_vs_home_shops",
                "The Singapore shop's monthly profit, in home shops",
                "times",
                v,
                tool=TOOL,
                inputs=[sg_ebitda_monthly, fx, home],
                note="the Singapore shop's steady monthly operating profit x FX / a home shop's",
            ),
        ]
    return out
