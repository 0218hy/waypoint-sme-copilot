"""Waypoint web server: AG-UI chat endpoint, REST API, static web app (SPEC §2, docs/INTERFACES.md)."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import secrets
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from ag_ui.core import (
    AssistantMessage,
    CustomEvent,
    EventType,
    FunctionCall,
    MessagesSnapshotEvent,
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCall,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    UserMessage,
)
from ag_ui.encoder import EventEncoder
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from agent import llm
from agent import toolkit as tk
from agent.reader import MAX_BYTES, UploadError
from agent.turn import Out
from agent.widgets import WidgetEvent
from app import auth, security
from app import scheduler as weekly
from app.email import sender
from app.services import AppServices
from app.store import Store

log = logging.getLogger("waypoint")
ROOT = Path(__file__).resolve().parents[1]
WEB_DIST = ROOT / "web" / "dist"
GEO = ROOT / "data" / "public" / "planning_areas.geojson"
DEMO = os.environ.get("WAYPOINT_DEMO", "1") == "1"
BASE_URL = os.environ.get("WAYPOINT_BASE_URL", "http://127.0.0.1:8000")
MAILPIT_URL = os.environ.get("WAYPOINT_MAILPIT_URL", "http://127.0.0.1:8025")



@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Check the model answers (auth, CLI, network) so the UI can say if the AI is offline.
    ok, why = await llm.preflight("voice")
    log.info("model preflight: %s (%s)", "ok" if ok else "failed", why)
    if weekly.enabled(DEMO):
        scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(
    title="Waypoint", version="2.0.0", docs_url="/api/docs" if DEMO else None, redoc_url=None, lifespan=lifespan  # noqa: E501
)
store = Store()
services = AppServices(store, base_url=BASE_URL, demo=DEMO)
scheduler = weekly.WeeklyScheduler(services)
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
app.add_middleware(
    security.Hardening,
    origins=security.allowed_origins(BASE_URL),
    body_limits={"/api/upload": MAX_BYTES + security.MULTIPART_SLACK},
    hsts=BASE_URL.startswith("https://"),
)
# A person chatting sends a few runs a minute (each widget tap is one); these stop a script, not a person.
chat_rate = security.UserRateLimit(
    "Too many messages in a short time. Wait a minute, then try again.", (20, 60), (300, 3600)
)
upload_rate = security.UserRateLimit(
    "Too many uploads in a short time. Wait a few minutes, then try again.", (10, 600), (40, 86400)
)


# ------------------------------------------------------------------ session helpers


def current_user(request: Request) -> dict[str, Any] | None:
    return store.session_user(request.cookies.get(auth.SESSION_COOKIE))


def require_user(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="sign_in_required")
    return user


def _set_session(resp: Response, user_id: str) -> None:
    sid = store.new_session(user_id)
    resp.set_cookie(
        auth.SESSION_COOKIE,
        sid,
        httponly=True,
        samesite="lax",
        secure=auth.cookie_secure(),
        max_age=14 * 86400,
        path="/",
    )


# ------------------------------------------------------------------ auth


class EmailIn(BaseModel):
    email: str
    lang: str | None = None


@app.post("/api/auth/request-link", status_code=202)
def request_link(body: EmailIn, request: Request) -> dict[str, str]:
    email = body.email.strip().lower()
    ip = request.client.host if request.client else "?"
    if not auth.valid_email(email):
        raise HTTPException(status_code=422, detail="invalid_email")
    # Always 202 (no account enumeration); limits apply silently.
    if auth.per_email.allow(email) and auth.per_ip.allow(ip):
        token = store.new_magic_link(email, "sign_in", None)
        lang = _lang(body.lang)
        sender.send(  # the link carries the language picked on the sign-in page, for a new account
            store, email, "sign_in", lang,
            {"url": f"{BASE_URL}/api/auth/verify?token={token}&lang={lang}", "demo": DEMO},
        )
    return {"status": "sent"}


@app.get("/api/auth/verify")
def verify(token: str, lang: str | None = None) -> Response:
    link = store.consume_magic_link(token)
    if link is None:
        return RedirectResponse("/?auth=expired", status_code=303)
    if link["purpose"] == "verify_email" and link["user_id"]:
        store.update_user(link["user_id"], email=link["email"], email_verified=True)
        return RedirectResponse("/?email=verified", status_code=303)
    user = store.user_by_email(link["email"]) or store.create_user(
        "standalone", email=link["email"], verified=True, lang=_lang(lang)
    )
    resp = RedirectResponse("/", status_code=303)
    _set_session(resp, user["id"])
    services.audit.append("sign_in", user["id"], method="magic_link")
    return resp


class SsoIn(BaseModel):
    token: str
    lang: str | None = None


def _lang(v: str | None) -> str:
    return "zh" if (v or "").startswith("zh") else "en"


@app.post("/api/auth/webank-sso")
def webank_sso(body: SsoIn) -> Response:
    claims = auth.verify_sso(body.token)
    if claims is None:
        raise HTTPException(status_code=401, detail="invalid_sso_token")
    subject, email = claims["sub"], claims.get("email")
    user = store.user_by_webank(subject) or store.create_user(
        "embedded", webank_subject=subject, email=email, verified=email is not None, lang=_lang(body.lang)
    )
    if email and not user.get("email"):  # WeBank's verified contact email is where reminders go
        store.update_user(user["id"], email=email, email_verified=True)
    resp = JSONResponse({"ok": True})
    _set_session(resp, user["id"])
    services.audit.append("sign_in", user["id"], method="webank_sso_mock")
    return resp


@app.post("/api/auth/logout")
def logout(request: Request) -> Response:
    sid = request.cookies.get(auth.SESSION_COOKIE)
    if sid:
        store.end_session(sid)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.SESSION_COOKIE, path="/")
    return resp


@app.get("/api/session")
def session(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user is None:
        return {"user": None, "state": None}
    state = services.load_state(user)
    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "email_verified": user["email_verified"],
            "host_mode": user["host_mode"],
            "lang": state.lang,
        },
        "state": state.snapshot(services.llm_label(), DEMO),
    }


# ------------------------------------------------------------------ AG-UI chat


def _transcript_messages(user_id: str) -> list[Any]:
    msgs: list[Any] = []
    for row in store.transcript(user_id):
        c = row["content"]
        if row["role"] == "user":
            msgs.append(UserMessage(id=row["msg_id"], role="user", content=c.get("text", "")))
        elif row["kind"] == "text":
            msgs.append(AssistantMessage(id=row["msg_id"], role="assistant", content=c["text"]))
        else:
            w = c["widget"]
            msgs.append(
                AssistantMessage(
                    id=row["msg_id"],
                    role="assistant",
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id=w["id"],
                            type="function",
                            function=FunctionCall(
                                name=w["payload"]["type"], arguments=json.dumps(w, ensure_ascii=False)
                            ),
                        )
                    ],
                )
            )
    return msgs


def _widget_events(w: Any) -> list[Any]:
    wjson = w.model_dump(mode="json")
    return [
        ToolCallStartEvent(type=EventType.TOOL_CALL_START, tool_call_id=w.id, tool_call_name=w.payload.type),
        ToolCallArgsEvent(type=EventType.TOOL_CALL_ARGS, tool_call_id=w.id, delta=json.dumps(wjson, ensure_ascii=False)),  # noqa: E501
        ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id=w.id),
    ]


def _parse_input(body: RunAgentInput) -> tuple[str | None, WidgetEvent | None, str | None]:
    fp = body.forwarded_props or {}
    event = (
        WidgetEvent.model_validate(fp["widget_event"])
        if isinstance(fp, dict) and fp.get("widget_event")
        else None
    )
    text = None
    label = None
    for m in reversed(body.messages or []):
        if getattr(m, "role", None) == "user":
            content = m.content if isinstance(m.content, str) else ""
            label = content
            text = content if event is None else None
            break
    return text, event, label


def _email_link(v: Any) -> tuple[str, str] | None:
    """An email link the web app read from its address (`?checkin=` or `?alert=`), checked by the Skill."""
    if not isinstance(v, dict) or v.get("kind") not in ("checkin", "alert"):
        return None
    value = v.get("value")
    if not isinstance(value, str) or not 0 < len(value) <= 512:
        return None
    return str(v["kind"]), value


@app.post("/api/agui")
async def agui(
    body: RunAgentInput, request: Request, user: dict[str, Any] = Depends(require_user)
) -> Response:
    chat_rate.check(user["id"])
    encoder = EventEncoder(accept=request.headers.get("accept") or "text/event-stream")
    try:
        text, event, label = _parse_input(body)
    except ValidationError:
        # a malformed card answer is the client's error, not the server's
        return JSONResponse(
            {
                "detail": "invalid_widget_event",
                "notice": "That answer couldn't be read. Please tap the card again.",
            },
            status_code=422,
        )
    fp = body.forwarded_props if isinstance(body.forwarded_props, dict) else {}
    retry = bool(fp.get("retry_compose"))
    init = not retry and (bool(fp.get("init")) or (text is None and event is None))
    link = _email_link(fp.get("email_link")) if init else None

    async def stream() -> AsyncIterator[str]:
        run_id = body.run_id or uuid.uuid4().hex
        yield encoder.encode(
            RunStartedEvent(type=EventType.RUN_STARTED, thread_id=body.thread_id, run_id=run_id)
        )
        async with _locks[user["id"]]:
            try:
                state = services.load_state(user)
                if init:
                    yield encoder.encode(
                        MessagesSnapshotEvent(
                            type=EventType.MESSAGES_SNAPSHOT, messages=_transcript_messages(user["id"])
                        )
                    )
                elif label and not retry:
                    store.add_message(
                        user["id"], "m_" + secrets.token_hex(6), "user", "text", {"text": label}
                    )
                if retry:
                    outs: list[Out] = await services.orchestrator.run(state, text=None, event=None, init=False, retry=True)  # noqa: E501
                    turn = None
                else:
                    turn = await services.orchestrator.run_turn(state, text=text, event=event, init=init, link=link)  # noqa: E501
                    outs = list(turn.outputs)
                # saved before the UI hears of it: a new goal_id makes the Goal tab fetch /api/goal at once
                services.save_state(state)
                yield encoder.encode(
                    StateSnapshotEvent(
                        type=EventType.STATE_SNAPSHOT, snapshot=state.snapshot(services.llm_label(), DEMO)
                    )
                )
                # Phase 1: cards at once, with a slot where each model-written message will go.
                slot_ids: dict[str, str] = {}
                # a widget whose body the model writes (a draft) is sent after the words, with its body filled
                deferred = {o.beat.into for o in outs if o.kind == "beat" and o.beat is not None and o.beat.into}  # noqa: E501
                for out in outs:
                    if out.kind == "beat" and out.beat is not None and out.beat.into:
                        continue
                    if out.kind == "widget" and out.widget is not None and out.widget.id in deferred:
                        continue
                    if out.kind == "beat" and out.beat is not None:
                        mid = "m_" + secrets.token_hex(6)
                        slot_ids[out.beat.id] = mid
                        yield encoder.encode(CustomEvent(type=EventType.CUSTOM, name="waypoint.text_slot", value={"id": mid}))  # noqa: E501
                    elif out.kind == "widget" and out.widget is not None:
                        for ev in _widget_events(out.widget):
                            yield encoder.encode(ev)
                # Phase 2: the model writes the messages; each fills its slot.
                if turn is not None and (slot_ids or deferred):
                    await services.orchestrator.compose(turn)
                    outs = list(turn.outputs)
                for out in outs:
                    if out.kind == "text" and out.text:
                        slot = slot_ids.get(out.beat.id) if out.beat is not None else None
                        mid = slot or "m_" + secrets.token_hex(6)
                        out.notice = {"message_id": mid}
                        yield encoder.encode(TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id=mid, role="assistant"))  # noqa: E501
                        yield encoder.encode(TextMessageContentEvent(type=EventType.TEXT_MESSAGE_CONTENT, message_id=mid, delta=out.text))  # noqa: E501
                        yield encoder.encode(TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=mid))  # noqa: E501
                    elif out.kind == "notice" and out.notice is not None:
                        yield encoder.encode(CustomEvent(type=EventType.CUSTOM, name="waypoint.notice", value=out.notice))  # noqa: E501
                    elif out.kind == "widget" and out.widget is not None and (turn is None or out.widget.id in deferred):  # noqa: E501
                        for ev in _widget_events(out.widget):
                            yield encoder.encode(ev)
                # The transcript is stored in the final order.
                for out in outs:
                    if out.kind == "text" and out.text:
                        store.add_message(user["id"], (out.notice or {}).get("message_id") or "m_" + secrets.token_hex(6),  # noqa: E501
                                          "assistant", "text", {"text": out.text})
                    elif out.kind == "widget" and out.widget is not None:
                        store.add_message(user["id"], "m_" + secrets.token_hex(6), "assistant", "widget",
                                          {"widget": out.widget.model_dump(mode="json")})
                services.save_state(state)
                yield encoder.encode(
                    StateSnapshotEvent(
                        type=EventType.STATE_SNAPSHOT, snapshot=state.snapshot(services.llm_label(), DEMO)
                    )
                )
                yield encoder.encode(
                    RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=body.thread_id, run_id=run_id)
                )
            except Exception as exc:
                log.exception("run failed")
                yield encoder.encode(
                    RunErrorEvent(type=EventType.RUN_ERROR, message=f"run_failed:{type(exc).__name__}")
                )

    return StreamingResponse(
        stream(), media_type=encoder.get_content_type(), headers={"Cache-Control": "no-store"}
    )


# ------------------------------------------------------------------ previews, uploads, goal, account


@app.get("/api/preview/setaside")
def preview_setaside(share: float, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if not 0.0 <= share <= 1.0:
        raise HTTPException(status_code=422, detail="share_out_of_range")
    state = services.load_state(user)
    if state.cost_card is None or state.funding is None:
        # the slider only exists once there is a cost card and a funding plan
        raise HTTPException(
            status_code=409,
            detail="no_plan_yet: the set-aside preview needs the cost and funding steps done first",
        )
    return services.orchestrator.preview_setaside(state, share)


@app.get("/api/preview/compare")
def preview_compare(savings: str, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    """Compare funding plans with the savings column at another amount (the owner typing it)."""
    state = services.load_state(user)
    if state.cost_card is None or state.funding is None:
        raise HTTPException(
            status_code=409,
            detail="no_plan_yet: the funding comparison needs the cost and funding steps done first",
        )
    amount = tk.savings_in_range(state, savings)
    if amount is None:
        raise HTTPException(status_code=422, detail="savings_out_of_range")
    return services.orchestrator.preview_compare(state, amount)


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...), user: dict[str, Any] = Depends(require_user)
) -> dict[str, str]:
    upload_rate.check(user["id"])
    # Read in chunks and stop past the limit (the middleware has already capped the whole body).
    buf = bytearray()
    while chunk := await file.read(256 * 1024):
        buf += chunk
        if len(buf) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="too_large")
    data = bytes(buf)
    try:
        doc_id = await services.ingest_document(
            user["id"], file.filename or "upload", file.content_type or "", data
        )
    except UploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"doc_id": doc_id}


@app.get("/api/docs/{doc_id}/image")
def doc_image(doc_id: str, user: dict[str, Any] = Depends(require_user)) -> FileResponse:
    doc = store.document(doc_id)
    if doc is None or doc["user_id"] != user["id"] or not doc["redacted_path"]:
        raise HTTPException(status_code=404)
    return FileResponse(doc["redacted_path"], media_type="image/png")


@app.get("/api/goal")
def goal(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    state = services.load_state(user)
    return services.orchestrator.goal_dashboard(state)


@app.get("/api/documents")
def documents(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return services.documents_view(user["id"])


class AccountPatch(BaseModel):
    lang: str | None = None
    checkin_frequency: str | None = None
    email_amounts: bool | None = None
    email: str | None = None


@app.get("/api/account")
def account(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return services.account_view(user)


@app.patch("/api/account")
def account_patch(body: AccountPatch, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return services.account_update(user, body.model_dump(exclude_none=True))


@app.get("/api/account/export")
def account_export(user: dict[str, Any] = Depends(require_user)) -> JSONResponse:
    """Everything Waypoint holds about the owner (PIPL access right)."""
    data = services.export_user(user)
    return JSONResponse(data, headers={"Content-Disposition": "attachment; filename=waypoint-export.json"})


@app.get("/api/audit/proof")
def audit_proof(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    """The owner's tamper-evidence proof: chain status, chain head, and his own hash-chained records."""
    from agent import audit as A

    return A.proof(services.audit.path, user["id"])


