"""Compare funding plans (SPEC §6.4): side-by-side columns, each one full solve of the plan model.

Each column's numbers are a direct `simulate_plan` call at the slider's share, with the same seed and runs as
the slider; the partner column only once the owner says a partner is possible; the pros and cons are the
ranking words; "Choose this funding" applies a column through toggle_option and the slider's share.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent import toolkit as tk
from sim.chen import generate_chen
from tests.test_api import _run, _sign_in, client  # noqa: F401  (fixture re-export)
from tests.test_journey import Driver, _to_cost, svc  # noqa: F401  (fixture re-export)
from tools import compare as CMP
from tools import params as P
from tools import plan as PL
from tools.costs import estimate_costs
from tools.data import load_catalogue, unit_by_id
from tools.figures import SourceKind
from tools.models import FundingPlan
from tools.stats import wilson_upper

WORDS = set(CMP.PROS) | set(CMP.CONS)


@pytest.fixture(scope="module")
def feed():  # type: ignore[no-untyped-def]
    return generate_chen()


@pytest.fixture(scope="module")
def unit():  # type: ignore[no-untyped-def]
    return unit_by_id("u-tm-01")


@pytest.fixture(scope="module")
def card(unit):  # type: ignore[no-untyped-def]
    return estimate_costs(unit)


def _cols(feed: Any, card: Any, unit: Any, plan: FundingPlan, savings: str = "200000") -> dict[str, Any]:
    cols = CMP.compare_plans(
        feed, card, plan, savings_cny=Decimal(savings), unit_available_from=unit.available_from
    )
    return {c.id: c for c in cols}


def test_catalogue_defines_three_columns_from_plan_routes() -> None:
    cat = load_catalogue()
    assert [c.id for c in cat.compare] == ["setaside", "savings", "partner"]
    for c in cat.compare:
        assert c.title_en and c.title_zh and c.blurb_en and c.blurb_zh
        for rid in c.routes:
            e = cat.get(rid)
            assert e is not None and e.in_plan and e.status != "closed", rid
        assert set(c.toggles) == {"own_savings", "partner_equity"}


@pytest.mark.parametrize("partner", [False, True])
def test_each_column_is_a_direct_simulate_plan_call(feed, card, unit, partner: bool) -> None:  # type: ignore[no-untyped-def]
    plan = FundingPlan(setaside_share=Decimal("0.35"), partner_considered=partner)
    cols = _cols(feed, card, unit, plan, "300000")
    runs, seed = P.inum("mc_runs"), P.default_seed()
    expect = {
        "setaside": plan.model_copy(update={"own_savings_cny": Decimal(0)}),
        "savings": plan.model_copy(update={"own_savings_cny": Decimal(300000)}),
        "partner": plan.model_copy(update={"partner_equity_share": P.num("partner_min_local_share")}),
    }
    for cid, cplan in expect.items():
        c = cols[cid]
        if cid == "partner" and not partner:
            assert not c.open and c.result is None and c.figures() == []
            continue
        direct = PL.simulate_plan(
            feed, card, cplan, runs=runs, seed=seed, unit_available_from=unit.available_from
        )
        assert c.result is not None and c.result.seed == seed and c.result.runs == runs
        assert c.result.setaside_share == Decimal("0.35")
        assert c.open_likely is not None and c.open_likely.value == direct.open_likely_week
        assert c.open_p95 is not None and c.open_p95.value == direct.open_p95_week
        assert c.monthly is not None and c.monthly.value == direct.monthly_setaside_cny
        assert c.floor_risk is not None and c.floor_risk.value == direct.floor_risk
        k = int(round(float(direct.floor_risk) * runs))
        assert c.floor_risk_upper is not None and c.floor_risk_upper.value is not None
        assert abs(float(c.floor_risk_upper.value) - wilson_upper(k, runs)) < 1e-4
        assert c.floor_risk_upper.value >= c.floor_risk.value
        assert c.savings is not None and c.savings.value == cplan.own_savings_cny
        assert c.ownership is not None and c.ownership.value == 1 - cplan.partner_equity_share
        for f in c.figures():
            assert f.id.startswith(f"funding.compare.{cid}.") and f.source.kind == SourceKind.TOOL


def test_partner_column_shows_the_profit_share_and_gives_up_ownership(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    cols = _cols(feed, card, unit, FundingPlan(partner_considered=True))
    p = cols["partner"]
    share = P.num("partner_min_local_share")
    assert p.open and p.profit_share is not None and p.profit_share.value == share
    assert p.ownership is not None and p.ownership.value == 1 - share
    assert {"costs_profit_share", "gives_up_ownership"} <= set(p.cons)
    for cid in ("setaside", "savings"):
        assert cols[cid].profit_share is None and "keeps_ownership" in cols[cid].pros
        assert "cheapest" in cols[cid].pros  # the costs differ once the partner column runs
    # the owner's own partner share wins over the EFS minimum
    own = _cols(feed, card, unit, FundingPlan(partner_equity_share=Decimal("0.40")))["partner"]
    assert own.profit_share is not None and own.profit_share.value == Decimal("0.40")


def test_partner_column_closed_until_the_owner_says_a_partner_is_possible(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    p = _cols(feed, card, unit, FundingPlan())["partner"]
    assert not p.open and p.pros == [] and p.cons == []
    assert p.why_not == load_catalogue().get("partner_equity").eligible_when_en  # type: ignore[union-attr]
    zh = CMP.compare_plans(feed, card, FundingPlan(), savings_cny=Decimal(0), lang="zh")
    assert "合伙人" in (zh[2].why_not or "") and zh[2].title == load_catalogue().compare[2].title_zh


def test_pros_and_cons_are_ranking_words_and_catalogue_terms(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    cols = _cols(feed, card, unit, FundingPlan(partner_considered=True))
    for c in cols.values():
        assert set(c.pros) <= set(CMP.PROS) and set(c.cons) <= set(CMP.CONS)
        assert not set(c.pros) & set(c.cons)
        for term in c.terms:
            e = load_catalogue().get(term.id)
            assert e is not None and term.cost == e.cost_en and term.conditions == e.conditions_en
    # the set-aside-only column is the floor-risk reference, so it carries no floor-risk word
    assert not {"lowers_floor_risk", "raises_floor_risk"} & set(cols["setaside"].pros + cols["setaside"].cons)
    likely = {cid: c.open_likely.value for cid, c in cols.items()}
    fastest = min(likely, key=lambda k: likely[k])
    slowest = max(likely, key=lambda k: likely[k])
    assert "fastest" in cols[fastest].pros and "slowest" in cols[slowest].cons
    assert [t.id for t in cols["setaside"].terms] == ["setaside"]
    assert [t.id for t in cols["savings"].terms] == ["own_savings"]  # only what sets the column apart
    assert [t.id for t in cols["partner"].terms] == ["partner_equity"]


def test_savings_default_and_chosen_column(feed, card, unit) -> None:  # type: ignore[no-untyped-def]
    presets = tk.savings_presets()
    assert CMP.default_savings(FundingPlan(), presets) == min(v for v in presets if v > 0)
    assert CMP.default_savings(FundingPlan(own_savings_cny=Decimal(123456)), presets) == Decimal(123456)
    cols = _cols(feed, card, unit, FundingPlan(), "200000")
    assert [cid for cid, c in cols.items() if c.chosen] == ["setaside"]
    cols = _cols(feed, card, unit, FundingPlan(own_savings_cny=Decimal(200000)), "200000")
    assert [cid for cid, c in cols.items() if c.chosen] == ["savings"]
    cols = _cols(feed, card, unit, FundingPlan(own_savings_cny=Decimal(400000)), "200000")
    assert not any(c.chosen for c in cols.values())  # a different amount is not this column


# ------------------------------------------------------------------ in the journey


def _to_funding(d: Driver) -> None:
    _to_cost(d)
    d.reply("looks_right")
    assert d.state.step == "funding"


def _compare_id(d: Driver) -> str:
    ids = [k for k, v in d.state.widget_types.items() if v == "funding_compare"]
    return max(ids, key=lambda k: int(k[1:]))


def _choose(d: Driver, column: str, amount: Any = None, share: Any = None) -> None:
    """What the web sends for "Choose this funding": the column's toggles, the typed amount, the share."""
    from agent.widgets import WidgetEvent

    payload = d.widgets("funding_compare")[-1].payload
    col = next(c for c in payload.columns if c.id == column)
    toggles = [t.model_dump() for t in col.toggles]
    for t in toggles:
        if t["id"] == "own_savings" and t["on"]:
            t["amount"] = amount
    data = {"column": column, "options": toggles, "share": payload.share if share is None else share}
    d.run(event=WidgetEvent(widget_id=_compare_id(d), event="toggle_option", value=column, data=data))


