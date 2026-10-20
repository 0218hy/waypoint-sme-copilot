"""Goal Keeper (SPEC §7): goals, the weekly check, alerts, repairs, the Goal tab, reminder emails.

The weekly check re-plans from today's position: the profit model is refit on the feed (or the
owner's check-ins), the money already saved counts towards the target, and the plan is simulated
again with the same seed. It alerts on the plan (the opening date or the floor risk), never on one
slow week: a channel shift or a missing feed week alone is not a drop.
"""

from __future__ import annotations

import logging
import secrets
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from agent import toolkit as tk
from agent.render import month_label
from agent.state import JourneyState
from agent.widgets import (
    AlertCard,
    CheckinForm,
    PlanVsActual,
    RepairOptions,
    RepairRow,
    StatusCard,
    Widget,
)
from app.email import sender
from tools import params as P
from tools.figtools import derived
from tools.figures import Figure
from tools.models import Alert, CheckIn, Goal, GoalRevision, GoalStatus, PlanResult

if TYPE_CHECKING:
    from app.services import AppServices

log = logging.getLogger(__name__)
STATUS_RANK = {GoalStatus.ON_TRACK: 0, GoalStatus.AT_RISK: 1, GoalStatus.OFF_TRACK: 2}
DUE_WEEKS = {"weekly": 1, "fortnightly": 2, "monthly": 4}


