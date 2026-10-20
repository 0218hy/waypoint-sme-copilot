"""Per-rule lawful alternatives that work at every step (judge-response memo §1c, §1d).

Each rule lists its own alternatives in rules/rules.yaml. A lever (changes the plan) applies at the funding
step, or reopens funding from a later step with the change applied; a cards view shows the funding cards
(WeBank at home, after opening); a topic shows anywhere. Before funding is reached, a lever says it comes at
that step.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from agent import toolkit as tk
from agent.widgets import WidgetEvent
from rules.engine import rule_ids
from tests.test_journey import Driver, _to_cost, _to_goal_plan, svc  # noqa: F401  (fixture re-export)
from tools.data import load_rules_yaml

ACTIONS = {"lever", "cards", "topic"}


def _alts(rid: str) -> list[str]:
    return [str(x) for x in load_rules_yaml()["rules"][rid]["alternatives"]]


def test_every_rule_lists_at_least_two_defined_alternatives() -> None:
    topics = set(tk._topics())
    vocab = load_rules_yaml()["alternatives"]
    for rid in rule_ids():
        alts = _alts(rid)
        assert len(alts) >= 2 and len(set(alts)) == len(alts), rid
        for a in alts:
            spec = vocab[a]
            assert spec["action"] in ACTIONS, a
            assert spec["label_en"] and spec["label_zh"], a
            if spec["action"] == "topic":
                assert spec["topic"] in topics, a
    used = {a for rid in rule_ids() for a in _alts(rid)}
    assert used == set(vocab), "every alternative is offered by some rule"


def test_memo_examples_are_the_rules_own() -> None:
    assert {"raise_share", "add_savings", "webank_home"} <= set(_alts("R1"))
    assert _alts("R4")[:2] == ["pre_investment", "start_filing"]
    assert {"rent_free", "staged_contractor", "later_lease"} <= set(_alts("R6"))
    assert _alts("R8")[:2] == ["partner", "after_opening"]


def test_lawful_options_are_rule_specific_and_bilingual(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    st = d.state
    r1 = [o.value for o in tk.lawful_options(st, "R1", "en")]
    r4 = [o.value for o in tk.lawful_options(st, "R4", "en")]
    assert r1 == _alts("R1") and r4 == _alts("R4") and r1 != r4
    zh = tk.lawful_options(st, "R6", "zh")
    assert [o.value for o in zh] == _alts("R6") and all(o.label != o.value for o in zh)


def _rule_card(d: Driver, rid: str) -> Any:
    cards = [c for c in d.widgets("rule_card") if c.payload.rule_id == rid]
    assert cards, f"no {rid} card"
    return cards[-1]


def _pick(d: Driver, card: Any, value: str) -> None:
    assert value in [o.value for o in card.payload.options]
    d.run(event=WidgetEvent(widget_id=card.id, event="select_option", value=value, data={"id": value}))


def test_card_shows_the_rules_own_options(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_cost(d)
    d.run(text="Send the money to Singapore before the ODI filing is done")
    assert [o.value for o in _rule_card(d, "R4").payload.options] == _alts("R4")


def test_a_lever_before_funding_waits_for_that_step(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_cost(d)
    pending = d.state.pending.slot  # type: ignore[union-attr]
    d.run(text="Just use my WeBank line for now")
    _pick(d, _rule_card(d, "R1"), "raise_share")
    assert d.state.step == "cost" and d.state.funding is None
    assert any(o.beat is not None and o.beat.key == "alternative_later" for o in d.outs)
    assert d.state.pending is not None and d.state.pending.slot == pending


def test_a_topic_shows_at_any_step(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_cost(d)
    d.run(text="Send the money to Singapore before the ODI filing is done")
    _pick(d, _rule_card(d, "R4"), "start_filing")
    assert [w.payload.topic_id for w in d.widgets("topic_card")] == ["T-LENDER-CONSENT"]
    assert d.state.step == "cost"


def test_a_lever_from_the_plan_step_reopens_funding_with_the_change(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_goal_plan(d)
    assert d.state.funding is not None and d.state.funding.confirmed
    share = d.state.funding.setaside_share
    wall = tk.wall(d.state)
    d.run(text="Just use my WeBank line for now")
    _pick(d, _rule_card(d, "R1"), "raise_share")
    assert d.state.step == "funding" and not d.state.funding.confirmed
    assert d.state.funding.setaside_share == min(share + Decimal("0.10"), wall)
    assert d.widgets("setaside_slider")  # funding re-entered and simulated with the change
    assert d.state.pending is not None and d.state.pending.slot == "lever"
    d.reply("looks_good")
    assert d.state.step == "goal_plan"


def test_add_savings_from_the_plan_step_asks_the_amount_at_funding(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_goal_plan(d)
    d.run(text="Just use my WeBank line for now")
    _pick(d, _rule_card(d, "R1"), "add_savings")
    assert d.state.step == "funding"
    assert d.state.pending is not None and d.state.pending.slot == "savings"
    d.reply(d.state.pending.options[-1]["value"])
    assert d.state.funding is not None and d.state.funding.own_savings_cny > 0


def test_cards_alternative_shows_the_after_opening_view_and_it_never_counts(svc: Any) -> None:  # noqa: F811
    d = Driver(svc)
    _to_cost(d)
    d.reply("looks_right")
    d.run(text="Can I get a DBS loan before we open?")
    _pick(d, _rule_card(d, "R8"), "after_opening")
    fo = d.widgets("funding_options")[-1].payload
    efs = {c.id: c for c in fo.later_cards}["efs_after_opening"]
    assert efs.status == "later" and efs.variant == "after_opening"
    assert "no trading-history test" in efs.conditions
    assert d.state.pending is not None and d.state.pending.slot == "lever"
    d.event("funding_options", "toggle_option", True, {"id": "efs_after_opening", "on": True})
    assert [c.payload.rule_id for c in d.widgets("rule_card")] == ["R8"]
    assert d.state.funding is not None and d.state.funding.options_on == []


def test_partner_after_the_goal_reopens_funding(svc: Any) -> None:  # noqa: F811
    from tests.test_journey import _approve

    d = Driver(svc)
    _to_goal_plan(d)
    _approve(d)
    assert d.state.goal_id is not None
    d.run(text="Can I get a DBS loan before we open?")
    _pick(d, _rule_card(d, "R8"), "partner")
    assert d.state.step == "funding" and d.state.revising
    assert d.state.pending is not None and d.state.pending.slot == "partner"


@pytest.mark.parametrize("value", ["klingon", "efs_grants", "raise_share'"])
def test_an_option_no_rule_offers_is_ignored(svc: Any, value: str) -> None:  # noqa: F811
    d = Driver(svc)
    _to_goal_plan(d)
    d.run(text="Just use my WeBank line for now")
    card = _rule_card(d, "R1")
    before = d.state.funding.model_dump()  # type: ignore[union-attr]
    d.run(event=WidgetEvent(widget_id=card.id, event="select_option", value=value, data={"id": value}))
    assert d.state.step == "goal_plan" and d.state.funding.model_dump() == before  # type: ignore[union-attr]
