from __future__ import annotations

from decimal import Decimal

import pytest

from rules.engine import check_action, check_funding_source, check_plan, is_recommendable, rule, rule_ids
from sim.chen import generate_chen
from tools.costs import estimate_costs
from tools.data import unit_by_id
from tools.funding import closed_options
from tools.models import FundingPlan, PlanChart, PlanResult

CHAIN = ["lender_consent", "odi_filing", "bank_registration"]


def _ids(vs: list) -> set[str]:  # type: ignore[type-arg]
    return {v.rule_id for v in vs}


def _result(floor_risk: str = "0.03", **weeks: int) -> PlanResult:
    w = {
        "lender_consent": 3,
        "odi_filing": 12,
        "bank_registration": 16,
        "incorporate": 24,
        "setup_transfer": 24,
        "first_transfer": 30,
        "sign_lease": 31,
        "fitout": 41,
        "licence": 44,
        "opening": 50,
    }
    w.update(weeks)
    chart = PlanChart(
        weeks=[],
        pot_p10=[],
        pot_p50=[],
        pot_p90=[],
        need=[],
        home_p05=[],
        home_p50=[],
        floor=[],
        milestones=[],
    )
    return PlanResult(
        setaside_share=Decimal("0.4"),
        open_likely_week=50,
        open_p95_week=70,
        floor_risk=Decimal(floor_risk),
        opened_share=Decimal(1),
        wall_share=Decimal("0.45"),
        monthly_setaside_cny=Decimal(84000),
        gap_cny=Decimal(1200000),
        milestone_weeks=w,
        chart=chart,
        runs=1000,
        seed=1,
    )


@pytest.fixture(scope="module")
def card():  # type: ignore[no-untyped-def]
    return estimate_costs(unit_by_id("u-tm-01"))


def test_rules_yaml_has_r1_to_r8_with_bilingual_text() -> None:
    assert rule_ids() == [f"R{i}" for i in range(1, 9)]
    for rid in rule_ids():
        r = rule(rid)
        for f in (
            "title_en",
            "title_zh",
            "message_en",
            "message_zh",
            "consequence_en",
            "consequence_zh",
            "source",
            "checks",
        ):
            assert r[f], (rid, f)


def test_clean_plan_passes(card) -> None:  # type: ignore[no-untyped-def]
    assert check_plan(FundingPlan(), _result(), card, None, generate_chen()) == []


# ------------------------------------------------------------------ R1


def test_r1_loan_transfer_blocked_and_operating_allowed() -> None:
    bad = {"type": "transfer", "from_account_type": "loan", "destination": "singapore", "completed": CHAIN}
    assert "R1" in _ids(check_action(bad))
    assert "R1" in _ids(check_action({"type": "recurring_setaside", "from_account_type": "loan"}))
    ok = {
        "type": "transfer",
        "from_account_type": "operating",
        "destination": "singapore",
        "completed": CHAIN,
    }
    assert check_action(ok) == []
    assert "R1" not in _ids(
        check_action({"type": "transfer", "from_account_type": "loan", "destination": "home"})
    )


def test_r1_plan_option() -> None:
    assert "R1" in _ids(check_plan(FundingPlan(options_on=["webank_loan"])))
    assert "R1" in _ids(check_funding_source("weilidai"))
    assert check_funding_source("spare_cash") == []


# ------------------------------------------------------------------ R2


def test_r2_action_while_above_normal() -> None:
    a = {"type": "recurring_setaside", "from_account_type": "operating", "loan_above_normal": True}
    assert "R2" in _ids(check_action(a))
    assert check_action({**a, "loan_above_normal": False}) == []


def test_r2_feed_notice_is_non_blocking(card) -> None:  # type: ignore[no-untyped-def]
    feed = generate_chen()
    hot = feed.model_copy(update={"loan_balance_cny": feed.loan_balance_cny + Decimal(400000)})
    vs = check_plan(FundingPlan(), _result(), card, None, hot)
    assert _ids(vs) == {"R2"} and is_recommendable(vs)
    assert check_plan(FundingPlan(), _result(), card, None, feed) == []


# ------------------------------------------------------------------ R3