class GoalKeeper:
    def __init__(self, svc: AppServices) -> None:
        self.svc = svc
        self.store = svc.store
        self._run_lock = threading.Lock()  # one scheduled run at a time (scheduler thread, demo clock)

    # ---------------------------------------------------------------- records

    def _rec(self, goal_id: str) -> dict[str, Any]:
        rec = self.store.goal(goal_id)
        if rec is None:
            raise KeyError(goal_id)
        return rec

    def goal(self, goal_id: str) -> Goal:
        return Goal.model_validate(self._rec(goal_id)["goal"])

    def _save(self, goal: Goal, plan: PlanResult | None = None, extra: dict[str, Any] | None = None) -> None:
        rec = self.store.goal(goal.id) or {}
        rec["goal"] = goal.model_dump(mode="json")
        if plan is not None:
            rec["plan"] = plan.model_dump(mode="json")
        rec.update(extra or {})
        self.store.save_goal(goal.id, goal.owner_id, rec)

    def plan(self, goal_id: str) -> PlanResult:
        return PlanResult.model_validate(self._rec(goal_id)["plan"])

    # ---------------------------------------------------------------- create and revise

    def create(self, state: JourneyState, card_hash: str) -> str:
        from tools import timeline as TL

        assert state.plan is not None and state.funding is not None and state.cost_card is not None
        res = state.plan
        if res.open_likely_week is None or res.open_p95_week is None:
            raise ValueError("plan does not open within the horizon")
        gid = "g_" + secrets.token_hex(6)
        now = datetime.now(UTC)
        prefs = state.goal_prefs
        goal = Goal(
            id=gid,
            owner_id=state.owner_id,
            start_date=state.start_date,
            unit_id=state.shortlist.chosen_unit_id or "",
            cost_total_likely_sgd=state.cost_card.total_likely_sgd,
            funding=state.funding,
            target_open_likely_week=res.open_likely_week,
            target_open_p95_week=res.open_p95_week,
            setaside_monthly_cny=res.monthly_setaside_cny,
            floor_cny=state.funding.floor_cny or Decimal(0),
            floor_risk=res.floor_risk,
            milestones=TL.build_timeline(res),
            checkin_frequency=prefs.get("checkin_frequency", "monthly"),
            email_amounts=bool(prefs.get("email_amounts")),
            recurring_setaside=bool(prefs.get("recurring_setaside")),
            revisions=[
                GoalRevision(at=now, reason="created", summary="goal created", approved_card_hash=card_hash)
            ],
            created_at=now,
        )
        scenario = {
            # the spare cash the plan used (never above the feed's figure), not whatever the owner typed
            "spare_moved_cny": str(state.funding.own_savings_cny + tk.spare_cash_used(state)),
            "monthly_cny": str(res.monthly_setaside_cny),
        }
        self._save(
            goal,
            res,
            {
                "state_snapshot": _snapshot(state),
                "last_check_week": 0,
                "scenario": scenario,
                "sched_week": 0,  # the weekly job's last run (week 0: the goal was just checked)
                "sched_email_week": 0,  # the welcome email opens the first email period
            },
        )
        state.goal_id = gid
        self._ensure_scenario(goal, state)
        self.svc.audit.append("goal_created", state.owner_id, goal_id=gid, card_hash=card_hash)
        self._email(goal, "welcome", self._welcome_ctx(goal, state.lang))
        return gid

    def revise(self, state: JourneyState, card_hash: str, reason: str) -> None:
        from tools import timeline as TL

        assert state.goal_id and state.plan is not None and state.funding is not None
        goal = self.goal(state.goal_id)
        res = state.plan
        elapsed = self.elapsed(goal)
        before = {
            "open_likely_week": str(goal.target_open_likely_week),
            "setaside_monthly_cny": str(goal.setaside_monthly_cny),
        }
        likely = res.open_likely_week or goal.target_open_likely_week
        p95 = res.open_p95_week or goal.target_open_p95_week
        goal = goal.model_copy(
            update={
                "funding": state.funding,
                "unit_id": state.shortlist.chosen_unit_id or goal.unit_id,
                "target_open_likely_week": likely,
                "target_open_p95_week": p95,
                "setaside_monthly_cny": res.monthly_setaside_cny,
                "floor_risk": res.floor_risk,
                "milestones": TL.carry_done(goal.milestones, TL.build_timeline(res)),
                "status": GoalStatus.ON_TRACK,
                "checkin_frequency": state.goal_prefs.get("checkin_frequency", goal.checkin_frequency),
                "email_amounts": bool(state.goal_prefs.get("email_amounts", goal.email_amounts)),
            }
        )
        goal.revisions.append(
            GoalRevision(
                at=datetime.now(UTC),
                reason=reason if reason in ("checkin", "alert", "owner") else "owner",
                summary="goal revised",
                approved_card_hash=card_hash,
                before=before,
                after={
                    "open_likely_week": str(likely),
                    "setaside_monthly_cny": str(res.monthly_setaside_cny),
                },
            )
        )
        self._save(
            goal,
            res,
            {"state_snapshot": _snapshot(state), "replan_offset_weeks": 0, "last_check_week": elapsed},
        )
        self.svc.audit.append(
            "goal_revised", state.owner_id, goal_id=goal.id, card_hash=card_hash, reason=reason
        )

    # ---------------------------------------------------------------- the monthly set-aside (embedded mode)

    def setaside_terms(self, state: JourneyState) -> dict[str, Any]:
        """The prepared monthly transfer, built by code from the approved goal, the company's own
        accounts in the (mock) WeBank feed and today's date. Rebuilt at approval."""
        from agent.approval import account_hash
        from mock_webank import feed as mw

        assert state.goal_id
        goal = self.goal(state.goal_id)
        today = self.svc.today()
        start = date(today.year + today.month // 12, today.month % 12 + 1, 1)  # the 1st of next month
        acc = mw.accounts(state.owner_id)
        return {
            "goal_id": goal.id,
            "amount_cny": str(goal.setaside_monthly_cny),
            "from_account": account_hash(acc["operating"]),
            "to_account": account_hash(acc["savings"]),
            "start_date": start.isoformat(),
            "pause_when": ["R2", "R5"],
            "floor_cny": str(goal.floor_cny),
            # R5 as the bank runs it: before each monthly transfer, skip the month if it would leave home
            # cash below floor + buffer (the plan simulates exactly this; tools/plan.py)
            "pause_below_cny": str(goal.floor_cny + (goal.funding.buffer_cny or Decimal(0))),
            "checked": "before_each_transfer",
        }

    def setaside_lines(self, state: JourneyState, terms: dict[str, Any]) -> list[dict[str, str]]:
        from agent.render import money
        from mock_webank import feed as mw

        zh = state.lang == "zh"
        acc = mw.accounts(state.owner_id)
        start = date.fromisoformat(terms["start_date"])
        amount = money(Decimal(terms["amount_cny"]), "CNY", state.lang)
        keep = money(Decimal(terms["pause_below_cny"]), "CNY", state.lang)
        weeks = P.inum("buffer_payroll_weeks")
        return [
            {"label": "每月金额" if zh else "Each month", "value": amount},
            {
                "label": "转出" if zh else "From",
                "value": f"公司结算账户 尾号{acc['operating'][-4:]}" if zh
                else f"Your company's operating account ••• {acc['operating'][-4:]}",
            },
            {
                "label": "转入" if zh else "Into",
                "value": f"公司自有储蓄子账户 尾号{acc['savings'][-4:]}" if zh
                else f"Your company's own savings sub-account ••• {acc['savings'][-4:]}",
            },
            {
                "label": "首次转存" if zh else "First transfer",
                "value": _day_label(start, state.lang),
            },
            {
                "label": "自动暂停" if zh else "Pauses",
                "value": f"微众贷款高于平时水平时；或某月转存后国内现金将低于 {keep}（安全底线加 {weeks} 周工资缓冲）时，当月跳过（每次转存前检查）" if zh  # noqa: E501
                else f"While your WeBank borrowing is above its usual level; and any month the transfer would leave home cash below {keep} (your safety floor plus a {weeks}-week payroll buffer), that month is skipped (checked before each transfer)",  # noqa: E501
            },
            {
                "label": "下一步" if zh else "Next",
                "value": "您在微众银行自己的签署流程中确认；Waypoint 不会移动任何资金" if zh
                else "You sign it in WeBank's own flow; Waypoint never moves money",
            },
        ]

    def setaside_blockers(self, state: JourneyState) -> list[str]:
        """Rules that hold the set-aside back today: R2 (borrowing above its usual level pauses it) and
        R5 (the plan's floor risk over the limit). R5's cash test is not a one-off check here: it is part
        of the instruction's terms (`pause_below_cny`), applied by the bank before every monthly transfer,
        as the plan simulates it. On approval day home cash sits at floor + buffer (the spare cash has just
        moved to the pot), and the first transfer is next month."""
        from mock_webank import feed as mw
        from rules import engine as R
        from tools import funding as F

        assert state.goal_id
        goal = self.goal(state.goal_id)
        out: list[str] = []
        if state.consent_feed:
            now = mw.get_feed(state.owner_id, self.svc.today())
            action = {
                "type": "recurring_setaside",
                "destination": "pot",
                "from_account_type": "operating",
                "loan_above_normal": F.r2_paused(now),
            }
            out += [v.rule_id for v in R.blocking(R.check_action(action))]
        if goal.floor_risk > P.num("floor_risk_limit"):
            out.append("R5")
        return sorted(set(out))

    def setaside_instruction(self, goal_id: str) -> dict[str, Any] | None:
        """The latest prepared instruction, as the (mock) bank has it now."""
        from mock_webank import instructions as MI

        rec = self._rec(goal_id).get("setaside_instruction")
        if not rec:
            return None
        goal = self.goal(goal_id)
        MI.restore(goal.owner_id, rec)
        return MI.get(goal.owner_id, rec["id"])

    def setaside_needed(self, state: JourneyState) -> bool:
        """True when the owner chose the monthly transfer (embedded mode) and no live instruction covers
        today's approved amount."""
        if not state.goal_id or state.host_mode.value != "embedded" or not state.goal_prefs.get("recurring_setaside"):  # noqa: E501
            return False
        cur = self.setaside_instruction(state.goal_id)
        goal = self.goal(state.goal_id)
        return not (
            cur and cur["status"] in ("pending_signature", "signed")
            and Decimal(cur["terms"]["amount_cny"]) == goal.setaside_monthly_cny
        )

    def prepare_setaside(self, state: JourneyState, card_hash: str) -> dict[str, Any]:
        """After the owner approves the card: record the instruction in the (mock) bank, pending his
        signature there. Nothing moves."""
        from mock_webank import instructions as MI

        assert state.goal_id
        terms = self.setaside_terms(state)
        rec = MI.prepare(state.owner_id, terms, card_hash)
        self._save(self.goal(state.goal_id), extra={"setaside_instruction": rec})
        self.svc.audit.append(
            "setaside_prepared", state.owner_id, goal_id=state.goal_id, instruction_id=rec["id"],
            card_hash=card_hash, amount_cny=terms["amount_cny"], start_date=terms["start_date"],
            status=rec["status"],
        )
        return rec

    def sign_setaside(self, owner_id: str, instruction_id: str) -> dict[str, Any] | None:
        """Demo only: the owner's signature in WeBank's own flow (simulated)."""
        from mock_webank import instructions as MI

        user = self.store.user(owner_id)
        state = self.svc.load_state(user) if user else None
        if state is None or not state.goal_id:
            return None
        self.setaside_instruction(state.goal_id)  # restored into the mock bank if needed
        rec = MI.sign(owner_id, instruction_id)
        if rec is None:
            return None
        self._save(self.goal(state.goal_id), extra={"setaside_instruction": rec})
        self.svc.audit.append(
            "setaside_signed", owner_id, goal_id=state.goal_id, instruction_id=rec["id"], via="webank_mock"
        )
        return rec

    def webank_view(self, user: dict[str, Any]) -> dict[str, Any]:
        """Demo only: what the mock WeBank shows the owner (instructions waiting for his signature)."""
        state = self.svc.load_state(user)
        rec = self.setaside_instruction(state.goal_id) if state.goal_id else None
        if rec is None or rec["status"] not in ("pending_signature", "signed"):
            return {"instructions": [], "simulated": True}
        from agent.render import money
        from mock_webank import feed as mw

        zh = state.lang == "zh"
        last4 = mw.accounts(state.owner_id)["savings"][-4:]
        start = date.fromisoformat(rec["terms"]["start_date"])
        return {
            "instructions": [
                {
                    "id": rec["id"],
                    "status": rec["status"],
                    "amount": money(Decimal(rec["terms"]["amount_cny"]), "CNY", state.lang),
                    "into": f"储蓄子账户（尾号{last4}）" if zh else f"your savings sub-account ••• {last4}",
                    "start": _day_label(start, state.lang),
                }
            ],
            "simulated": True,
        }

    def _ensure_scenario(self, goal: Goal, state: JourneyState) -> None:
        """The mock feed's scenario lives in memory: rebuild it from the goal record (idempotent)."""
        if not state.consent_feed:
            return
        from mock_webank import feed as mw

        sc = self._rec(goal.id).get("scenario") or {}
        mw.reset(goal.owner_id)
        mw.register_goal(
            goal.owner_id,
            goal.start_date,
            Decimal(sc.get("spare_moved_cny", "0")),
            Decimal(sc.get("monthly_cny", str(goal.setaside_monthly_cny))),
        )
        shocks = _shocks_from(sc.get("shocks", []))
        if shocks:
            mw.add_shocks(goal.owner_id, shocks)

    def add_scenario(self, user: dict[str, Any], scenario: str, start: date) -> None:
        """Demo only: a labelled, simulated scenario that starts today (sales dip, channel shift, extra draw)."""  # noqa: E501
        state = self.svc.load_state(user)
        if not state.goal_id:
            return
        rec = self._rec(state.goal_id)
        sc = rec.get("scenario") or {}
        sc.setdefault("shocks", []).append({"kind": scenario, "start": start.isoformat()})
        self._save(self.goal(state.goal_id), extra={"scenario": sc})
        self.svc.audit.append("demo_scenario", user["id"], scenario=scenario, start=start.isoformat())

    def update_prefs(self, goal_id: str, settings: dict[str, Any]) -> None:
        goal = self.goal(goal_id)
        goal = goal.model_copy(
            update={
                "checkin_frequency": settings.get("checkin_frequency", goal.checkin_frequency),
                "email_amounts": bool(settings.get("email_amounts", goal.email_amounts)),
            }
        )
        self._save(goal)

    # ---------------------------------------------------------------- milestones and drafts (SPEC §7.4)

    def mark_milestone_done(self, state: JourneyState, mid: str) -> Goal:
        """Record a step the owner says is done (validated by code: a real step, in legal order), then
        recompute the status from the latest check. Raises ValueError (unknown / already_done /
        out_of_order). The caller asks the owner to confirm a money step before calling this."""
        from tools import timeline as TL

        assert state.goal_id
        goal = self.goal(state.goal_id)
        today = self.svc.today()
        milestones = TL.mark_done(goal.milestones, mid, today)
        goal = goal.model_copy(update={"milestones": milestones})
        latest = self._rec(goal.id).get("latest") or {}
        likely = latest.get("likely")
        if not latest:
            moved = 0  # not checked since it was approved: the goal as approved
        else:
            moved = (int(likely) - goal.target_open_likely_week) if likely is not None else 999
        risk = Decimal(str(latest.get("risk", goal.floor_risk)))
        status = _status_for(moved, risk, bool(_late(goal, self.elapsed(goal))))
        goal = goal.model_copy(update={"status": status})
        self._save(goal)
        self.svc.audit.append(
            "milestone_done", goal.owner_id, goal_id=goal.id, milestone=mid, on=today.isoformat(), status=status.value  # noqa: E501
        )
        return goal

    def consent_draft(self, state: JourneyState, lang: str) -> tuple[list[Figure], Any]:
        """The lender-consent request's facts, from the approved goal (the model writes the prose)."""
        from agent import drafts

        assert state.goal_id
        goal = self.goal(state.goal_id)
        u = tk.unit(goal.unit_id)
        figs, card = drafts.consent_request(
            goal, self._rec(goal.id).get("state_snapshot") or {}, f"{u.mall} {u.unit_no}", lang  # type: ignore[arg-type]
        )
        self.svc.audit.append("draft_prepared", goal.owner_id, goal_id=goal.id, draft="consent_request")
        return figs, card

    # ---------------------------------------------------------------- the weekly check

    def elapsed(self, goal: Goal) -> int:
        return max(0, (self.svc.today() - goal.start_date).days // 7)

    def replan(
        self, state: JourneyState, owner_numbers: dict[str, Decimal] | None = None
    ) -> tuple[PlanResult, JourneyState, Any, dict[str, Any], int]:
        """Re-plan the active goal from today: returns the plan in weeks from the goal's start, the
        positioned state, the planner's source, the signals and the weeks elapsed."""
        assert state.goal_id
        goal = self.goal(state.goal_id)
        elapsed = self.elapsed(goal)
        today = self.svc.today()
        self._ensure_scenario(goal, state)
        signals = tk.goal_signals(state, goal, today, owner_numbers)
        # With the feed the pot balance is already a plan input; only owner-reported savings are added.
        in_hand = Decimal(0) if signals.get("feed_now") is not None else signals["saved_cny"]
        replan_state = _replan_state(state, goal, today, in_hand)
        src = tk.replan_source(replan_state, signals)
        res = tk.simulate_from(replan_state, src)
        return _shift(res, elapsed), replan_state, src, signals, elapsed

    def check(
        self, goal_id: str, state: JourneyState, owner_numbers: dict[str, Decimal] | None = None
    ) -> tuple[Goal, Alert | None, dict[str, Any]]:
        """Re-plan from today and decide status and alerts (SPEC §7.2)."""
        today = self.svc.today()
        res, replan_state, src, signals, elapsed = self.replan(state, owner_numbers)
        # read after the re-plan (which takes a while): a step marked done meanwhile is kept and counted
        goal = self.goal(goal_id)
        rec = self._rec(goal_id)
        new_likely, new_p95 = res.open_likely_week, res.open_p95_week
        moved = (new_likely - goal.target_open_likely_week) if new_likely is not None else 999
        risk = res.floor_risk
        late = _late(goal, elapsed)
        status = _status_for(moved, risk, bool(late))
        alert_move = P.inum("alert_move_weeks")
        last_moved = int(rec.get("last_moved", 0))
        worse = STATUS_RANK[status] > STATUS_RANK[goal.status]
        moved_more = abs(moved - last_moved) >= alert_move and moved >= alert_move
        alert: Alert | None = None
        kind = None
        if signals["r2"] and not rec.get("r2_alerted"):
            kind = "r2_pause"
        elif worse or moved_more:
            kind = "status_worse" if worse else "date_slip"
        if kind is not None and (
            signals["drop"] or kind == "r2_pause" or risk > _threshold("at_risk_floor_risk") or late
        ):
            repairs = [
                r.model_copy(
                    update={
                        "new_open_likely_week": None
                        if r.new_open_likely_week is None
                        else elapsed + r.new_open_likely_week,
                        "new_open_p95_week": None
                        if r.new_open_p95_week is None
                        else elapsed + r.new_open_p95_week,
                    }
                )
                for r in tk.find_repairs(replan_state, src)
            ]
            alert = Alert(
                id="a_" + secrets.token_hex(5),
                goal_id=goal.id,
                created_at=datetime.now(UTC),
                kind=kind,
                weeks_moved=moved if moved < 999 else 0,
                act_by=today + timedelta(days=P.inum("act_by_alert_days")),
                status_before=goal.status,
                status_after=status,
                repairs=repairs,
            )
            self.store.save_alert(alert.id, goal.id, {**alert.model_dump(mode="json"), "elapsed": elapsed})
        ci = CheckIn(
            goal_id=goal.id,
            week=elapsed,
            on=today,
            profit_cny=signals.get("profit_cny"),
            set_aside_cny=signals.get("set_aside_cny"),
            loan_balance_cny=signals.get("loan_cny"),
            source="owner" if owner_numbers else "feed",
            channel_shift=bool(signals.get("channel_shift")),
        )
        self.store.add_checkin(
            goal.id,
            {
                **ci.model_dump(mode="json"),
                "saved_cny": str(signals["saved_cny"]),
                "new_likely": new_likely,
                "new_p95": new_p95,
                "floor_risk": str(risk),
                "status": status.value,
                "drop": bool(signals["drop"]),
            },
        )
        goal = goal.model_copy(update={"status": status})
        self._save(
            goal,
            extra={
                "last_check_week": elapsed,
                "last_moved": moved if moved < 999 else last_moved,
                "r2_alerted": bool(signals["r2"]) or bool(rec.get("r2_alerted")) and signals["r2"],
                "replan_offset_weeks": elapsed,
                "latest": {"likely": new_likely, "p95": new_p95, "risk": str(risk)},
            },
        )
        self.svc.audit.append(
            "goal_check",
            goal.owner_id,
            goal_id=goal.id,
            week=elapsed,
            status=status.value,
            moved=moved,
            alert=alert.kind if alert else None,
        )
        return (
            goal,
            alert,
            {"new_likely": new_likely, "new_p95": new_p95, "risk": risk, "r2": signals["r2"], "moved": moved},
        )

    def run_due(self) -> dict[str, int]:
        """The scheduled job (SPEC §7.2), idempotent per goal and period.

        Each active goal is checked at most once per week of its life (with a feed; standalone goals
        are checked when the owner answers), and emailed at most once per period of its chosen
        frequency: the alert if this week's check raised one, otherwise the digest (feed) or the
        check-in email (standalone). The period is marked before the email goes, so a repeated or
        overlapping run never sends twice; a missed run catches up with one check and one email.
        """
        sent = {"checks": 0, "emails": 0}
        with self._run_lock:
            for gid, uid, _rec in self.store.active_goals():
                try:
                    self._run_goal(gid, uid, sent)
                except Exception:  # one goal's failure must not stop the others
                    log.exception("weekly check failed for goal %s", gid)
        return sent

    def _run_goal(self, gid: str, uid: str, sent: dict[str, int]) -> None:
        user = self.store.user(uid)
        if user is None:
            return
        goal = self.goal(gid)
        state = self.svc.load_state(user)
        if goal.owner_id != uid or state.goal_id != gid:
            return
        rec = self._rec(gid)
        elapsed = self.elapsed(goal)
        alert: Alert | None = None
        if elapsed > int(rec.get("sched_week", 0)):
            self._save(goal, extra={"sched_week": elapsed})
            if state.consent_feed:
                goal, alert, _info = self.check(gid, state)
                sent["checks"] += 1
        email_due = elapsed - int(rec.get("sched_email_week", 0)) >= DUE_WEEKS[goal.checkin_frequency]
        if alert is not None or email_due:
            self._save(self.goal(gid), extra={"sched_email_week": elapsed})
            sent["emails"] += 1
            if alert is not None:
                self._email(goal, "alert", self._alert_ctx(goal, alert, state.lang))
                fresh = self.svc.load_state(user)  # only the alert pointer changes: never clobber a chat turn
                fresh.last_alert_id = alert.id
                self.svc.save_state(fresh)
            elif state.consent_feed:
                self._email(goal, "digest", self._digest_ctx(goal, state.lang))
            else:
                from app import auth

                token = auth.checkin_token(gid, f"w{elapsed}")  # one goal, one period: both links carry it
                quick = f"{self.svc.base_url}/api/checkin/quick?token={token}"
                self._email(
                    goal,
                    "checkin",
                    {"url": f"{self.svc.base_url}/?checkin={token}", "quick_url": quick, "demo": self.svc.demo()},  # noqa: E501
                    state.lang,
                )
        self._milestone_reminders(self.goal(gid), state.lang)

    def owner_checkin(self, state: JourneyState, data: dict[str, Any]) -> dict[str, Any]:
        from agent.parse import amounts

        assert state.goal_id
        nums: dict[str, Decimal] = {}
        for k in ("profit_cny", "set_aside_cny"):
            v = amounts(str(data.get(k, "")))
            if v:
                nums[k] = v[0]
        goal, alert, info = self.check(state.goal_id, state, nums or None)
        period = str(data.get("period") or "")
        if self._period_week(goal, period) is not None:  # answered: that email's one-tap link is spent
            rec = self._rec(goal.id)
            done = set(rec.get("quick_checkins", [])) | {period}
            self._save(self.goal(goal.id), extra={"quick_checkins": sorted(done)})
        return self._check_view(goal, alert, info, state)

    def _period_week(self, goal: Goal, period: str) -> int | None:
        """A check-in period ("w<n>": the goal's week the email went out), if it is a real one so far."""
        if not (period.startswith("w") and period[1:].isdigit()):
            return None
        n = int(period[1:])
        return n if 0 <= n <= self.elapsed(goal) else None

    def checkin_link(self, state: JourneyState, token: str) -> str | None:
        """The period of a check-in email's "Something changed" link, or None when the signed token is
        invalid, expired, or for a goal that isn't this owner's current goal."""
        from app import auth

        got = auth.verify_checkin(token)
        if got is None or not state.goal_id:
            return None
        goal_id, period = got
        if goal_id != state.goal_id or self.store.goal(goal_id) is None:
            return None
        goal = self.goal(goal_id)
        if goal.owner_id != state.owner_id or self._period_week(goal, period) is None:
            return None
        return period

    def _check_view(
        self, goal: Goal, alert: Alert | None, info: dict[str, Any], state: JourneyState
    ) -> dict[str, Any]:
        lang = state.lang
        f_likely = derived(
            "goal.open_likely", "Likely opening", "weeks", info["new_likely"], tool="goalkeeper"
        )
        f_moved = derived(
            "goal.weeks_moved",
            "Weeks moved",
            "weeks",
            info["moved"] if info["moved"] < 999 else None,
            tool="goalkeeper",
        )
        f_risk = derived("goal.floor_risk", "Floor risk", "pct", info["risk"], tool="goalkeeper")
        line = {"on_track": "on_track", "at_risk": "at_risk", "off_track": "off_track"}[goal.status.value]
        changes = _changes(info, lang)
        status = StatusCard(
            status=goal.status.value,
            headline=_status_headline(goal.status.value, lang),
            changes=changes,
            figures=["goal.open_likely", "goal.floor_risk"],
        )
        if alert is not None:
            state.last_alert_id = alert.id
        return {
            "figs": [f_likely, f_moved, f_risk],
            "status": status,
            "line": line,
            "alert_id": alert.id if alert else None,
            "r2_pause": bool(info["r2"]),
        }

    def quick_checkin(self, goal_id: str, period: str) -> bool:
        """'On plan as usual' from the email: the month's set-aside as planned, then the usual check."""
        rec = self._rec(goal_id)
        done = set(rec.get("quick_checkins", []))
        if period in done:
            return False
        goal = self.goal(goal_id)
        user = self.store.user(goal.owner_id)
        if user is None:
            return False
        state = self.svc.load_state(user)
        self.check(goal_id, state, {"set_aside_cny": goal.setaside_monthly_cny})
        done.add(period)
        self._save(self.goal(goal_id), extra={"quick_checkins": sorted(done)})
        self.svc.audit.append("checkin", goal.owner_id, goal_id=goal_id, via="email_one_tap", period=period)
        return True

    def show_checkin(self, t: Any, period: str | None = None) -> None:
        """The check-in form; for an email's period ("w<n>"), the month that email asked about."""
        st = t.state
        if not st.goal_id:
            return
        week = self._period_week(self.goal(st.goal_id), period or "")
        goal = self.goal(st.goal_id)
        asked = goal.start_date + timedelta(weeks=week) if week is not None else self.svc.today()
        label = month_label(asked - timedelta(weeks=4), 0, st.lang)
        t.say("checkin_ask", skill="goal-keeper")
        t.show(
            CheckinForm(goal_id=st.goal_id, period_label=label, period=period if week is not None else None),
            skill=t.skills["goal-keeper"],
        )

    # ---------------------------------------------------------------- alerts and repairs

    def _alert(self, goal_id: str, alert_id: str) -> Alert | None:
        for a in self.store.alerts_for(goal_id):
            if a.get("id") == alert_id:
                return Alert.model_validate(a)
        return None

    def alert_view(self, state: JourneyState, alert_id: str, lang: str) -> dict[str, Any] | None:
        if not state.goal_id:
            return None
        alert = self._alert(state.goal_id, alert_id)
        if alert is None:
            return None
        figs: list[Figure] = []
        rows = []
        for r in alert.repairs:
            a = derived(
                f"rep.{r.id}.likely", "New likely opening", "weeks", r.new_open_likely_week, tool="repairs"
            )
            b = derived(
                f"rep.{r.id}.p95",
                "New opening if things go badly",
                "weeks",
                r.new_open_p95_week,
                tool="repairs",
            )
            c = derived(f"rep.{r.id}.risk", "New floor risk", "pct", r.new_floor_risk, tool="repairs")
            figs += [a, b, c]
            label, detail = tk.repair_text(r, lang)  # type: ignore[arg-type]
            rows.append(
                RepairRow(
                    id=r.id,
                    label=label,
                    detail=detail,
                    new_open_likely=a.id,
                    new_open_p95=b.id,
                    new_floor_risk=c.id,
                )
            )
        moved = derived("alert.moved", "Weeks moved", "weeks", None, tool="goalkeeper")
        head = _alert_headline(alert, lang)
        act = month_label(alert.act_by, 0, lang) if alert.act_by else None  # type: ignore[arg-type]
        return {
            "figs": [*figs, moved],
            "alert": AlertCard(
                alert_id=alert.id, kind=alert.kind, headline=head, weeks_moved=None, act_by_date=act
            ),
            "repairs": RepairOptions(alert_id=alert.id, repairs=rows),
        }

    def apply_repair(self, state: JourneyState, alert_id: str, repair_id: str) -> None:
        assert state.goal_id and state.funding is not None
        alert = self._alert(state.goal_id, alert_id)
        rep = next((r for r in (alert.repairs if alert else []) if r.id == repair_id), None)
        if rep is None:
            raise KeyError(repair_id)
        tk.apply_repair(state, rep)
        state.revising = True
        state.plan = self.replan(state)[0]
        if alert is not None:
            alert = alert.model_copy(update={"resolved_with": repair_id})
            self.store.save_alert(alert.id, alert.goal_id, alert.model_dump(mode="json"))

    # ---------------------------------------------------------------- dashboard

    def dashboard(self, state: JourneyState) -> dict[str, Any]:
        if not state.goal_id:
            return {"goal": None, "widgets": []}
        goal = self.goal(state.goal_id)
        res = self.plan(goal.id)
        lang = state.lang
        rec = self._rec(goal.id)
        latest = rec.get("latest") or {}
        elapsed = self.elapsed(goal)
        likely = latest.get("likely") or goal.target_open_likely_week
        p95 = latest.get("p95") or goal.target_open_p95_week
        figs = {
            "goal.open_likely": derived(
                "goal.open_likely", "Likely opening", "weeks", likely, tool="goalkeeper"
            ),
            "goal.open_p95": derived(
                "goal.open_p95", "Opening if things go badly", "weeks", p95, tool="goalkeeper"
            ),
            "goal.setaside_monthly": derived(
                "goal.setaside_monthly",
                "Monthly set-aside",
                "CNY",
                goal.setaside_monthly_cny,
                tool="goalkeeper",
            ),
            "goal.floor_risk": derived(
                "goal.floor_risk",
                "Floor risk",
                "pct",
                Decimal(str(latest.get("risk", goal.floor_risk))),
                tool="goalkeeper",
            ),
        }
        widgets: list[Widget] = []

        def w(payload: Any, ids: list[str], extra: dict[str, Figure] | None = None) -> None:
            fs = {**{i: figs[i] for i in ids if i in figs}, **(extra or {})}
            from agent.render import display_map

            widgets.append(
                Widget(
                    id=f"g{len(widgets) + 1}",
                    payload=payload,
                    figures=fs,
                    display=display_map(fs, lang, goal.start_date),
                )
            )

        w(
            StatusCard(
                status=goal.status.value,
                headline=_status_headline(goal.status.value, lang),
                changes=_changes({"moved": (likely or 0) - goal.target_open_likely_week, "r2": False}, lang),
                figures=["goal.open_likely", "goal.open_p95"],
            ),
            ["goal.open_likely", "goal.open_p95"],
        )
        w(_plan_vs_actual(goal, res, self.store.checkins_for(goal.id), elapsed, lang), [])
        tfigs, timeline = tk.timeline_for_goal(goal, elapsed, lang, interactive=False)
        w(timeline, [], {f.id: f for f in tfigs})
        for _kind, payload, extra in tk.plan_summaries(goal, rec.get("state_snapshot", {}), res, lang):
            w(payload, [], {f.id: f for f in extra})
        for payload, extra in tk.goal_analysis(state, rec.get("state_snapshot", {}), lang, self.svc.today()):
            w(payload, [], {f.id: f for f in extra})
        # an alert about a plan that has since been revised and approved is closed: the new plan answers it
        revised = [r.at for r in goal.revisions if r.reason != "created"]
        last_revision = max(revised) if revised else None
        for a in self.store.alerts_for(goal.id):
            al = Alert.model_validate(a)
            superseded = last_revision is not None and _utc(al.created_at) <= _utc(last_revision)
            w(
                AlertCard(
                    alert_id=al.id,
                    kind=al.kind,
                    headline=_alert_headline(al, lang),
                    weeks_moved=None,
                    act_by_date=month_label(al.act_by, 0, lang) if al.act_by else None,
                    resolved=al.resolved_with is not None or superseded,
                ),
                [],
            )
        return {
            "goal": {
                "id": goal.id,
                "status": goal.status.value,
                "sentence": tk.goal_text(goal, lang, figs),
                "start_date": goal.start_date.isoformat(),
                "elapsed_weeks": elapsed,
                "revisions": len(goal.revisions),
                "change_in_progress": bool(state.revising),
                "today": self.svc.today().isoformat(),
                "next_step": self._next_step_view(goal, lang),
            },
            "widgets": [x.model_dump(mode="json") for x in widgets],
        }

    # ---------------------------------------------------------------- emails

    def _email(self, goal: Goal, template: str, ctx: dict[str, Any], lang: str | None = None) -> None:
        user = self.store.user(goal.owner_id)
        if not user or not user.get("email") or not user.get("email_verified"):
            return
        lang = lang or (user.get("settings") or {}).get("lang", "en")
        ctx = {
            "demo": self.svc.demo(),
            "settings_url": f"{self.svc.base_url}/#/account",
            "unsubscribe_url": f"{self.svc.base_url}/#/account",
            **ctx,
        }
        sender.send(self.store, user["email"], template, lang, ctx, user["id"])  # type: ignore[arg-type]

    def _next_step(self, goal: Goal, lang: str) -> tuple[str, str]:
        from tools import timeline as TL

        nxt = TL.next_open(goal.milestones)
        if nxt is None:
            return "", ""
        return tk.milestone_label(nxt.id, lang), month_label(goal.start_date, nxt.act_by_week, lang)  # type: ignore[arg-type]

    def _next_step_view(self, goal: Goal, lang: str) -> dict[str, Any] | None:
        """The Goal tab's "next step" (SPEC §7.3): the first step not done, its act-by date, and whether
        a draft or checklist for it is ready in the chat."""
        from agent import drafts
        from tools import timeline as TL

        nxt = TL.next_open(goal.milestones)
        if nxt is None:
            return None
        return {
            "id": nxt.id,
            "label": tk.milestone_label(nxt.id, lang),  # type: ignore[arg-type]
            "act_by_date": month_label(goal.start_date, nxt.act_by_week, lang),  # type: ignore[arg-type]
            "status": TL.milestone_status(nxt, self.elapsed(goal)).value,
            "draft": "consent_request" if nxt.id == "lender_consent" else (
                "checklist" if drafts.has_draft(nxt.id) else None
            ),
        }

    def _welcome_ctx(self, goal: Goal, lang: str) -> dict[str, Any]:
        step, act_by = self._next_step(goal, lang)
        return {
            "goal_sentence": tk.goal_text(goal, lang, None, amounts=goal.email_amounts),  # type: ignore[arg-type]
            "next_step": step,
            "next_act_by": act_by,
            "url": f"{self.svc.base_url}/#/goal",
        }

    def _digest_ctx(self, goal: Goal, lang: str) -> dict[str, Any]:
        step, act_by = self._next_step(goal, lang)
        return {
            "status_line": _status_headline(goal.status.value, lang),
            "next_step": step,
            "next_act_by": act_by,
            "url": f"{self.svc.base_url}/#/goal",
        }

    def _alert_ctx(self, goal: Goal, alert: Alert, lang: str) -> dict[str, Any]:
        return {
            "headline": _alert_headline(alert, lang),
            "act_by": month_label(alert.act_by, 0, lang) if alert.act_by else None,  # type: ignore[arg-type]
            "url": f"{self.svc.base_url}/?alert={alert.id}",
        }

    def _milestone_reminders(self, goal: Goal, lang: str) -> None:
        el = self.elapsed(goal)
        rec = self._rec(goal.id)
        sent = set(rec.get("reminded", []))
        for m in goal.milestones:
            for days in (14, 3):
                key = f"{m.id}:{days}"
                if key in sent or m.status.value == "done":
                    continue
                if 0 <= (m.act_by_week - el) * 7 <= days:
                    self._email(
                        goal,
                        "milestone",
                        {
                            "step_label": tk.milestone_label(m.id, lang),  # type: ignore[arg-type]
                            "act_by": month_label(goal.start_date, m.act_by_week, lang),  # type: ignore[arg-type]
                            "url": f"{self.svc.base_url}/#/goal",
                        },
                        lang,
                    )
                    sent.add(key)
        self._save(goal, extra={"reminded": sorted(sent)})


# ------------------------------------------------------------------ helpers


def _late(goal: Goal, elapsed: int) -> list[str]:
    """Steps past their latest-safe week and not marked done."""
    return [m.id for m in goal.milestones if m.latest_safe_week < elapsed and m.done_at is None]


def _threshold(key: str) -> Decimal:
    """One of `status_thresholds` in data/params.yaml (a missing key is an error, never a default)."""
    return Decimal(str(P.table("status_thresholds")[key]))


def _status_for(moved: int, risk: Decimal, late: bool) -> GoalStatus:
    """SPEC §7.2 step 5: on track / at risk / off track from the move, the floor risk and late steps.

    On track: slipped at most `on_track_slip_weeks` and floor risk at most `at_risk_floor_risk`. At risk:
    slipped up to `at_risk_slip_weeks`, or floor risk up to `off_track_floor_risk`. Off track: beyond
    either, or a step past its latest-safe week."""
    if late or moved > _threshold("at_risk_slip_weeks") or risk > _threshold("off_track_floor_risk"):
        return GoalStatus.OFF_TRACK
    if moved > _threshold("on_track_slip_weeks") or risk > _threshold("at_risk_floor_risk"):
        return GoalStatus.AT_RISK
    return GoalStatus.ON_TRACK


def _shocks_from(items: list[dict[str, Any]]) -> list[Any]:
    """Rebuild the goal's simulated scenarios as feed shocks (sim.shocks)."""
    from sim import shocks as SH

    out: list[Any] = []
    for it in items:
        start = date.fromisoformat(it["start"])
        kind = it["kind"]
        if kind == "sales_dip":
            out += SH.demo_dip(start, after_weeks=0)
        elif kind == "channel_shift":
            out += SH.channel_shift_only(start, after_weeks=0)
        elif kind == "above_normal_draw":
            out += SH.above_normal_draw(start, after_weeks=0)
    return out


def _snapshot(state: JourneyState) -> dict[str, Any]:
    return {
        "unit_id": state.shortlist.chosen_unit_id,
        "cost_card": state.cost_card.model_dump(mode="json") if state.cost_card else None,
        "funding": state.funding.model_dump(mode="json") if state.funding else None,
        "profile": state.profile.model_dump(mode="json"),
        "consent_feed": state.consent_feed,
    }


def _shift(res: PlanResult, weeks: int) -> PlanResult:
    """Express a plan simulated from today in weeks from the goal's start."""
    if weeks == 0:
        return res
    chart = res.chart.model_copy(
        update={
            "weeks": [w + weeks for w in res.chart.weeks],
            "milestones": [(w + weeks, m) for w, m in res.chart.milestones],
        }
    )
    return res.model_copy(
        update={
            "open_likely_week": None if res.open_likely_week is None else res.open_likely_week + weeks,
            "open_p95_week": None if res.open_p95_week is None else res.open_p95_week + weeks,
            "milestone_weeks": {k: v + weeks for k, v in res.milestone_weeks.items()},
            "chart": chart,
        }
    )


def _replan_state(state: JourneyState, goal: Goal, today: date, saved: Decimal) -> JourneyState:
    """A copy of the journey positioned at today: money already saved counts as savings in hand."""
    s = state.model_copy(deep=True)
    s.start_date = today
    assert s.funding is not None
    s.funding = s.funding.model_copy(update={"own_savings_cny": s.funding.own_savings_cny + saved})
    return s


def _status_headline(status: str, lang: str) -> str:
    return {
        "on_track": ("进度正常", "On track"),
        "at_risk": ("略有延后", "Slipping a little"),
        "off_track": ("偏离计划", "Off track"),
    }[status][0 if lang == "zh" else 1]


def _changes(info: dict[str, Any], lang: str) -> list[str]:
    zh = lang == "zh"
    out = []
    moved = info.get("moved", 0)
    if moved is not None and moved < 999:
        if moved >= 2:
            out.append("预计开业时间推迟" if zh else "Your likely opening moved later")
        elif moved <= -2:
            out.append("预计开业时间提前" if zh else "Your likely opening moved earlier")
        else:
            out.append("开业时间基本不变" if zh else "Your opening date is holding")
    if info.get("r2"):
        out.append(
            "微业贷用款高于平时，储蓄暂停" if zh else "Set-aside paused: WeBank borrowing is above usual"
        )
    return out


def _day_label(d: date, lang: str) -> str:
    return f"{d.year}年{d.month}月{d.day}日" if lang == "zh" else f"{d.day} {d:%b %Y}"


def _alert_headline(alert: Alert, lang: str) -> str:
    zh = lang == "zh"
    return {
        "date_slip": "预计开业时间推迟了" if zh else "Your likely opening date has moved",
        "status_worse": "你的计划偏离了原定目标" if zh else "Your plan has slipped from the goal",
        "floor_risk": "门店现金跌破安全线的风险上升" if zh else "The risk to your home cash has gone up",
        "milestone_due": "有一个步骤快到期了" if zh else "A step is due soon",
        "r2_pause": "微业贷用款高于平时，储蓄已暂停"
        if zh
        else "Your set-aside is paused while borrowing is above usual",
    }.get(alert.kind, alert.kind)


def _plan_vs_actual(
    goal: Goal, res: PlanResult, checkins: list[dict[str, Any]], elapsed: int, lang: str
) -> PlanVsActual:
    weeks = res.chart.weeks
    horizon = min(len(weeks), max(goal.target_open_p95_week + 8, elapsed + 8))
    weeks = weeks[:horizon]
    actual_pot: list[float | None] = [None] * len(weeks)
    actual_profit: list[float | None] = [None] * len(weeks)
    for ci in checkins:
        w = int(ci.get("week", 0))
        if 0 <= w < len(weeks):
            actual_pot[w] = float(Decimal(str(ci.get("saved_cny", "0"))))
            if ci.get("profit_cny") is not None:
                actual_profit[w] = float(Decimal(str(ci["profit_cny"])))
    if actual_pot and actual_pot[0] is None:
        actual_pot[0] = float(res.chart.pot_p50[0]) if res.chart.pot_p50 else 0.0
    planned_profit = tk.planned_profit_series(goal, len(weeks))
    return PlanVsActual(
        weeks=weeks,
        month_labels=[month_label(goal.start_date, w, lang) for w in weeks],  # type: ignore[arg-type]
        planned_pot=res.chart.pot_p50[:horizon],
        actual_pot=actual_pot,
        planned_profit=planned_profit,
        actual_profit=actual_profit,
        milestones=[(m.likely_week, tk.milestone_label(m.id, lang)) for m in goal.milestones],  # type: ignore[arg-type]
        today_week=elapsed,
    )


def _utc(d: datetime) -> datetime:
    return d if d.tzinfo is not None else d.replace(tzinfo=UTC)

