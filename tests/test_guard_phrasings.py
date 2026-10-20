"""Keyword guard coverage (SPEC §4.4), no model. Phrasings written from the rule descriptions in
rules/rules.yaml, in English and Chinese, plus benign controls that must stay quiet. These are not the
E4 evaluation scripts (eval/e4_guard.py); E4 is not re-measured by these tests."""

from __future__ import annotations

import pytest

from agent import intent


def _rules(text: str) -> list[str]:
    return [i.rule_id for i in intent.classify(text)]


@pytest.mark.parametrize(
    "text,rule",
    [
        # R1: loan money stays home
        ("Put the loan money into the Singapore company for now.", "R1"),
        ("Borrow from the bank line to cover the shop deposit.", "R1"),
        ("Can the credit line pay for the renovation over there in Singapore?", "R1"),
        ("Move some borrowed money into the savings pot.", "R1"),
        ("先把贷款的钱打到新加坡公司", "R1"),
        ("从银行额度里拿钱付新店押金", "R1"),
        # R2: no borrowing to free up profit
        ("Let the loan cover payroll so the profits can go to Singapore.", "R2"),
        ("Pay the suppliers with borrowed money and send our cash abroad.", "R2"),
        ("Send the profits to Singapore and borrow to pay the wages.", "R2"),
        ("用贷款付货款，把利润转去新加坡", "R2"),
        # R3: no guarantee from home
        ("Could my Shenzhen company co-sign the Singapore lease?", "R3"),
        ("I can stand surety for the Singapore company myself.", "R3"),
        ("深圳公司给新加坡那边兜底", "R3"),
        # R4: legal order
        ("Wire the deposit now and we'll do the ODI paperwork later.", "R4"),
        ("Transfer the money before the filing is approved.", "R4"),
        ("Route the funds via Hong Kong to save time.", "R4"),
        ("Pay the deposit out of the pre-investment allowance.", "R4"),
        ("Keep each transfer under the limit so nobody asks.", "R4"),
        ("I'll just send my savings myself from my personal account.", "R4"),
        ("先把钱汇过去，备案以后再补", "R4"),
        ("还没备案就先汇款吧", "R4"),
        ("用前期费用付押金", "R4"),
        ("钱走香港转一下", "R4"),
        ("分几次去换汇", "R4"),
        ("以个人名义汇过去", "R4"),
        # R5: a safe home floor
        ("Ignore the safety line, put everything into the pot.", "R5"),
        ("We don't need a buffer at home.", "R5"),
        ("Send all of our home cash to Singapore.", "R5"),
        ("不要安全线了", "R5"),
        ("把全部现金汇去新加坡", "R5"),
        # R6: cash before commitment
        ("Lock in the lease today, the money can follow.", "R6"),
        ("Sign the offer for the unit before the money arrives.", "R6"),
        ("先把租约签了，钱后面再说", "R6"),
        ("钱还没到就签合同吧", "R6"),
        # R7: capital from savings only
        ("I'll put my share on my credit cards.", "R7"),
        ("I'll borrow from my brother for my part of the capital.", "R7"),
        ("用借呗凑一下出资", "R7"),
        ("找亲戚借点钱当本金", "R7"),
        ("刷信用卡付装修", "R7"),
        # R8: no Singapore borrowing before opening
        ("Can a Singapore bank lend us the money for the renovation?", "R8"),
        ("Take a DBS loan to pay for the fit-out.", "R8"),
        ("开业前找新加坡银行借款装修", "R8"),
    ],
)
def test_new_phrasings_flag_their_rule(text: str, rule: str) -> None:
    assert rule in _rules(text), _rules(text)


@pytest.mark.parametrize(
    "text",
    [
        "We buy our tea from a supplier in Hong Kong.",
        "Hong Kong customers love our milk tea.",
        "We ship tea samples through Hong Kong.",
        "我们从香港的供应商进茶叶。",
        "Our WeBank loan repayments are always on time.",
        "We repay the loan from the Shenzhen shops before we open in Singapore.",
        "每月按时还微业贷。",
        "What deposit does a Singapore landlord usually ask for?",
        "My savings will cover part of the deposit.",
        "Our customers pay by credit card.",
        "When can I sign the lease?",
        "We'll sign the lease after the money arrives.",
        "Why is the safety line grey?",
        "What happens if home cash dips below the floor?",
        "After we open, could a DBS loan help with a second shop?",
        "The product guarantee period is a year.",
        "How long does the ODI filing take?",
        "Our shops in Shenzhen are busy at lunch.",
        "我想在学生多的地方开店",
    ],
)
def test_benign_text_stays_quiet(text: str) -> None:
    assert _rules(text) == [], _rules(text)


def test_singapore_bank_loan_alone_is_r8_and_home_loan_is_r1() -> None:
    assert _rules("Get a Singapore bank loan for the fit-out first.") == ["R8"]
    assert "R1" in _rules("Put the loan money into the Singapore company for now.")
    assert "R8" not in _rules("Put the loan money into the Singapore company for now.")
