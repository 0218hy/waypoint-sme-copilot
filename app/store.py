"""Persistence (SQLite for the demo, Postgres-ready via SQLAlchemy Core)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine

ROOT = Path(__file__).resolve().parents[1]
VAR = Path(os.environ.get("WAYPOINT_VAR", ROOT / "var"))

md = MetaData()

users = Table(
    "users",
    md,
    Column("id", String, primary_key=True),
    Column("email", String, unique=True, nullable=True),
    Column("email_verified", Boolean, default=False),
    Column("host_mode", String, nullable=False),
    Column("webank_subject", String, unique=True, nullable=True),
    Column("settings", JSON, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
magic_links = Table(
    "magic_links",
    md,
    Column("token_hash", String, primary_key=True),
    Column("email", String, nullable=False),
    Column("purpose", String, nullable=False),  # sign_in | verify_email
    Column("user_id", String, nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("used_at", DateTime(timezone=True), nullable=True),
)
sessions = Table(
    "sessions",
    md,
    Column("id_hash", String, primary_key=True),
    Column("user_id", String, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
journeys = Table(
    "journeys",
    md,
    Column("user_id", String, primary_key=True),
    Column("state", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
messages = Table(
    "messages",
    md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=False, index=True),
    Column("msg_id", String, nullable=False),
    Column("role", String, nullable=False),  # user | assistant
    Column("kind", String, nullable=False),  # text | widget
    Column("content", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
documents = Table(
    "documents",
    md,
    Column("id", String, primary_key=True),
    Column("user_id", String, nullable=False, index=True),
    Column("filename", String, nullable=False),
    Column("mime", String, nullable=False),
    Column("sha256_original", String, nullable=False),
    Column("redacted_path", String, nullable=False),
    Column("extracted", JSON, nullable=True),
    Column("reader_mode", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
goals = Table(
    "goals",
    md,
    Column("id", String, primary_key=True),
    Column("user_id", String, nullable=False, index=True),
    Column("data", JSON, nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
checkins = Table(
    "checkins",
    md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("goal_id", String, nullable=False, index=True),
    Column("data", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
alerts = Table(
    "alerts",
    md,
    Column("id", String, primary_key=True),
    Column("goal_id", String, nullable=False, index=True),
    Column("data", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
emails = Table(
    "emails",
    md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=True),
    Column("to_hash", String, nullable=False),
    Column("template", String, nullable=False),
    Column("subject", Text, nullable=False),
    Column("delivered", Boolean, nullable=False),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
clock = Table(
    "clock",
    md,
    Column("id", Integer, primary_key=True),
    Column("offset_weeks", Integer, nullable=False, default=0),
)


def now() -> datetime:
    return datetime.now(UTC)


def h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, url: str | None = None) -> None:
        if url is None:
            VAR.mkdir(parents=True, exist_ok=True)
            url = os.environ.get("WAYPOINT_DB_URL", f"sqlite:///{VAR / 'waypoint.sqlite3'}")
        self.engine: Engine = create_engine(url, future=True)
        md.create_all(self.engine)

    @contextmanager
    def tx(self) -> Iterator[Connection]:
        with self.engine.begin() as conn:
            yield conn

    # ---------------------------------------------------------------- users and sessions

    def user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.tx() as c:
            row = c.execute(select(users).where(users.c.email == email.lower())).mappings().first()
            return dict(row) if row else None

    def user(self, user_id: str) -> dict[str, Any] | None:
        with self.tx() as c:
            row = c.execute(select(users).where(users.c.id == user_id)).mappings().first()
            return dict(row) if row else None

    def user_by_webank(self, subject: str) -> dict[str, Any] | None:
        with self.tx() as c:
            row = c.execute(select(users).where(users.c.webank_subject == subject)).mappings().first()
            return dict(row) if row else None

    def create_user(
        self,
        host_mode: str,
        email: str | None = None,
        webank_subject: str | None = None,
        verified: bool = False,
        lang: str = "en",
    ) -> dict[str, Any]:
        uid = "u_" + secrets.token_hex(8)
        row = {
            "id": uid,
            "email": email.lower() if email else None,
            "email_verified": verified,
            "host_mode": host_mode,
            "webank_subject": webank_subject,
            "settings": {"lang": lang if lang in ("en", "zh") else "en", "checkin_frequency": "monthly",
                         "email_amounts": False},
            "created_at": now(),
        }
        with self.tx() as c:
            c.execute(insert(users).values(**row))
        return row

    def update_user(self, user_id: str, **fields: Any) -> None:
        with self.tx() as c:
            c.execute(update(users).where(users.c.id == user_id).values(**fields))

    def new_magic_link(self, email: str, purpose: str, user_id: str | None, ttl_minutes: int = 15) -> str:
        token = secrets.token_urlsafe(32)
        with self.tx() as c:
            c.execute(
                insert(magic_links).values(
                    token_hash=h(token),
                    email=email.lower(),
                    purpose=purpose,
                    user_id=user_id,
                    expires_at=now() + timedelta(minutes=ttl_minutes),
                    used_at=None,
                )
            )
        return token

    def consume_magic_link(self, token: str) -> dict[str, Any] | None:
        """Single use, unexpired. Returns the link row or None."""
        with self.tx() as c:
            row = (
                c.execute(select(magic_links).where(magic_links.c.token_hash == h(token))).mappings().first()
            )
            if row is None or row["used_at"] is not None:
                return None
            exp = row["expires_at"]
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if exp < now():
                return None
            c.execute(update(magic_links).where(magic_links.c.token_hash == h(token)).values(used_at=now()))
            return dict(row)

    def recent_links(self, email: str, minutes: int = 15) -> int:
        with self.tx() as c:
            rows = c.execute(select(magic_links).where(magic_links.c.email == email.lower())).mappings().all()
        cutoff = now() - timedelta(minutes=minutes)
        n = 0
        for r in rows:
            created = r["expires_at"]
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if created - timedelta(minutes=15) > cutoff:
                n += 1
        return n

    def new_session(self, user_id: str, days: int = 14) -> str:
        sid = secrets.token_urlsafe(32)
        with self.tx() as c:
            c.execute(
                insert(sessions).values(
                    id_hash=h(sid), user_id=user_id, expires_at=now() + timedelta(days=days)
                )
            )
        return sid

    def session_user(self, sid: str | None) -> dict[str, Any] | None:
        if not sid:
            return None
        with self.tx() as c:
            row = c.execute(select(sessions).where(sessions.c.id_hash == h(sid))).mappings().first()
        if row is None:
            return None
        exp = row["expires_at"]
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if exp < now():
            return None
        return self.user(row["user_id"])

    def end_session(self, sid: str) -> None:
        with self.tx() as c:
            c.execute(sessions.delete().where(sessions.c.id_hash == h(sid)))

    # ---------------------------------------------------------------- journey and transcript

    def load_journey(self, user_id: str) -> dict[str, Any] | None:
        with self.tx() as c:
            row = c.execute(select(journeys.c.state).where(journeys.c.user_id == user_id)).first()
            return dict(row[0]) if row else None

    def save_journey(self, user_id: str, state: dict[str, Any]) -> None:
        payload = json.loads(json.dumps(state, default=str))
        with self.tx() as c:
            exists = c.execute(select(journeys.c.user_id).where(journeys.c.user_id == user_id)).first()
            if exists:
                c.execute(
                    update(journeys)
                    .where(journeys.c.user_id == user_id)
                    .values(state=payload, updated_at=now())
                )
            else:
                c.execute(insert(journeys).values(user_id=user_id, state=payload, updated_at=now()))

    def add_message(self, user_id: str, msg_id: str, role: str, kind: str, content: dict[str, Any]) -> None:
        payload = json.loads(json.dumps(content, default=str))
        with self.tx() as c:
            c.execute(
                insert(messages).values(
                    user_id=user_id, msg_id=msg_id, role=role, kind=kind, content=payload, created_at=now()
                )
            )

    def transcript(self, user_id: str) -> list[dict[str, Any]]:
        with self.tx() as c:
            rows = (
                c.execute(select(messages).where(messages.c.user_id == user_id).order_by(messages.c.id))
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]

    # ---------------------------------------------------------------- documents

    def add_document(self, row: dict[str, Any]) -> None:
        with self.tx() as c:
            c.execute(insert(documents).values(**row, created_at=now()))

    def document(self, doc_id: str) -> dict[str, Any] | None:
        with self.tx() as c:
            row = c.execute(select(documents).where(documents.c.id == doc_id)).mappings().first()
            return dict(row) if row else None

    def update_document(self, doc_id: str, **fields: Any) -> None:
        fields = json.loads(json.dumps(fields, default=str))
        with self.tx() as c:
            c.execute(update(documents).where(documents.c.id == doc_id).values(**fields))

    def documents_for(self, user_id: str) -> list[dict[str, Any]]:
        with self.tx() as c:
            rows = (
                c.execute(
                    select(documents).where(documents.c.user_id == user_id).order_by(documents.c.created_at)
                )
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]

    # ---------------------------------------------------------------- goals

    def save_goal(self, goal_id: str, user_id: str, data: dict[str, Any]) -> None:
        payload = json.loads(json.dumps(data, default=str))
        with self.tx() as c:
            exists = c.execute(select(goals.c.id).where(goals.c.id == goal_id)).first()
            if exists:
                c.execute(update(goals).where(goals.c.id == goal_id).values(data=payload, updated_at=now()))
            else:
                c.execute(
                    insert(goals).values(
                        id=goal_id, user_id=user_id, data=payload, active=True, updated_at=now()
                    )
                )

    def goal(self, goal_id: str) -> dict[str, Any] | None:
        with self.tx() as c:
            row = c.execute(select(goals.c.data).where(goals.c.id == goal_id)).first()
            return dict(row[0]) if row else None

    def active_goals(self) -> list[tuple[str, str, dict[str, Any]]]:
        with self.tx() as c:
            rows = c.execute(
                select(goals.c.id, goals.c.user_id, goals.c.data).where(goals.c.active.is_(True))
            ).all()
            return [(r[0], r[1], dict(r[2])) for r in rows]

    def add_checkin(self, goal_id: str, data: dict[str, Any]) -> None:
        payload = json.loads(json.dumps(data, default=str))
        with self.tx() as c:
            c.execute(insert(checkins).values(goal_id=goal_id, data=payload, created_at=now()))

    def checkins_for(self, goal_id: str) -> list[dict[str, Any]]:
        with self.tx() as c:
            rows = c.execute(
                select(checkins.c.data).where(checkins.c.goal_id == goal_id).order_by(checkins.c.id)
            ).all()
            return [dict(r[0]) for r in rows]

    def save_alert(self, alert_id: str, goal_id: str, data: dict[str, Any]) -> None:
        payload = json.loads(json.dumps(data, default=str))
        with self.tx() as c:
            exists = c.execute(select(alerts.c.id).where(alerts.c.id == alert_id)).first()
            if exists:
                c.execute(update(alerts).where(alerts.c.id == alert_id).values(data=payload))
            else:
                c.execute(insert(alerts).values(id=alert_id, goal_id=goal_id, data=payload, created_at=now()))

    def alerts_for(self, goal_id: str) -> list[dict[str, Any]]:
        with self.tx() as c:
            rows = c.execute(
                select(alerts.c.data).where(alerts.c.goal_id == goal_id).order_by(alerts.c.created_at)
            ).all()
            return [dict(r[0]) for r in rows]

    def delete_user(self, user_id: str) -> None:
        with self.tx() as c:
            gids = [r[0] for r in c.execute(select(goals.c.id).where(goals.c.user_id == user_id)).all()]
            for gid in gids:
                c.execute(checkins.delete().where(checkins.c.goal_id == gid))
                c.execute(alerts.delete().where(alerts.c.goal_id == gid))
            c.execute(goals.delete().where(goals.c.user_id == user_id))
            c.execute(documents.delete().where(documents.c.user_id == user_id))
            c.execute(messages.delete().where(messages.c.user_id == user_id))
            c.execute(journeys.delete().where(journeys.c.user_id == user_id))
            c.execute(sessions.delete().where(sessions.c.user_id == user_id))
            c.execute(emails.delete().where(emails.c.user_id == user_id))
            c.execute(users.delete().where(users.c.id == user_id))

    # ---------------------------------------------------------------- email log and demo clock

    def log_email(
        self, user_id: str | None, to: str, template: str, subject: str, delivered: bool, error: str | None
    ) -> None:
        with self.tx() as c:
            c.execute(
                insert(emails).values(
                    user_id=user_id,
                    to_hash=h(to.lower()),
                    template=template,
                    subject=subject,
                    delivered=delivered,
                    error=error,
                    created_at=now(),
                )
            )

    def emails_for(self, user_id: str) -> list[dict[str, Any]]:
        with self.tx() as c:
            rows = (
                c.execute(select(emails).where(emails.c.user_id == user_id).order_by(emails.c.id))
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]

    def clock_offset_weeks(self) -> int:
        with self.tx() as c:
            row = c.execute(select(clock.c.offset_weeks).where(clock.c.id == 1)).first()
            return int(row[0]) if row else 0

    def advance_clock(self, weeks: int) -> int:
        cur = self.clock_offset_weeks() + weeks
        with self.tx() as c:
            exists = c.execute(select(clock.c.id).where(clock.c.id == 1)).first()
            if exists:
                c.execute(update(clock).where(clock.c.id == 1).values(offset_weeks=cur))
            else:
                c.execute(insert(clock).values(id=1, offset_weeks=cur))
        return cur
