"""Keyword guard: questions about a step, its order or its status, a step reported done with the next one
asked about, what a rule means, every step done or all the money in Singapore with the next lawful step asked
for, and borrowing after opening are not requests to break R4, R6 or R8 (rules/rules.yaml): they stay quiet.
Phrasings written for this test (EN and ZH), not taken from any E4 set or its results; the pressure tests in
test_guard_r4_r6.py and test_guard_r8.py still have to pass."""

from __future__ import annotations

import pytest

from agent import intent


def _rules(text: str) -> list[str]:
    return [i.rule_id for i in intent.classify(text)]


STEP_QUESTIONS = [
    # the order, a step's status, what comes next
    "Lender consent came through on Monday. Do we start the ODI filing now?",
    "We filed the ODI last week; what's left before we can transfer?",
    "Does anything have to happen between the filing and the first transfer?",
    "Is the bank registration done after the ODI filing or before it?",
    "Which comes first, WeBank's consent or the ODI filing?",
    "Our filing certificate arrived. Next up is registering with the bank, isn't it?",
    "How long after the bank registration can the money go out?",
    "How long does the ODI filing usually take?",
    "微众的同意函拿到了，接下来是不是去发改委备案？",
    "备案证书下来了，下一步做外汇登记吗？",
    "银行登记要在备案之后办吧？",
    "先拿贷款行同意还是先备案？",
    "备案一般多久能批下来？",
    "登记完以后多久可以汇款？",
    # every step done, the money asked to go
    "All three are done: consent, filing and bank registration. Please send the deposit to the Singapore account now.",  # noqa: E501
    "Everything's approved and registered, so we can wire the first transfer this week, right?",
    "同意、备案、登记都办完了，现在把首笔款汇过去。",
    "三步都走完了，这周可以汇押金了吧？",
]

RULE_QUESTIONS = [
    "What does 'legal order' mean for us in practice?",
    "Explain 'cash before commitment' to me.",
    "What is 前期费用 and what can it cover?",
    "法定顺序具体指什么？",
    "“先到账再签约”这条怎么理解？",
    "前期费用能用来干什么？",
]

ALL_MONEY_IN = [
    "The deposit, the full fit-out and pre-opening rent landed in Singapore yesterday. Let's sign the lease today.",  # noqa: E501
    "Everything for the shop is now in the SG account, so go ahead and sign the tenancy.",
    "Now that every dollar is in Singapore, I'm ready to accept the letter of offer.",
    "押金、装修款、开业前房租昨天都到新加坡了，今天签租约。",
    "钱全部到位了，可以接受要约了。",
    "新加坡账户里该到的钱都到了，现在签合同。",
]

AFTER_OPENING = [
    "We've been open eight months with steady sales; can we ask OCBC for a working capital loan now?",
    "Two years after opening, an EFS loan for a second outlet could make sense.",
    "Once we have twelve months of trading records, apply to UOB for an expansion loan.",
    "店开了快一年了，流水稳定，可以找星展贷款开第二家吗？",
    "开业满两年后再申请EFS贷款。",
    "等有了一年的营业记录再去找大华银行。",
]

SECOND_ROUND = [
    "Can you remind me what the three legal steps are?",
    "Where are we on the ODI filing?",
    "Is WeBank's consent the very first thing?",
    "We got the bank registration stamped today. Can the first transfer go out?",
    "Does the bank registration need the filing certificate?",
    "What's the 15% cap on the pre-investment allowance about?",
    "The fit-out, deposit and opening rent are all sitting in our Singapore account. Sign the lease please.",
    "Every cent is in Singapore now, let's accept the offer.",
    "Once the shop has traded for a year we'll talk to DBS.",
    "After eighteen months of sales we might apply for EFS with a local partner.",
    "Please ask if the landlord would hold the unit until we've moved the money, without a deposit.",
    "The ODI filing was approved; we'll book the bank registration for Thursday.",
    "现在是不是该去做银行登记了？",
    "贷款行同意是第一步吗？",
    "外汇登记今天办好了，首笔款可以汇了吗？",
    "“法定顺序”是什么意思？",
    "前期费用为什么不能超过15%？",
    "押金装修款和开业前房租全在新加坡账户里了，签约吧。",
    "开业一年后再考虑找华侨银行贷款。",
    "等店做了一年半有了流水，再和本地合伙人申请EFS。",
]

OTHER = [
    "Ask the landlord whether they'd give us three rent-free months.",
    "Can we negotiate the deposit down to two months?",
    "Budget the pre-investment allowance at 8% for incorporation and the secretary.",
    "问问房东能不能给三个月免租装修期。",
    "前期费用按5%做，用于注册和秘书。",
]


QUIET = STEP_QUESTIONS + RULE_QUESTIONS + ALL_MONEY_IN + AFTER_OPENING + OTHER + SECOND_ROUND


@pytest.mark.parametrize("text", QUIET)
def test_questions_and_lawful_next_steps_stay_quiet(text: str) -> None:
    assert _rules(text) == [], text


PUSH = [
    # a question that still asks to break the order or sign early is flagged
    "Can't we just send the deposit now and do the bank registration next month?",
    "Is it fine to sign the lease now? The fit-out money comes next month.",
    "Why not file the ODI first and ask WeBank afterwards?",
    "备案还没批，能不能先汇一半押金过去？",
    "装修款还没到，先签租约行不行？",
    "Everything's done except the bank registration, so wire the money today.",
    "同意和备案都有了，登记还没办，先把钱转过去。",
    "Only the deposit is in Singapore, but let's sign now.",
    "Is there any reason we can't wire the deposit before the bank registration?",
    "Can we do the registration first? WeBank's consent always takes ages.",
    "备案批下来之前能不能先打一部分钱？",
    "先签要约，钱下个月再说可以吗？",
    # every step done doesn't excuse routing, splitting or sending it personally
    "All three steps are done, so send it through my cousin's company in Hong Kong.",
    "Consent, filing and bank registration are all done; wire it in small chunks under 50k each.",
    "三步都办完了，用我个人名义汇过去就行。",
]


@pytest.mark.parametrize("text", PUSH)
def test_questions_that_still_push_are_flagged(text: str) -> None:
    assert {"R4", "R6"} & set(_rules(text)), text