@pytest.mark.parametrize(
    "kind,guarantor",
    [
        ("corporate_guarantee", "company"),
        ("personal_guarantee", "owner_personal"),
        ("standby_letter_of_credit", "company"),
        ("sblc", "company"),
        ("keep_well", "company"),
        ("share_pledge", "owner"),
        ("guarantee", "company"),
        ("comfort_letter", "company"),
    ],
)
def test_r3_every_china_guarantee_variant_denied(kind: str, guarantor: str) -> None:
    assert "R3" in _ids(check_action({"type": kind, "guarantor": guarantor}))


@pytest.mark.parametrize(
    "oid",
    [
        "china_guarantee",
        "china_guarantee_company",
        "china_guarantee_owner",
        "china_standby_lc",
        "china_keep_well",
        "china_share_pledge",
    ],
)
def test_r3_catalogue_variants_closed(oid: str) -> None:
    assert _ids(check_funding_source(oid)) == {"R3"}
    assert "R3" in _ids(check_plan(FundingPlan(options_on=[oid])))


def test_r3_negative_singapore_partner_guarantee_is_not_from_china() -> None:
    assert (
        check_action({"type": "guarantee", "guarantor": "local_partner", "guarantor_location": "singapore"})
        == []
    )
    assert "R3" in _ids(
        check_action({"type": "guarantee", "guarantor": "owner", "guarantor_location": "singapore"})
    )


# ------------------------------------------------------------------ R4


def test_r4_transfer_before_legal_steps() -> None:
    for done in ([], ["lender_consent"], ["lender_consent", "odi_filing"]):
        a = {
            "type": "transfer",
            "from_account_type": "operating",
            "destination": "singapore",
            "completed": done,
        }
        assert "R4" in _ids(check_action(a))
    ok = {
        "type": "transfer",
        "from_account_type": "operating",
        "destination": "singapore",
        "completed": CHAIN,
    }
    assert "R4" not in _ids(check_action(ok))
    # saving into his own pot at home is not a transfer to Singapore
    assert check_action({"type": "transfer", "from_account_type": "operating", "destination": "pot"}) == []


def test_r4_pre_investment_allowance() -> None:
    base = {
        "type": "transfer",
        "destination": "singapore",
        "purpose": "pre_investment",
        "completed": ["lender_consent"],
        "amount_cny": 100000,
        "planned_total_cny": 1700000,
        "covers": ["incorporation"],
    }
    assert check_action(base) == []
    assert "R4" in _ids(check_action({**base, "amount_cny": 300000}))
    assert "R4" in _ids(check_action({**base, "covers": ["security_deposit"]}))
    assert "R4" in _ids(check_action({**base, "completed": []}))


def test_r4_plan_checks(card) -> None:  # type: ignore[no-untyped-def]
    assert "R4" in _ids(check_plan(FundingPlan(pre_investment_cny=Decimal(900000)), None, card))
    assert "R4" in _ids(
        check_plan(
            FundingPlan(pre_investment_cny=Decimal(1000), pre_investment_covers=["security_deposit"]),
            None,
            card,
        )
    )
    assert (
        check_plan(
            FundingPlan(pre_investment_cny=Decimal(100000), pre_investment_covers=["incorporation"]),
            None,
            card,
        )
        == []
    )
    assert "R4" in _ids(check_plan(FundingPlan(), _result(setup_transfer=10), card))


# ------------------------------------------------------------------ R5


def test_r5_floor_risk_limit(card) -> None:  # type: ignore[no-untyped-def]
    assert "R5" in _ids(check_plan(FundingPlan(), _result("0.051"), card))
    assert "R5" not in _ids(check_plan(FundingPlan(), _result("0.05"), card))


# ------------------------------------------------------------------ R6


def test_r6_sign_lease_action() -> None:
    assert "R6" in _ids(
        check_action({"type": "sign_lease", "funds_in_singapore_sgd": 100000, "required_sgd": 200000})
    )
    assert "R6" in _ids(check_action({"type": "sign_lease"}))  # unknown funds: missing != enough
    assert (
        check_action({"type": "sign_lease", "funds_in_singapore_sgd": 200000, "required_sgd": 200000}) == []
    )


def test_r6_plan_order(card) -> None:  # type: ignore[no-untyped-def]
    assert "R6" in _ids(check_plan(FundingPlan(), _result(sign_lease=29), card))
    assert "R6" not in _ids(check_plan(FundingPlan(), _result(sign_lease=31), card))


# ------------------------------------------------------------------ R7


