"""App services the orchestrator and routes share: state, documents, goals, emails, demo clock."""

from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from agent import llm
from agent.audit import AuditLog
from agent.audit import proof as audit_proof
from agent.orchestrator import Orchestrator
from agent.reader import read_document
from agent.state import JourneyState
from app.email import sender
from app.store import VAR, Store
from tools import params as P
from tools.models import ExtractedQuote, HostMode

log = logging.getLogger(__name__)
DEMO_QUOTE = Path(__file__).resolve().parents[1] / "data" / "demo" / "docs" / "fitout_quote.png"
DEMO_TODAY = date(2026, 10, 19)


class AppServices:
    def __init__(self, store: Store, base_url: str, demo: bool) -> None:
        self.store = store
        self.base_url = base_url.rstrip("/")
        self._demo = demo
        self.audit = AuditLog(Path(os.environ.get("WAYPOINT_AUDIT", VAR / "audit.jsonl")))
        self.seed = P.default_seed()
        self.docs_dir = VAR / "docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.orchestrator = Orchestrator(self, self.audit)
        from app import goalkeeper

        self.gk = goalkeeper.GoalKeeper(self)

    # ---------------------------------------------------------------- clock and flags

    def demo(self) -> bool:
        return self._demo

    def today(self) -> date:
        base = DEMO_TODAY if self._demo else date.today()
        return base + timedelta(weeks=self.store.clock_offset_weeks())

    def llm_label(self) -> str:
        return llm.model_label("turn")

    # ---------------------------------------------------------------- journey state

    def load_state(self, user: dict[str, Any]) -> JourneyState:
        raw = self.store.load_journey(user["id"])
        if raw:
            return JourneyState.model_validate(raw)
        settings = user.get("settings") or {}
        return JourneyState(
            owner_id=user["id"],
            host_mode=HostMode(user["host_mode"]),
            lang=settings.get("lang", "en"),
            start_date=self.today(),
        )

    def save_state(self, state: JourneyState) -> None:
        self.store.save_journey(state.owner_id, state.model_dump(mode="json"))
        # a language switched in the chat is the owner's language: reminders and the UI follow it
        user = self.store.user(state.owner_id)
        if user is not None:
            settings = dict(user.get("settings") or {})
            if settings.get("lang") != state.lang:
                settings["lang"] = state.lang
                self.store.update_user(state.owner_id, settings=settings)

    # ---------------------------------------------------------------- documents

    async def ingest_document(self, user_id: str, filename: str, mime: str, data: bytes) -> str:
        """Read (quarantined), redact, then store only the redacted copy and the original's hash."""
        import hashlib

        doc_id = "d_" + secrets.token_hex(6)
        res = await read_document(doc_id, data, mime)
        path = ""
        if res.redacted_png is not None:
            p = self.docs_dir / f"{doc_id}.png"
            p.write_bytes(res.redacted_png)
            path = str(p)
        self.store.add_document(
            {
                "id": doc_id,
                "user_id": user_id,
                "filename": filename[:120],
                "mime": mime[:60],
                "sha256_original": hashlib.sha256(data).hexdigest(),
                "redacted_path": path,
                "extracted": {
                    **res.quote.model_dump(mode="json"),
                    "ignored_text_count": len(res.ignored_text),
                },
                "reader_mode": res.mode,
            }
        )
        self.audit.append(
            "document",
            user_id,
            doc_id=doc_id,
            mode=res.mode,
            lines=len(res.quote.lines),
            ignored_instructions=len(res.ignored_text),
        )
        return doc_id

    def ingest_demo_quote(self, user_id: str) -> str:
        import asyncio

        data = DEMO_QUOTE.read_bytes()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.ingest_document(user_id, DEMO_QUOTE.name, "image/png", data))
        # inside the event loop (an AG-UI run): read synchronously via a worker thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(1) as ex:
            return ex.submit(
                asyncio.run, self.ingest_document(user_id, DEMO_QUOTE.name, "image/png", data)
            ).result()

    def load_quote(
        self, user_id: str, doc_id: str
    ) -> tuple[ExtractedQuote | None, str, str | None, list[str]]:
        doc = self.store.document(doc_id)
        if doc is None or doc["user_id"] != user_id:
            return None, "none", None, []
        ext = dict(doc["extracted"] or {})
        n_ignored = int(ext.pop("ignored_text_count", 0))
        quote = ExtractedQuote.model_validate(ext) if ext else None
        url = f"/api/docs/{doc_id}/image" if doc["redacted_path"] else None
        return quote, doc["reader_mode"] or "none", url, ["ignored"] * n_ignored

    def documents_view(self, user_id: str) -> dict[str, Any]:
        uploads = []
        for d in self.store.documents_for(user_id):
            ext = d["extracted"] or {}
            uploads.append(
                {
                    "id": d["id"],
                    "filename": d["filename"],
                    "reader_mode": d["reader_mode"],
                    "image_url": f"/api/docs/{d['id']}/image" if d["redacted_path"] else None,
                    "lines": [
                        {
                            "label": ln["label"],
                            "amount": ln["amount"],
                            "currency": ln.get("currency", "SGD"),
                            "status": ln.get("status"),
                        }
                        for ln in ext.get("lines", [])
                    ],
                    "exclusions": ext.get("exclusions", []),
                    "ignored_instructions": ext.get("ignored_text_count", 0),
                    "created_at": d["created_at"].isoformat() if d["created_at"] else None,
                }
            )
        return {"uploads": uploads, "sources": data_sources()}

    # ---------------------------------------------------------------- account and consent

    def account_view(self, user: dict[str, Any]) -> dict[str, Any]:
        settings = user.get("settings") or {}
        return {
            "email": user["email"],
            "email_verified": user["email_verified"],
            "host_mode": user["host_mode"],
            "lang": settings.get("lang", "en"),
            "checkin_frequency": settings.get("checkin_frequency", "monthly"),
            "email_amounts": bool(settings.get("email_amounts", False)),
            "consent_feed": self.load_state(user).consent_feed,
        }

    def account_update(self, user: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        settings = dict(user.get("settings") or {})
        state = self.load_state(user)
        if "lang" in patch and patch["lang"] in ("en", "zh"):
            settings["lang"] = patch["lang"]
            state.lang = patch["lang"]
            state.lang_chosen = True
        if patch.get("checkin_frequency") in ("weekly", "fortnightly", "monthly"):
            settings["checkin_frequency"] = patch["checkin_frequency"]
        if "email_amounts" in patch:
            settings["email_amounts"] = bool(patch["email_amounts"])
        self.store.update_user(user["id"], settings=settings)
        if "email" in patch and patch["email"]:
            from app import auth

            email = str(patch["email"]).strip().lower()
            if auth.valid_email(email) and auth.per_email.allow(email):
                token = self.store.new_magic_link(email, "verify_email", user["id"])
                sender.send(
                    self.store,
                    email,
                    "verify_email",
                    settings.get("lang", "en"),
                    {"url": f"{self.base_url}/api/auth/verify?token={token}", "demo": self._demo},
                    user["id"],
                )
        if state.goal_id:
            self.gk.update_prefs(state.goal_id, settings)
        self.save_state(state)
        self.audit.append("account_update", user["id"], fields=sorted(patch))
        fresh = self.store.user(user["id"]) or user
        return self.account_view(fresh)

    def export_user(self, user: dict[str, Any]) -> dict[str, Any]:
        uid = user["id"]
        goals = [g for g in self.store.active_goals() if g[1] == uid]
        return {
            "account": self.account_view(user),
            "journey": self.store.load_journey(uid),
            "transcript": [
                {"role": m["role"], "kind": m["kind"], "content": m["content"]}
                for m in self.store.transcript(uid)
            ],
            "documents": self.documents_view(uid)["uploads"],
            "goals": [{"id": gid, "data": rec} for gid, _, rec in goals],
            "emails": [
                {"template": e["template"], "subject": e["subject"], "delivered": e["delivered"]}
                for e in self.store.emails_for(uid)
            ],
            "audit_proof": audit_proof(self.audit.path, uid),
            "note": "Simulated demo data. Redacted document images only; originals are never stored.",
        }

    def delete_user(self, user: dict[str, Any]) -> None:
        uid = user["id"]
        for d in self.store.documents_for(uid):
            if d["redacted_path"]:
                Path(d["redacted_path"]).unlink(missing_ok=True)
        self.store.delete_user(uid)
        from mock_webank import instructions as MI

        MI.reset(uid)
        self.audit.append("account_deleted", uid)

    def withdraw_consent(self, user: dict[str, Any]) -> dict[str, Any]:
        state = self.load_state(user)
        state.consent_feed = False
        self.save_state(state)
        self.audit.append("consent", user["id"], granted=False, via="account")
        return self.account_view(user)

    # ---------------------------------------------------------------- goals (delegated to the Goal Keeper)

    def create_goal(self, state: JourneyState, card_hash: str) -> str:
        return self.gk.create(state, card_hash)

    def revise_goal(self, state: JourneyState, card_hash: str, reason: str) -> None:
        self.gk.revise(state, card_hash, reason)

    def goal_dashboard(self, state: JourneyState) -> dict[str, Any]:
        return self.gk.dashboard(state)

    def owner_checkin(self, state: JourneyState, data: dict[str, Any]) -> dict[str, Any]:
        return self.gk.owner_checkin(state, data)

    def alert_view(self, state: JourneyState, alert_id: str, lang: str) -> dict[str, Any] | None:
        return self.gk.alert_view(state, alert_id, lang)

    def apply_repair_to_state(self, state: JourneyState, alert_id: str, repair_id: str) -> None:
        self.gk.apply_repair(state, alert_id, repair_id)

    def replan_for_revision(self, state: JourneyState) -> Any:
        return self.gk.replan(state)[0]

    def user_pref(self, owner_id: str, key: str, default: Any) -> Any:
        user = self.store.user(owner_id)
        return ((user or {}).get("settings") or {}).get(key, default)

    def history(self, owner_id: str, n: int = 8) -> list[str]:
        """The last few messages, for the voice's context (text only)."""
        rows = self.store.transcript(owner_id)[-(n * 3) :]
        out = []
        for r in rows:
            if r["kind"] != "text":
                continue
            who = "Owner" if r["role"] == "user" else "Waypoint"
            out.append(f"{who}: {r['content'].get('text', '')}")
        return out[-n:]

    def show_checkin(self, t: Any, period: str | None = None) -> None:
        self.gk.show_checkin(t, period)

    def checkin_link(self, state: JourneyState, token: str) -> str | None:
        return self.gk.checkin_link(state, token)

    def setaside_offer(self, state: JourneyState) -> dict[str, Any] | None:
        """The monthly set-aside card's content when one is due: its terms, its lines and the rules
        holding it back today (none means it can be prepared)."""
        if not self.gk.setaside_needed(state):
            return None
        terms = self.gk.setaside_terms(state)
        return {
            "terms": terms,
            "lines": self.gk.setaside_lines(state, terms),
            "blockers": self.gk.setaside_blockers(state),
        }

    def setaside_terms(self, state: JourneyState) -> dict[str, Any]:
        return self.gk.setaside_terms(state)

    def setaside_blockers(self, state: JourneyState) -> list[str]:
        return self.gk.setaside_blockers(state)

    def prepare_setaside(self, state: JourneyState, card_hash: str) -> dict[str, Any]:
        return self.gk.prepare_setaside(state, card_hash)

    def advance(self, user: dict[str, Any], weeks: int, scenario: str = "none") -> dict[str, Any]:
        """Demo clock: optionally start a simulated scenario today, move the clock, run the weekly check."""
        if scenario != "none":
            self.gk.add_scenario(user, scenario, self.today())
        offset = self.store.advance_clock(weeks)
        ran = self.run_scheduled()
        return {
            "offset_weeks": offset,
            "today": self.today().isoformat(),
            "checks": ran["checks"],
            "emails": ran["emails"],
            "scenario": scenario,
        }

    def run_scheduled(self) -> dict[str, int]:
        """The weekly Goal Keeper job (app/scheduler.py runs it on a timer; the demo clock runs it too)."""
        return self.gk.run_due()

    def mark_milestone_done(self, state: JourneyState, mid: str) -> Any:
        return self.gk.mark_milestone_done(state, mid)

    def consent_draft(self, state: JourneyState, lang: str) -> Any:
        return self.gk.consent_draft(state, lang)


def data_sources() -> list[dict[str, Any]]:
    """Public and simulated data sources, with dates (Documents tab)."""
    out: list[dict[str, Any]] = []
    src = Path(__file__).resolve().parents[1] / "data" / "public" / "sources.json"
    if src.exists():
        out.extend(json.loads(src.read_text(encoding="utf-8")))
    out.append(
        {
            "label": "Unit listings",
            "publisher": "Simulated for the demo",
            "as_of": "2026-10",
            "simulated": True,
        }
    )
    out.append(
        {
            "label": "Business accounts (WeBank feed)",
            "publisher": "Mocked; fictional company",
            "as_of": "2026-10",
            "simulated": True,
        }
    )
    for key in ("fx_cny_per_sgd", "gst_rate"):
        try:
            prm = P.param(key)
            out.append(
                {"label": key, "publisher": prm.source, "as_of": str(prm.as_of or ""), "simulated": False}
            )
        except KeyError:
            pass
    return out
