"""Email (SPEC §9): a provider-agnostic SMTP sender; Mailpit catches every email in the demo.

Emails never contain account numbers and never ask for approval of money; amounts appear only
if the owner turned them on. Every send is logged (recipient hashed) whether or not it delivered.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Literal

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.store import Store

log = logging.getLogger(__name__)
TEMPLATES = Path(__file__).parent / "templates"
Template = Literal["sign_in", "verify_email", "welcome", "checkin", "digest", "alert", "milestone"]

_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))

SUBJECTS: dict[str, dict[str, str]] = {
    "sign_in": {"en": "Your Waypoint sign-in link", "zh": "Waypoint 登录链接"},
    "verify_email": {"en": "Confirm your email for Waypoint reminders", "zh": "确认用于 Waypoint 提醒的邮箱"},
    "welcome": {"en": "Your goal is set", "zh": "你的目标已设定"},
    "checkin": {"en": "How did last month go?", "zh": "上个月情况怎么样？"},
    "digest": {"en": "Your plan this week", "zh": "本周计划进展"},
    "alert": {"en": "Your plan moved", "zh": "你的计划有变化"},
    "milestone": {"en": "A step is coming up", "zh": "下一个步骤快到了"},
}


def smtp_settings() -> tuple[str, int, str]:
    return (
        os.environ.get("WAYPOINT_SMTP_HOST", "127.0.0.1"),
        int(os.environ.get("WAYPOINT_SMTP_PORT", "1025")),
        os.environ.get("WAYPOINT_MAIL_FROM", "Waypoint <no-reply@waypoint.test>"),
    )


def render_email(template: Template, lang: str, ctx: dict[str, Any]) -> tuple[str, str, str]:
    subject = SUBJECTS[template]["zh" if lang == "zh" else "en"]
    base = {"lang": lang, "subject": subject, **ctx}
    html = _env.get_template(f"{template}.html").render(**base)
    text = _env.get_template(f"{template}.txt").render(**base)
    return subject, html, text


def send(
    store: Store, to: str, template: Template, lang: str, ctx: dict[str, Any], user_id: str | None = None
) -> bool:
    subject, html, text = render_email(template, lang, ctx)
    host, port, sender = smtp_settings()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    error: str | None = None
    try:
        with smtplib.SMTP(host, port, timeout=5) as s:
            s.send_message(msg)
    except OSError as exc:
        error = type(exc).__name__
        log.warning("email not delivered (%s): template=%s", error, template)
    store.log_email(user_id, to, template, subject, delivered=error is None, error=error)
    return error is None