def test_compare_shown_under_the_slider_with_every_figure(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_funding(d)
    types = [w.payload.type for w in d.widgets()]
    assert types.index("funding_compare") == types.index("setaside_slider") + 1
    w = d.widgets("funding_compare")[-1]
    p = w.payload
    assert [c.id for c in p.columns] == ["setaside", "savings", "partner"]
    assert p.share == float(d.state.funding.setaside_share)  # type: ignore[union-attr]
    assert p.share_fig in w.figures and p.savings_max in w.figures
    slider = d.widgets("setaside_slider")[-1]
    setaside = p.columns[0]
    rows = ("savings", "monthly", "open_likely", "open_p95", "floor_risk", "floor_risk_upper", "ownership")
    for row in rows:
        assert getattr(setaside, row) in w.figures and getattr(setaside, row) in w.display
    # the set-aside-only column is the slider's own plan: the same numbers
    assert w.figures[setaside.open_likely].value == slider.figures["plan.open_likely"].value
    assert w.figures[setaside.floor_risk].value == slider.figures["plan.floor_risk"].value
    assert setaside.chosen and p.columns[1].savings_editable and not setaside.savings_editable
    partner = p.columns[2]
    assert not partner.open and partner.why_not and partner.open_likely is None


def test_choose_savings_applies_toggle_and_amount(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_funding(d)
    _choose(d, "savings", amount="250000")
    st = d.state
    assert st.funding is not None and st.funding.own_savings_cny == Decimal(250000)
    assert st.funding.partner_equity_share == 0
    p = d.widgets("funding_compare")[-1].payload
    assert [c.id for c in p.columns if c.chosen] == ["savings"]
    assert d.widgets("funding_options"), "own savings opened to this owner: the options card re-ranked"
    assert d.widgets("setaside_slider")
    # back to set-aside only
    _choose(d, "setaside")
    assert st.funding.own_savings_cny == 0
    assert [c.id for c in d.widgets("funding_compare")[-1].payload.columns if c.chosen] == ["setaside"]


@pytest.mark.parametrize("amount", ["-1", "nan", "abc", "1e12", None])
def test_choose_savings_rejects_a_bad_amount(svc: Any, amount: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_funding(d)
    before = d.state.funding.model_copy()  # type: ignore[union-attr]
    _choose(d, "savings", amount=amount)
    assert d.state.funding == before and not d.widgets()


def test_choose_partner_only_once_the_owner_says_a_partner_is_possible(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_funding(d)
    from agent.widgets import WidgetEvent

    wid = _compare_id(d)
    opts = [{"id": "partner_equity", "on": True}, {"id": "own_savings", "on": False}]
    forged = {"options": opts, "share": 0.3}
    d.run(event=WidgetEvent(widget_id=wid, event="toggle_option", value="partner", data=forged))
    assert d.state.funding.partner_equity_share == 0 and not d.widgets()  # type: ignore[union-attr]
    # a closed or bank route can't be slipped into a column choice
    bads = ({"id": "webank_loan", "on": True}, {"id": "webank_home_wc", "on": True}, {"id": "own_savings"})
    for bad in bads:
        d.run(event=WidgetEvent(widget_id=wid, event="toggle_option", value="x", data={"options": [bad]}))
        assert not d.widgets() and d.state.funding.options_on == []  # type: ignore[union-attr]
    d.reply("partner")
    d.reply("include")
    assert d.state.funding.partner_considered  # type: ignore[union-attr]
    p = d.widgets("funding_compare")[-1].payload
    assert p.columns[2].open and p.columns[2].chosen
    _choose(d, "setaside")
    assert d.state.funding.partner_equity_share == 0  # type: ignore[union-attr]
    p = d.widgets("funding_compare")[-1].payload
    assert p.columns[2].open, "choosing another column doesn't close the partner column"
    _choose(d, "partner")
    assert d.state.funding.partner_equity_share == P.num("partner_min_local_share")  # type: ignore[union-attr]


def test_choose_applies_the_share_through_the_wall(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_funding(d)
    wall = tk.wall(d.state)
    _choose(d, "savings", amount="200000", share=1.0)
    assert d.state.funding.setaside_share <= wall  # type: ignore[union-attr]
    if wall < 1:
        assert any(w.payload.rule_id == "R5" for w in d.widgets("rule_card"))


def test_compare_preview_and_savings_range(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_funding(d)
    st = d.state
    out = tk.compare_preview(st, Decimal(400000), "zh")
    sav = next(c for c in out["columns"] if c["id"] == "savings")
    assert out["figures"][sav["savings"]]["value"] == "400000"
    assert sav["title"] == load_catalogue().compare[1].title_zh and sav["open_likely"] in out["display"]
    assert st.funding is not None and st.funding.own_savings_cny == 0, "a preview changes nothing"
    cap = CMP.savings_max(st.cost_card).value  # type: ignore[arg-type]
    assert tk.savings_in_range(st, "0") == 0 and tk.savings_in_range(st, str(cap)) == cap
    for bad in ("-5", str(cap + 1), "inf", "nan", "", None):
        assert tk.savings_in_range(st, bad) is None, bad


def test_compare_preview_api_guards(client: TestClient) -> None:  # noqa: F811
    _sign_in(client)
    _run(client, init=True)
    r = client.get("/api/preview/compare", params={"savings": "100000"})
    assert r.status_code == 409 and r.json()["detail"].startswith("no_plan_yet")
