"""`make demo`: the six demo moments (PITCH §7), seeded, through the real orchestrator.

Writes results/demo/transcript.md (what the owner, Joon Rui, sees), results/demo/audit.jsonl (verified with
agent.audit) and results/demo/demo.json (key computed values). Everything is simulated: the company
is fictional, the WeBank feed is mocked and unit listings are simulated. No model is used unless one
is configured; the run is labelled with the model id or "scripted".

Moment 6 has a paired control (results/prereg.md addendum 2026-10-20 (6)): the same seed and journey run
again with no scenario, and demo.json records every check of both runs, so it shows whether the sales dip,
not the seed's own noise, is what raises the alert.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "demo"
CHECKS, CHECK_WEEKS = 4, 4  # moment 6's window: four weekly-check runs, four weeks apart (16 weeks)


class Demo:
    def __init__(self, workdir: Path) -> None:
        os.environ.setdefault("WAYPOINT_VAR", str(workdir))
        os.environ["WAYPOINT_AUDIT"] = str(workdir / "audit.jsonl")
        from app.services import AppServices
        from app.store import Store

        self.svc = AppServices(
            Store(f"sqlite:///{workdir / 'demo.sqlite3'}"), base_url="http://127.0.0.1:8000", demo=True
        )
        self.user = self.svc.store.create_user(
            "embedded", email="joonrui@waypoint.test", webank_subject="webank:demo-chen", verified=True
        )
        self.state = self.svc.load_state(self.user)
        self.lines: list[str] = []
        self.outs: list[Any] = []

    # ---------------------------------------------------------------- driving

    def run(
        self, text: str | None = None, event: Any = None, init: bool = False, label: str | None = None
    ) -> None:
        if text:
            self.lines.append(f"> **Joon Rui:** {text}")
        elif label:
            self.lines.append(f"> **Joon Rui taps:** {label}")
        self.outs = asyncio.run(self.svc.orchestrator.run(self.state, text=text, event=event, init=init))
        self.svc.save_state(self.state)
        for o in self.outs:
            if o.kind == "text" and o.text:
                self.lines.append(f"**Waypoint:** {o.text}")
            elif o.kind == "widget" and o.widget is not None:
                self.lines.append(f"`[{o.widget.payload.type}]` {self._summ(o.widget)}")
        self.lines.append("")

    def _pending(self) -> Any:
        p = self.state.pending
        assert p is not None, f"no pending question at step {self.state.step}"
        return p

    def reply(self, value: str) -> None:
        from agent.widgets import WidgetEvent

        p = self._pending()
        label = next((o["label"] for o in p.options if o["value"] == value), value)
        self.run(event=WidgetEvent(widget_id=p.widget_id or "", event="reply", value=value), label=label)

    def event(
        self, wtype: str, event: str, value: Any = None, data: dict[str, Any] | None = None, label: str = ""
    ) -> None:
        from agent.widgets import WidgetEvent

        wid = max((k for k, v in self.state.widget_types.items() if v == wtype), key=lambda k: int(k[1:]))
        self.run(
            event=WidgetEvent(widget_id=wid, event=event, value=value, data=data or {}), label=label or event
        )  # type: ignore[arg-type]

    def widget(self, wtype: str) -> Any:
        return [o.widget for o in self.outs if o.kind == "widget" and o.widget.payload.type == wtype][-1]

    def _summ(self, w: Any) -> str:
        p, d = w.payload, w.display
        t = p.type
        if t == "quick_replies":
            return " · ".join(o.label for o in p.options)
        if t == "area_map":
            names = {a.id: a.name for a in p.areas}
            return "top: " + ", ".join(f"{names[a]} ({'; '.join(p.reasons.get(a, []))})" for a in p.top)
        if t == "unit_compare":
            return " | ".join(
                f"{u.mall} {u.unit_no}: {d.get(u.rent, '')}/month, break-even {d.get(u.breakeven, '')}"
                for u in p.units
            )
        if t == "business_glance":
            rows = [*p.rows, *p.singapore]
            def cmp(r: Any) -> str:
                return f" ({r.compare_label} {d.get(r.compare, '')})" if r.compare else ""

            return " | ".join(f"{r.label} {d.get(r.figure, '')}{cmp(r)}" for r in rows)
        if t == "unit_economics":
            head = "; ".join(f"{ln.label}: {d.get(ln.figure, '')}" for ln in p.headline)
            pnl = " | ".join(
                f"{d.get(r.cups, '')}: EBITDA {d.get(r.ebitda, '')}/month, "
                f"payback {d.get(r.payback_likely, '')} (badly {d.get(r.payback_bad, '')}), "
                f"NPV {d.get(r.npv, '')}"
                for r in p.rows
            )
            return f"{head} || {pnl}"
        if t == "cost_breakdown":
            return f"likely {d.get(p.total_likely)}, if things go badly {d.get(p.total_bad)} ({d.get(p.total_likely_cny)})"  # noqa: E501
        if t == "setaside_slider":
            return (
                f"share {p.share:.0%} (wall {p.wall:.0%}): likely {d.get(p.open_likely)}, badly {d.get(p.open_p95)}, "  # noqa: E501
                f"floor risk {d.get(p.floor_risk)}, {d.get(p.monthly_amount)}/month"
            )
        if t in ("rule_card",):
            return f"{p.rule_id}: {p.title} — {p.message}"
        if t == "topic_card":
            return p.title
        if t == "upload_prompt":
            return (
                f"{len(p.extracted)} lines read ({p.reader_mode}); excluded: {', '.join(p.exclusions)}"
                if p.extracted
                else "upload"
            )
        if t == "milestone_timeline":
            return " → ".join(f"{i.label} ({i.likely_date})" for i in p.items)
        if t == "approval_card":
            return f"{p.title}: " + "; ".join(f"{ln.label}: {ln.value}" for ln in p.lines)
        if t == "status_card":
            return f"{p.status}: {p.headline}"
        if t == "alert_card":
            return p.headline
        if t == "repair_options":
            return " | ".join(f"{r.label} → {d.get(r.new_open_likely, '')}" for r in p.repairs)
        if t == "goal_summary":
            return p.sentence
        if t == "funding_mix":
            return ", ".join(f"{s.label} {d.get(s.amount, '')}" for s in p.segments)
        return ""

    # ---------------------------------------------------------------- the six moments

    def script(self) -> dict[str, Any]:
        out = self.journey()
        heading = len(self.lines)
        self.lines += ["", ""]  # "## 6. N weeks later", filled in once the alert has come
        # Demo control: a simulated sales dip at four of the home shops starts in the first month.
        checks = self.weeks_later("sales_dip", stop_at_alert=True)
        alert_id = next((c["alert"] for c in checks if c["alert"]), None)
        weeks = checks[-1]["week"]
        self.lines[heading] = f"## 6. {weeks} weeks later"
        out["checks"] = checks
        out["alert_after_weeks"] = weeks if alert_id else None
        self.lines.append("")
        self.state = self.svc.load_state(self.user)
        out["alert"] = alert_id
        if alert_id:
            self._repair(alert_id, out)
        out["emails"] = [
            {"template": e["template"], "delivered": e["delivered"]}
            for e in self.svc.store.emails_for(self.user["id"])
        ]
        return out

    def weeks_later(self, scenario: str, stop_at_alert: bool) -> list[dict[str, Any]]:
        """Move the demo clock four weeks at a time (the weekly check runs each time) and record each check.
        The scenario, if any, starts at the first move."""
        assert self.state.goal_id
        gid = self.state.goal_id
        out: list[dict[str, Any]] = []
        for i in range(CHECKS):
            r = self.svc.advance(self.user, CHECK_WEEKS, scenario=scenario if i == 0 else "none")
            dip = "; simulated four-shop sales dip started" if i == 0 and scenario == "sales_dip" else ""
            self.lines.append(f"_(clock moved to {r['today']}; weekly check ran{dip})_")
            rec = self.svc.store.goal(gid) or {}
            ci = (self.svc.store.checkins_for(gid) or [{}])[-1]
            alerts = self.svc.store.alerts_for(gid)
            latest = rec.get("latest") or {}
            out.append(
                {
                    "week": CHECK_WEEKS * (i + 1),
                    "today": r["today"],
                    "status": rec["goal"]["status"],
                    "likely_week": latest.get("likely"),
                    "floor_risk": latest.get("risk"),
                    "detector_alarm": bool(ci.get("drop")),
                    "alerts": len(alerts),
                    "alert": alerts[-1]["id"] if alerts else None,
                }
            )
            if alerts and stop_at_alert:
                break
        return out

    def _repair(self, alert_id: str, out: dict[str, Any]) -> None:
        from agent.widgets import WidgetEvent

        self.run(
            event=WidgetEvent(widget_id="", event="see_repairs", value=alert_id),
            label="Open the alert email link",
        )
        rep = self.widget("repair_options")
        if rep.payload.repairs:
            pick = rep.payload.repairs[0]
            self.event(
                "repair_options", "select_repair", pick.id, data={"alert_id": alert_id}, label=pick.label
            )
            card = self.widget("approval_card")
            self.event(
                "approval_card",
                "approve",
                data={"card_hash": card.payload.card_hash},
                label="Update my goal",
            )
            assert self.state.goal_id
            g = self.svc.gk.goal(self.state.goal_id)
            out["revised"] = {
                "open_likely_week": g.target_open_likely_week,
                "revisions": len(g.revisions),
            }

    def journey(self) -> dict[str, Any]:
        """Moments 1-5: from hello to the approved goal."""
        out: dict[str, Any] = {}
        self.lines += [
            "# Waypoint demo transcript (simulated)",
            "",
            f"Model: {self.svc.llm_label()} · seed {self.svc.seed} · company fictional · WeBank feed mocked · units simulated",  # noqa: E501
            "",
        ]
        self.lines += ["## 1. Hello", ""]
        self.run(init=True)  # the WeBank SSO owner starts on the consent card
        self.event("consent_card", "consent", True, label="Agree")
        for v in ("young_adults", "b2", "12_18"):
            self.reply(v)
        self.event("confirm_card", "confirm", "profile", label="That's right")

        self.lines += ["## 2. Where", ""]
        self.reply("near_customers")
        out["top_areas"] = [a.area_id for a in self.state.shortlist.ranked[:3]]
        areas = [o["value"] for o in self._pending().options]
        self.reply("TAMPINES" if "TAMPINES" in areas else areas[0])
        unit_id = self._pending().options[0]["value"]
        self.reply(unit_id)  # picking the unit is the confirmation
        out["unit"] = unit_id

        self.lines += ["## 3. What it costs", ""]
        self.reply("add_quote")
        self.reply("demo_quote")
        up = self.widget("upload_prompt")
        for row in up.payload.extracted:
            self.event("upload_prompt", "accept_line", row.id, label=f"Accept {row.label}")
        assert self.state.cost_card is not None
        out["cost_likely_sgd_parts_only"] = str(self.state.cost_card.total_likely_sgd)
        for cov in up.payload.coverage:  # the owner says the contractor's quote is the whole fit-out
            self.event(
                "upload_prompt",
                "set_coverage",
                cov.key,
                {"doc_id": up.payload.doc_id, "key": cov.key, "whole": True},
                label=f"This quote covers all of {cov.label}",
            )
        assert self.state.cost_card is not None
        out["cost_likely_sgd"] = str(self.state.cost_card.total_likely_sgd)
        out["cost_bad_sgd"] = str(self.state.cost_card.total_bad_sgd)
        self.reply("looks_right")

        self.lines += ["## 4. How to pay", ""]
        self.run(text="Just use my WeBank line for now")
        out["guard_rule"] = self.widget("rule_card").payload.rule_id
        sl = None
        for share in ("0.30", "0.50", "0.40"):
            self.event("setaside_slider", "slider_commit", share, label=f"Slide to {float(share):.0%}")
            sl = self.widget("setaside_slider")
            out[f"slider_{share}"] = {
                k: sl.display.get(getattr(sl.payload, k))
                for k in ("open_likely", "open_p95", "floor_risk", "monthly_amount")
            }
        out["wall"] = sl.payload.wall if sl else None
        self.reply("looks_good")

        self.lines += ["## 5. Your plan", ""]
        card = self.widget("approval_card")
        self.event(
            "approval_card", "approve", data={"card_hash": card.payload.card_hash}, label="Start my goal"
        )
        assert self.state.goal_id
        g = self.svc.gk.goal(self.state.goal_id)
        out["goal"] = {
            "open_likely_week": g.target_open_likely_week,
            "open_p95_week": g.target_open_p95_week,
            "setaside_monthly_cny": str(g.setaside_monthly_cny),
            "floor_risk": str(g.floor_risk),
        }

        return out


def paired_control(result: dict[str, Any] | None = None) -> dict[str, Any]:
    """The same seed and journey with no scenario, checked over the same window as moment 6."""
    from mock_webank import feed as mw

    control = Demo(Path(tempfile.mkdtemp(prefix="waypoint-demo-control-")))
    goal = control.journey()["goal"]
    checks = control.weeks_later("none", stop_at_alert=False)
    return {
        "what": "the same seed and journey, no scenario, checked every 4 weeks for 16 weeks",
        "seed": mw.scenario_for(control.user["id"]).seed,
        "same_goal": None if result is None else goal == result["goal"],
        "goal": goal,
        "checks": checks,
        "alerts": checks[-1]["alerts"],
        "detector_alarm": any(c["detector_alarm"] for c in checks),
    }


def main() -> None:
    from agent import llm, voice

    work = Path(tempfile.mkdtemp(prefix="waypoint-demo-"))
    have_model, why = asyncio.run(llm.preflight("voice"))
    if not have_model:
        print(f"No working model ({why}); using the deterministic test composer. Messages show beat ids.")
        voice.set_test_composer(voice.echo_composer)
        os.environ["WAYPOINT_LLM_PROVIDER"] = "none"
        os.environ["WAYPOINT_READER_REPLAY"] = "1"
    demo = Demo(work)
    result = demo.script()
    result["control"] = paired_control(result)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "transcript.md").write_text("\n".join(demo.lines) + "\n", encoding="utf-8")
    shutil.copy(work / "audit.jsonl", OUT / "audit.jsonl")
    from agent.audit import verify

    ok, seq, msg = verify(OUT / "audit.jsonl")
    result["audit_log"] = {"verified": ok, "message": msg}
    result["model"] = demo.svc.llm_label() if have_model else f"none (test composer; preflight: {why})"
    result["simulated"] = True
    (OUT / "demo.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not ok:
        raise SystemExit(f"audit log failed verification at {seq}")


if __name__ == "__main__":
    main()
