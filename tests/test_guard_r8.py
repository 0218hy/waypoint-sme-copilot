"""Keyword guard for R8 (no Singapore borrowing before opening), no model. Phrasings written for this test
from R8's text in rules/rules.yaml: Singapore banks, EFS and other Singapore lenders, before opening, in
English and Chinese. Not the E4 scripts (eval/e4_guard.py was not read). Borrowing after opening is a
lawful option, and asking who qualifies is learning, so both stay quiet."""

from __future__ import annotations

import pytest

from agent import intent


def _rules(text: str) -> list[str]:
    return [i.rule_id for i in intent.classify(text)]


PRESSURE = [
    # Singapore banks
    "Let's get a DBS loan to pay the deposit.",
    "Can OCBC lend us the money for the fit-out?",
    "We could use a working capital loan from UOB to bridge the gap.",
    "Put a Maybank overdraft into the plan for pre-opening rent.",
    "Just ask a Singapore bank for 150k and we can sign next month.",
    "Our relationship manager at Standard Chartered says they'd finance the renovation, put that in.",
    "我们找星展贷一笔款付押金吧。",
    "开业前先在新加坡贷款把装修做了。",
    "新加坡公司直接向当地银行借钱。",
    "让华侨银行给新店开个透支额度。",
    # EFS and government schemes
    "Apply for EFS so we can start the renovation.",
    "Count on an Enterprise Singapore loan for the set-up costs.",
    "Add a government-backed SME loan to cover the shortfall.",
    "申请企业融资计划补贴前期费用。",
    "把企业发展局的贷款算进开店资金里。",
    "EFS贷款拿来付押金就行了。",
    # other Singapore lenders
    "The Singapore company will borrow 200k locally to get started.",
    "Equipment financing for the tea machines in Singapore, then we don't need so much savings.",
    "Use hire purchase for the kitchen kit before we open.",
    "An online SME lender there can give us 80k for the fit-out quickly.",
    "用新加坡那边的设备融资买机器。",
    "找当地的贷款公司借点钱先开起来。",
    "新加坡有网贷平台，借一笔给装修。",
    "装修款用狮城的财务公司分期付。",
]

BENIGN = [
    "After we open and have a year of trading, can we apply for a DBS loan?",
    "Does EFS need 30% local ownership?",
    "Why can't we take a Singapore bank loan before opening?",
    "Once the shop is open, a local bank loan could fund the second outlet.",
    "We will repay the WeBank loan from profits.",
    "Is the fit-out quote in Singapore dollars?",
    "开业以后可以申请新加坡的银行贷款吗？",
    "EFS贷款需要本地持股吗？",
    "为什么开业前不能在新加坡贷款？",
    "有了经营记录之后再找星展谈贷款。",
    "装修大概要多久？",
    "我们用自己的储蓄出资。",
]


@pytest.mark.parametrize("text", PRESSURE)
def test_r8_pressure_is_flagged(text: str) -> None:
    assert "R8" in _rules(text), text


@pytest.mark.parametrize("text", BENIGN)
def test_r8_lawful_or_learning_stays_quiet(text: str) -> None:
    assert _rules(text) == [], text


def test_a_singapore_loan_is_r8_not_r1_unless_webank_is_named() -> None:
    assert _rules("Let's get a DBS loan to pay the deposit.") == ["R8"]
    assert "R1" in _rules("Use my WeBank loan for the Singapore deposit.")


def test_after_opening_does_not_excuse_a_pre_opening_cost() -> None:
    assert "R8" in _rules("Borrow from DBS for the fit-out, we'll repay it after we open.")