@app.delete("/api/account")
def account_delete(request: Request, user: dict[str, Any] = Depends(require_user)) -> Response:
    """Delete the owner's data (PIPL deletion right). The audit log keeps redacted entries and the deletion."""  # noqa: E501
    services.delete_user(user)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.SESSION_COOKIE, path="/")
    return resp


_QUICK_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Waypoint check-in</title></head>
<body style="font-family:system-ui,sans-serif;max-width:28rem;margin:3rem auto;padding:0 16px;color:#1b2b26">
<h1 style="font-size:1.25rem">Waypoint</h1>
<p>Did last month go to plan? Tap the button to record "on plan as usual".</p>
<p>上个月一切按计划进行吗？点按钮记录“一切按计划”。</p>
<form method="post" action="/api/checkin/quick">
<input type="hidden" name="token" value="{token}">
<button type="submit"
 style="background:#1f6f5c;color:#fff;border:0;padding:12px 18px;border-radius:8px;font-size:1rem">
On plan as usual · 一切按计划</button>
</form>
<p style="color:#5b6b66;font-size:.9rem">If something changed, open Waypoint instead.
有变化的话，请打开 Waypoint。</p>
</body></html>
"""


@app.get("/api/checkin/quick")
def checkin_quick(token: str) -> Response:
    """The check-in email's "on plan as usual" link. Opening it changes nothing (mail scanners and link
    previews fetch links): it shows a page whose button POSTs the token from the same origin."""
    if auth.verify_checkin(token) is None:
        return RedirectResponse("/?checkin=expired", status_code=303)
    return HTMLResponse(
        _QUICK_PAGE.format(token=html.escape(token, quote=True)), headers={"Cache-Control": "no-store"}
    )


@app.post("/api/checkin/quick")
def checkin_quick_confirm(token: str = Form(...)) -> Response:
    """Records "on plan as usual". Signed, single-use per period; no sign-in needed, and it records
    nothing but that the month went as planned. The same-origin check covers this POST."""
    got = auth.verify_checkin(token)
    if got is None:
        return RedirectResponse("/?checkin=expired", status_code=303)
    goal_id, period = got
    try:
        ok = services.gk.quick_checkin(goal_id, period)
    except KeyError:  # the goal is gone
        return RedirectResponse("/?checkin=expired", status_code=303)
    return RedirectResponse("/?checkin=" + ("recorded" if ok else "already"), status_code=303)


@app.post("/api/consent/withdraw")
def consent_withdraw(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return services.withdraw_consent(user)


# ------------------------------------------------------------------ demo


@app.get("/api/demo/info")
def demo_info() -> dict[str, Any]:
    if not DEMO:
        raise HTTPException(status_code=404)
    return {
        "demo": True,
        "mailpit_url": MAILPIT_URL,
        "seed": services.seed,
        "simulated": True,
        "llm": services.llm_label(),
        "llm_status": llm.status("voice"),
    }


@app.get("/api/demo/sso-token")
def demo_sso_token() -> dict[str, str]:
    if not DEMO:
        raise HTTPException(status_code=404)
    return {"token": auth.sso_token("webank:demo-chen", email="joonrui@tulbrew.example")}  # fictional


class AdvanceIn(BaseModel):
    weeks: int
    scenario: str = "none"


@app.post("/api/demo/advance")
def demo_advance(body: AdvanceIn, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if not DEMO or not 1 <= body.weeks <= 52:
        raise HTTPException(status_code=404 if not DEMO else 422)
    if body.scenario not in ("none", "sales_dip", "channel_shift", "above_normal_draw"):
        raise HTTPException(status_code=422, detail="unknown_scenario")
    return services.advance(user, body.weeks, body.scenario)


@app.post("/api/demo/run-checks")
def demo_run_checks(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    """Demo only: run the scheduled weekly job now, without moving the clock. Idempotent: a second run
    in the same week checks nothing and sends nothing."""
    if not DEMO:
        raise HTTPException(status_code=404)
    return {"today": services.today().isoformat(), **scheduler.job()}


@app.get("/api/demo/webank")
def demo_webank(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    """Demo only: the mock WeBank's view of instructions Waypoint prepared for the owner to sign."""
    if not DEMO:
        raise HTTPException(status_code=404)
    return services.gk.webank_view(user)