@pytest.mark.parametrize("src", ["personal_loan", "consumer_loan", "credit_card", "card_advance"])
def test_r7_borrowed_capital_denied(src: str) -> None:
    a = {"type": "capital_injection", "source": src, "destination": "pot"}
    assert "R7" in _ids(check_action(a))


def test_r7_negative_and_plan() -> None:
    assert check_action({"type": "capital_injection", "source": "savings", "destination": "pot"}) == []
    assert "R7" in _ids(check_plan(FundingPlan(own_savings_cny=Decimal(1), own_savings_source="borrowed")))
    assert "R7" not in _ids(check_plan(FundingPlan(own_savings_cny=Decimal(1))))
    assert "R7" in _ids(check_funding_source("consumer_loan"))


# ------------------------------------------------------------------ R8


def test_r8_singapore_borrowing() -> None:
    assert "R8" in _ids(check_action({"type": "sg_loan", "opened": False}))
    assert "R8" in _ids(check_action({"type": "efs_loan", "opened": True, "local_ownership": 0.1}))
    assert check_action({"type": "efs_loan", "opened": True, "local_ownership": 0.3}) == []
    assert "R8" in _ids(check_action({"type": "grant", "local_ownership": 0.0}))
    assert check_action({"type": "grant", "local_ownership": 0.35}) == []
    assert "R8" in _ids(check_plan(FundingPlan(options_on=["sg_bank_loan"])))
    # the after-opening view (EFS, bank SME loans) is never counted in the plan, partner or not
    assert "R8" in _ids(check_plan(FundingPlan(options_on=["efs_after_opening"])))
    assert "R8" in _ids(
        check_plan(FundingPlan(options_on=["efs_after_opening"], partner_equity_share=Decimal("0.3")))
    )


def test_closed_options_cite_their_rules() -> None:
    co = {c.id: c for c in closed_options()}
    assert co["webank_loan"].rule_id == "R1" and co["china_guarantee"].rule_id == "R3"
    assert co["personal_loan"].rule_id == "R7" and co["sg_bank_loan"].rule_id == "R8"
    assert all(c.source for c in co.values())
    assert closed_options("zh")[0].reason != co[closed_options("zh")[0].id].reason


def test_own_savings_states_the_lawful_channel_with_its_source() -> None:
    from tools.data import load_catalogue

    o = load_catalogue().get("own_savings")
    assert o is not None and o.rule_ids[0] == "R7"
    assert "Shenzhen company" in o.conditions_en and "never sent personally" in o.conditions_en
    assert "深圳公司" in o.conditions_zh and "个人名义" in o.conditions_zh
    assert o.source and "ODI" in o.source and "个人外汇管理办法" in o.source


def test_every_rule_has_a_kind_and_a_url() -> None:
    """A WeBank compliance reader can tell the law from Waypoint's own rules, and open the source."""
    for rid in rule_ids():
        r = rule(rid)
        assert r.get("kind") in ("law", "design", "law+design"), rid
        assert str(r.get("url", "")).startswith("https://"), rid
    assert rule("R1")["kind"] == "law" and "Art. 24(三)" in rule("R1")["source"]
    assert "Art. 30" in rule("R1")["source"] and "1 Jul 2024" in rule("R1")["source"]
    assert rule("R3")["kind"] == "design" and "SAFE registration" in rule("R3")["consequence_en"]
    assert rule("R8")["kind"] == "design" and "no trading-history test" in rule("R8")["source"]
    assert rule("R7")["kind"] == "law+design"
    assert "Art. 6" in rule("R2")["source"] and "39号" in rule("R2")["source"]
    assert "substitution" in rule("R2")["consequence_en"]
    assert "Art. 27 para 2" in rule("R4")["source"]


def test_violations_and_closed_routes_carry_the_kind() -> None:
    v = check_funding_source("webank_loan")[0]
    assert v.source_kind == "law" and v.source_url
    co = {c.id: c for c in closed_options()}
    assert co["china_guarantee"].source_kind == "design" and co["webank_loan"].source_kind == "law"


def test_catalogue_legal_notes_have_a_kind_and_url() -> None:
    from tools.data import load_catalogue

    for o in load_catalogue().options:
        if o.source:
            assert o.source_kind in ("law", "design", "law+design"), o.id
            assert (o.source_url or "").startswith("https://"), o.id
    own = load_catalogue().get("own_savings")
    assert own is not None and "实施细则" in (own.source or "") and "Art. 2" in (own.source or "")
