"""Milestone drafts (SPEC §7.4, tier T1): the lender-consent request and the step checklists.

Code builds every fact a draft states from the goal (each quantity a Figure); the model writes only
the consent request's prose, from a beat, with quantities as placeholders. Checklists come from
`data/milestone_checklists.yaml`, each item with its source. Waypoint never sends a draft: the owner
copies or downloads it and sends it himself.
"""

from __future__ import annotations

from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from agent.render import Lang
from agent.widgets import ChecklistItem, DraftCard, DraftFact, SourceNote
from tools.figtools import derived
from tools.figures import Figure
from tools.models import Goal

ROOT = Path(__file__).resolve().parents[1]
CHECKLISTS = ROOT / "data" / "milestone_checklists.yaml"
CONSENT_MUST = ["{{fig:draft.invest_total}}", "{{fig:draft.setaside_monthly}}"]


@cache
def _checklists() -> dict[str, Any]:
    return dict(yaml.safe_load(CHECKLISTS.read_text(encoding="utf-8")))


def has_draft(mid: str) -> bool:
    return mid == "lender_consent" or mid in _checklists()["checklists"]


def _source(key: str) -> SourceNote:
    s = _checklists()["sources"][key]
    return SourceNote(label=s["label"], url=s.get("url"), as_of=s.get("as_of"))


def checklist(mid: str, lang: Lang) -> DraftCard | None:
    """The checklist for a step, from data (None if the step has none)."""
    data = _checklists()
    cl = data["checklists"].get(mid)
    if cl is None:
        return None
    items = [
        ChecklistItem(id=str(it["id"]), text=str(it[lang]), who=it["who"], source=_source(str(it["source"])))
        for it in cl["items"]
    ]
    keys = list(dict.fromkeys(str(it["source"]) for it in cl["items"]))
    return DraftCard(
        kind="checklist",
        milestone_id=mid,
        title=str(cl["title"][lang]),
        who=str(cl["who"][lang]),
        items=items,
        sources=[_source(k) for k in keys],
        as_of=str(data.get("as_of", "")),
        filename=f"waypoint-checklist-{mid}.txt",
    )


def consent_figures(goal: Goal, snapshot: dict[str, Any]) -> list[Figure]:
    """The quantities the consent request states, all from the approved goal."""
    tool = "drafts.consent_request"
    card = snapshot.get("cost_card") or {}
    fx = Decimal(str(card.get("fx_cny_per_sgd"))) if card.get("fx_cny_per_sgd") is not None else None
    total = derived(
        "draft.invest_total",
        "Planned investment in Singapore (likely)",
        "SGD",
        goal.cost_total_likely_sgd,
        tool=tool,
        note="the approved goal's cost card",
    )
    figs = [
        total,
        derived(
            "draft.invest_total_cny",
            "Planned investment in RMB (likely)",
            "CNY",
            None if fx is None else goal.cost_total_likely_sgd * fx,
            tool=tool,
            inputs=[total],
            assumptions=("fx_cny_per_sgd",),
        ),
        derived(
            "draft.setaside_monthly",
            "Monthly set-aside from profit",
            "CNY",
            goal.setaside_monthly_cny,
            tool=tool,
            note="the approved goal",
        ),
        derived("draft.floor", "Home cash safety floor", "CNY", goal.floor_cny, tool=tool),
        derived("draft.open_likely", "Likely opening", "weeks", goal.target_open_likely_week, tool=tool),
    ]
    first = next((m for m in goal.milestones if m.id == "first_transfer"), None)
    if first is not None:
        figs.append(derived("draft.first_transfer", "First main transfer", "weeks", first.likely_week, tool=tool))  # noqa: E501
    if goal.funding.own_savings_cny > 0:
        figs.append(
            derived("draft.own_savings", "Owner savings put in", "CNY", goal.funding.own_savings_cny, tool=tool)  # noqa: E501
        )
    if goal.funding.partner_equity_share > 0:
        figs.append(
            derived(
                "draft.partner_share",
                "Singapore partner's equity share",
                "pct",
                goal.funding.partner_equity_share,
                tool=tool,
            )
        )
    return figs


def consent_request(goal: Goal, snapshot: dict[str, Any], unit_name: str, lang: Lang) -> tuple[list[Figure], DraftCard]:  # noqa: E501
    """The consent request's facts (code) around an empty body the model fills from a beat."""
    zh = lang == "zh"
    figs = consent_figures(goal, snapshot)
    ids = {f.id for f in figs}

    def fact(en: str, zh_: str, figure: str | None = None, text: tuple[str, str] = ("", "")) -> DraftFact:
        return DraftFact(label=zh_ if zh else en, figure=figure, text=text[1] if zh else text[0])

    facts = [
        fact(
            "What",
            "投资内容",
            text=(
                f"One leased tea shop at {unit_name}, through a new Singapore company owned by your Shenzhen company",  # noqa: E501
                f"在{unit_name}租铺开一家茶饮店，由深圳公司持股的新加坡新公司经营",
            ),
        ),
        fact("Planned investment (likely)", "计划投资额（预计）", "draft.invest_total"),
        fact("In RMB", "折合人民币", "draft.invest_total_cny"),
        fact(
            "Funded by",
            "资金来源",
            text=(
                "The company's own profit, set aside each month, and its savings. No WeBank loan money",
                "公司自有利润（每月储蓄）和积蓄，不使用任何微众银行贷款资金",
            ),
        ),
        fact("Monthly set-aside", "每月储蓄", "draft.setaside_monthly"),
    ]
    if "draft.own_savings" in ids:
        facts.append(fact("Savings put in", "投入的积蓄", "draft.own_savings"))
    if "draft.partner_share" in ids:
        facts.append(fact("Singapore partner's share", "新加坡合伙人持股", "draft.partner_share"))
    facts += [
        fact("Home cash kept above", "境内现金保持在", "draft.floor"),
        fact(
            "Guarantees",
            "担保",
            text=(
                "None: nothing in China guarantees the Singapore company",
                "无：境内不为新加坡公司提供任何担保",
            ),
        ),
        fact(
            "Order",
            "办理顺序",
            text=(
                "Your consent first, then the ODI filing and bank registration, before any money leaves China",  # noqa: E501
                "先取得贵行同意，再办理境外投资备案和银行登记，之后才会有资金汇出",
            ),
        ),
    ]
    if "draft.first_transfer" in ids:
        facts.append(fact("First main transfer (likely)", "首笔主要汇款（预计）", "draft.first_transfer"))
    facts.append(fact("Likely opening", "预计开业", "draft.open_likely"))
    facts.append(
        fact(
            "If borrowing rises",
            "如用款增加",
            text=(
                "The set-aside pauses while WeBank borrowing is above its usual level",
                "微业贷用款高于平时水平期间，储蓄暂停",
            ),
        )
    )
    card = DraftCard(
        kind="consent_request",
        milestone_id="lender_consent",
        title="同意申请（草稿）" if zh else "Consent request (draft)",
        to="微众银行，你的客户经理" if zh else "WeBank, your relationship manager",
        subject="关于境外投资的贷款人同意申请" if zh else "Request for lender consent: an outbound investment in Singapore",  # noqa: E501
        facts=facts,
        sources=[_source("loan_2024")],
        filename="waypoint-consent-request.txt",
    )
    return figs, card