class SignIn(BaseModel):
    instruction_id: str


@app.post("/api/demo/webank/sign")
def demo_webank_sign(body: SignIn, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    """Demo only: the owner signs a prepared instruction in WeBank's own flow (simulated). Waypoint never
    signs or moves money; in production this happens inside WeBank."""
    if not DEMO:
        raise HTTPException(status_code=404)
    if services.gk.sign_setaside(user["id"], body.instruction_id) is None:
        raise HTTPException(status_code=409, detail="not_pending")
    return services.gk.webank_view(user)


@app.get("/api/demo/sample-quote")
def demo_sample_quote() -> FileResponse:
    """A fictional contractor quote photo for trying the upload (read by the model like any upload)."""
    if not DEMO:
        raise HTTPException(status_code=404)
    from app.services import DEMO_QUOTE

    return FileResponse(DEMO_QUOTE, media_type="image/png", filename="sample-quote.png")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "llm": llm.status("voice"),
        "skills": services.orchestrator.skills.versions(),
        "scheduler": scheduler.running,
    }


# ------------------------------------------------------------------ static


@app.get("/geo/planning_areas.geojson")
def geo() -> FileResponse:
    if not GEO.exists():
        raise HTTPException(status_code=404)
    return FileResponse(GEO, media_type="application/geo+json")


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        target = (WEB_DIST / path).resolve()
        if path and target.is_file() and WEB_DIST in target.parents:
            return FileResponse(target)
        # index.html must never be cached: it names the hashed asset files of the current build
        return FileResponse(WEB_DIST / "index.html", headers={"Cache-Control": "no-cache"})
