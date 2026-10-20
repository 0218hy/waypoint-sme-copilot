"""Rules engine (SPEC §8.1): R1-R8 over funding plans, plan results, prepared actions and funding routes.

Code decides; the messages and sources come from rules/rules.yaml. A blocking violation means the plan or
action can't be recommended or prepared. R2 on a plan is a notice (non-blocking): the plan model already
pauses set-asides while borrowing is above normal; the notice says why.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from tools import params as P
from tools.data import load_catalogue, load_rules_yaml
from tools.funding import loan_excess_cny, r2_paused
from tools.models import CostCard, FeedSnapshot, FundingPlan, PlanResult, Profile, Violation

SG_DESTINATIONS = {"singapore", "sg", "sg_company", "pot", "savings_pot"}
CHAIN_ORDER = ("lender_consent", "odi_filing", "bank_registration", "setup_transfer", "first_transfer")
SG_LOAN_TYPES = {"sg_loan", "sg_bank_loan", "efs_loan", "bank_loan_sg", "efs"}


def rule(rule_id: str) -> dict[str, Any]:
    r = load_rules_yaml()["rules"].get(rule_id)
    if r is None:
        raise KeyError(f"unknown rule {rule_id!r}")
    return dict(r)


def rule_ids() -> list[str]:
    return list(load_rules_yaml()["rules"])


def violation(rule_id: str, obj: str, detail: str = "", blocking: bool = True) -> Violation:
    r = rule(rule_id)
    return Violation(
        rule_id=rule_id,
        blocking=blocking,
        object=obj,
        title_en=r["title_en"],
        title_zh=r["title_zh"],
        message_en=r["message_en"],
        message_zh=r["message_zh"],
        consequence_en=r["consequence_en"],
        consequence_zh=r["consequence_zh"],
        source=r["source"],
        source_url=r.get("url"),
        source_kind=r.get("kind"),
        detail=detail,
    )


def blocking(vs: Sequence[Violation]) -> list[Violation]:
    return [v for v in vs if v.blocking]


def is_recommendable(vs: Sequence[Violation]) -> bool:
    return not blocking(vs)


# ------------------------------------------------------------------ funding routes


def check_funding_source(option_id: str) -> list[Violation]:
    """A closed route (or any of its variants, e.g. a keep-well from China) returns its rule(s)."""
    entry = load_catalogue().get(option_id)
    if entry is None or entry.status != "closed":
        return []
    return [violation(r, "funding_source", f"closed route: {option_id}") for r in entry.rule_ids]


def check_plan_route(option_id: str) -> list[Violation]:
    """A route counted in the Singapore plan that must stay out of it (e.g. WeBank working capital for the
    home shops: counting it toward Singapore is loan money funding Singapore, R1)."""
    entry = load_catalogue().get(option_id)
    if entry is None or entry.in_plan or entry.never_in_plan is None:
        return []
    return [violation(entry.never_in_plan, "funding_plan", f"{option_id} counted toward Singapore")]


# ------------------------------------------------------------------ plans


def _check_r4_plan(plan: FundingPlan, card: CostCard | None) -> list[Violation]:
    out: list[Violation] = []
    if plan.pre_investment_cny > 0:
        if "security_deposit" in plan.pre_investment_covers:
            out.append(violation("R4", "funding_plan", "前期费用 can't pay the lease deposit"))
        if card is not None:
            cap = card.total_likely_sgd * card.fx_cny_per_sgd * P.num("pre_investment_cap_share")
            if plan.pre_investment_cny > cap:
                out.append(
                    violation("R4", "funding_plan", f"前期费用 {plan.pre_investment_cny} above cap {cap:.0f}")
                )
    return out


def _check_order(result: PlanResult) -> list[Violation]:
    out: list[Violation] = []
    w = result.milestone_weeks
    present = [(k, w[k]) for k in CHAIN_ORDER if k in w]
    for (a, wa), (b, wb) in zip(present, present[1:], strict=False):
        if wb < wa:
            out.append(violation("R4", "plan_result", f"{b} (week {wb}) before {a} (week {wa})"))
    if "sign_lease" in w:
        if "first_transfer" not in w:
            out.append(violation("R6", "plan_result", "lease signed with no first main transfer"))
        elif w["sign_lease"] < w["first_transfer"]:
            out.append(violation("R6", "plan_result", "lease signed before the first main transfer"))
    return out


def check_plan(
    plan: FundingPlan,
    result: PlanResult | None = None,
    card: CostCard | None = None,
    profile: Profile | None = None,
    feed: FeedSnapshot | None = None,
) -> list[Violation]:
    out: list[Violation] = []
    for oid in plan.options_on:
        out += check_funding_source(oid)
        out += check_plan_route(oid)  # e.g. home working capital (R1) or the after-opening view (R8)
    if plan.own_savings_cny > 0 and plan.own_savings_source == "borrowed":
        out.append(violation("R7", "funding_plan", "own capital comes from borrowing"))
    out += _check_r4_plan(plan, card)
    if result is not None:
        if result.floor_risk > P.num("floor_risk_limit"):
            out.append(violation("R5", "plan_result", f"floor risk {result.floor_risk} above the limit"))
        out += _check_order(result)
    if feed is not None and r2_paused(feed):
        out.append(violation("R2", "feed", f"borrowing {loan_excess_cny(feed)} above normal", blocking=False))
    return out


# ------------------------------------------------------------------ prepared actions


def _vocab(key: str) -> set[str]:
    return {str(x) for x in load_rules_yaml()[key]}


def _truthy(a: Mapping[str, Any], key: str) -> bool:
    return bool(a.get(key, False))


def _from_loan(a: Mapping[str, Any]) -> bool:
    return str(a.get("from_account_type", "")).lower() == "loan" or str(
        a.get("funds_source", "")
    ).lower() in {
        "loan",
        "webank_loan",
    }


def _check_money_move(t: str, a: Mapping[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    dest = str(a.get("destination", "pot" if t in ("recurring_setaside", "setaside") else "")).lower()
    to_sg = dest in SG_DESTINATIONS or t == "capital_injection"
    if to_sg and _from_loan(a):
        out.append(violation("R1", "action", f"{t} from a loan account"))
    if to_sg and _truthy(a, "loan_above_normal"):
        out.append(violation("R2", "action", f"{t} while borrowing is above normal"))
    if t == "capital_injection" and str(a.get("source", "savings")).lower() in _vocab("borrowed_sources"):
        out.append(violation("R7", "action", f"capital from {a.get('source')}"))
    if dest in {"singapore", "sg", "sg_company"} or (t == "capital_injection" and dest != "pot"):
        out += _check_r4_action(a)
    return out


def _check_r4_action(a: Mapping[str, Any]) -> list[Violation]:
    done = {str(x) for x in a.get("completed", [])}
    chain = [str(x) for x in load_rules_yaml()["legal_chain"]]
    if str(a.get("purpose", "")) == "pre_investment":
        out: list[Violation] = []
        if "lender_consent" not in done:
            out.append(violation("R4", "action", "前期费用 before lender consent"))
        if "deposit" in str(a.get("covers", "")) or "security_deposit" in a.get("covers", []):
            out.append(violation("R4", "action", "前期费用 can't pay the deposit"))
        amt, total = a.get("amount_cny"), a.get("planned_total_cny")
        if (
            amt is None
            or total is None
            or Decimal(str(amt)) > Decimal(str(total)) * P.num("pre_investment_cap_share")
        ):
            out.append(violation("R4", "action", "前期费用 above 15% of the planned total (or unknown)"))
        return out
    missing = [c for c in chain if c not in done]
    return [violation("R4", "action", "transfer before " + ", ".join(missing))] if missing else []


def check_action(action: Mapping[str, Any]) -> list[Violation]:
    """Check a prepared action (a dict with `type` and its fields) against R1-R8."""
    t = str(action.get("type", "")).lower()
    out: list[Violation] = []
    if t in _vocab("guarantee_types") or _truthy(action, "guarantee"):
        loc = str(action.get("guarantor_location", "china")).lower()
        guarantor = str(action.get("guarantor", "company")).lower()
        if loc != "singapore" or guarantor in {"company", "owner", "owner_personal", "chen"}:
            out.append(violation("R3", "action", f"{t or 'guarantee'} by {guarantor}"))
    if t in {"transfer", "recurring_setaside", "setaside", "capital_injection"}:
        out += _check_money_move(t, action)
    if t == "sign_lease":
        have, need = action.get("funds_in_singapore_sgd"), action.get("required_sgd")
        if have is None or need is None or Decimal(str(have)) < Decimal(str(need)):
            out.append(
                violation("R6", "action", "deposit, fit-out and pre-opening rent not all in Singapore")
            )
    if t in SG_LOAN_TYPES:
        if not _truthy(action, "opened"):
            out.append(violation("R8", "action", "Singapore borrowing before opening"))
        elif float(action.get("local_ownership", 0)) < P.fnum("partner_min_local_share"):
            out.append(violation("R8", "action", "EFS needs at least 30% local ownership"))
    if t == "grant" and float(action.get("local_ownership", 0)) < P.fnum("partner_min_local_share"):
        out.append(violation("R8", "action", "grants need at least 30% local ownership"))
    return out
