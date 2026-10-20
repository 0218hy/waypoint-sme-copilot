# Interfaces between the web app and the backend

This is the build contract for SPEC §2 (AG-UI), §5 (widgets) and §7.3 (Goal tab). The payload schemas are generated from `agent/widgets.py` into `web/src/contracts/*.schema.json` (`make contracts`). Never hand-edit the schemas.

## 1. Chat: AG-UI over SSE

`POST /api/agui` takes an AG-UI `RunAgentInput` and returns `text/event-stream`. The session cookie identifies the owner. `threadId` is the owner's journey id.

**The client sends one of two things:**
- **Free text:** the last `user` message in `messages`.
- **A widget event:** in `forwardedProps.widget_event`, a `WidgetEvent` (`{widget_id, event, value, data}`). The client also appends a short, human-readable `user` message for the transcript (e.g. "Tampines", "Use this cost"). **The server acts only on `widget_event`, never on that text.**

**Links from emails:** the check-in email's "Something changed" links to `/?checkin=<signed token>` and the alert email to `/?alert=<id>`; the one-tap check-in lands on `/?checkin=recorded|already|expired`. The web app (`web/src/lib/emailLink.ts`) reads the parameter once at start-up, removes it from the address bar (opening the chat tab), keeps it through sign-in (in this browser, 30 minutes), and sends it once with the opening run as `forwardedProps.email_link: {kind: "checkin" | "alert", value}`. The server decides what it opens (SPEC §7.4): a valid check-in token opens `checkin_form` for that goal and period; a valid alert id opens `alert_card` and `repair_options`; anything else is a plain `waypoint.notice`.

**The server streams these events, in order:**

| Event | Meaning |
|---|---|
| `RUN_STARTED` | The run has begun |
| `STATE_SNAPSHOT` | The journey state (below), at the start of every run and whenever it changes |
| `CUSTOM` `waypoint.text_slot` `{id}` | Where a model-written message will go (sent at once, in order with the widgets) |
| `TEXT_MESSAGE_START` / `TEXT_MESSAGE_CONTENT` / `TEXT_MESSAGE_END` | Bot text, already rendered (figures filled, localised). Its `messageId` equals a slot id: fill that slot in place. Sent after every widget of the run |
| `TOOL_CALL_START` (`toolCallName` = the widget `type`, `toolCallId` = `widget.id`), then `TOOL_CALL_ARGS` (`delta` = JSON of the `Widget`), then `TOOL_CALL_END` | One widget. The web app renders it with the renderer registered for that `toolCallName`. These are display-only: **the client never returns a tool result** |
| `CUSTOM` `waypoint.notice` `{code: "compose_failed" \| "model_unavailable", retry: true}` | A message couldn't be written; the UI shows a notice with Retry, which sends `forwardedProps.retry_compose: true` |
| `CUSTOM` `waypoint.notice` `{code: "link_invalid" \| "checkin_recorded" \| "checkin_already", retry: false}` | A plain notice about an email link: expired, tampered or not this owner's (`link_invalid`), or where the one-tap check-in landed. Nothing to retry |
| `RUN_FINISHED` or `RUN_ERROR` | The run has ended |

`MESSAGES_SNAPSHOT` is sent on the first run of a page load, so a returning owner sees the transcript, including widget tool calls.

**Journey state (`STATE_SNAPSHOT.snapshot`):**
```json
{
  "lang": "en" | "zh",
  "host_mode": "embedded" | "standalone",
  "step": "welcome" | "profile" | "site" | "cost" | "funding" | "goal_plan" | "goal_keeper",
  "steps": [{"id": "profile", "label": "Your business", "status": "done" | "current" | "todo" | "stale"}],
  "goal_id": null | "g_…",
  "llm": "model id" | "off",
  "demo": true,
  "busy_widget": null | "w_…"
}
```

**Drafts (`draft_card`):** a widget whose body the model writes (the consent request's prose) has no text slot; it is sent after the words, with `payload.body` filled. If the prose couldn't be written, the card still comes with its facts and `body` empty, and a `waypoint.notice` offers Retry. The web app offers Copy and Download (plain text, `payload.filename`); the server never sends a draft.

**Milestone timelines:** `milestone_timeline.step` is `goal_keeper` for the active goal's own timeline, which stays tappable in the Goal Keeper. A chat timeline item with `can_mark_done` shows "Mark as done" (it sends `mark_milestone_done {value: id}`); the server checks the step and its order again, and asks the owner to confirm a money step (`money_step`) with quick replies before recording it.

**Superseded widgets:** when a later widget replaces an earlier one (e.g. a new `unit_compare`), the server sends the new widget with a new id. The UI (`web/src/chat/transcript.ts`) shows an interactive widget disabled when:
- a newer widget of the same type exists;
- the step has moved on (a widget's step is fixed per type in `web/src/widgets/types.ts`; a `confirm_card` carries its own `step`);
- it is **answered once** (`quick_replies`, `confirm_card`, `consent_card`, `rule_card`, `approval_card`, `repair_options`, `alert_card`, `goal_summary`, `checkin_form`) and the owner has sent anything after it;
- it is a `profile_card` and the profile's summary `confirm_card` follows it (the card's own confirm gives way to the summary).

## 2. REST

**Errors common to every endpoint** (`app/security.py`, see [SECURITY.md](SECURITY.md)): a POST, PUT, PATCH or DELETE from another origin gets **403** `cross_origin_request`; an upload over 10 MB gets **413** before the rest is read; over a per-owner rate limit (`/api/agui`, `/api/upload`) gets **429** with `Retry-After` and a plain notice the chat shows. Every response carries the security headers.

| Method and path | Purpose |
|---|---|
| `GET /api/session` | `{user: {id, email, email_verified, host_mode, lang} \| null, state}` |
| `POST /api/auth/request-link` `{email, lang?}` | Sends a magic link (`sign_in` email, in `lang`; it goes to Mailpit in the demo). Always 202 for a valid address (422 for an invalid one); rate limits apply silently |
| `GET /api/auth/verify?token=&lang=` | A sign-in link: creates the account if new (in `lang`), sets the session cookie and redirects to `/` (`/?auth=expired` if used or expired). A `verify_email` link: marks the email verified and redirects to `/?email=verified` |
| `POST /api/auth/webank-sso` `{token, lang?}` | Mock WeBank SSO; a new account takes `lang` |
| `GET /api/demo/sso-token` | Demo only: `{token}`, a signed mock SSO token for the fictional company |
| `POST /api/auth/logout` | Clears the session |
| `GET /api/preview/setaside?share=0.45` | Slider preview (read-only, < 300 ms): `{share, chart, figures, display, wall}` |
| `GET /api/preview/compare?savings=300000` | "Compare funding plans" with the savings column at that amount (read-only; 0 to the likely total, else 422): `{columns, figures, display}` |
| `POST /api/upload` (multipart `file`) | `{doc_id}`; the client then sends widget event `upload` with `value = doc_id` |
| `GET /api/docs/{doc_id}/image` | The redacted image for `upload_prompt` highlights |
| `GET /api/goal` | Goal tab: `{goal: {..., next_step: {id, label, act_by_date, status, draft: "consent_request" \| "checklist" \| null} \| null} \| null, widgets: Widget[]}`. The widgets are read-only `status_card`, `plan_vs_actual`, `milestone_timeline` (done steps ticked), `plan_summary` ×3, plus alert history. The only events the Goal tab sends (into the chat) are `reopen_step`, `see_repairs` and `open_milestone` |
| `GET /api/documents` | `{uploads: [...], sources: [...]}` |
| `GET /api/checkin/quick?token=` | The check-in email's "on plan as usual" link. Changes nothing: a valid token gets a small confirm page (no script) whose button POSTs the token; a bad one redirects to `/?checkin=expired` |
| `POST /api/checkin/quick` (form: `token`) | Records "on plan as usual": signed, single use per period, same-origin check; redirects to `/?checkin=recorded\|already\|expired` |
| `GET /api/account` / `PATCH /api/account` | `{lang?, checkin_frequency?, email_amounts?, email?}`. A new `email` is not stored until verified: it sends a `verify_email` link |
| `POST /api/consent/withdraw` | Withdraws the feed consent |
| `POST /api/demo/advance` `{weeks, scenario}` | Demo only: optionally starts a simulated scenario today (`none`, `sales_dip`, `channel_shift`, `above_normal_draw`), moves the clock and runs the weekly Goal Keeper job. Returns `{offset_weeks, today, checks, emails, scenario}` |
| `POST /api/demo/run-checks` | Demo only: runs the scheduled weekly job now without moving the clock: `{today, checks, emails}`. Idempotent: a second run in the same week does nothing |
| `GET /api/demo/sample-quote` | Demo only: a fictional contractor quote photo, to upload through `/api/upload` like any file |
| `GET /api/demo/webank` | Demo only: the mock WeBank's view of the monthly transfer Waypoint prepared: `{instructions: [{id, status: "pending_signature" \| "signed", amount, into, start}], simulated: true}` (display text, in the owner's language) |
| `POST /api/demo/webank/sign` `{instruction_id}` | Demo only: "Sign in WeBank", the owner's signature in WeBank's own flow, simulated. Signs only a pending instruction (409 otherwise); audit `setaside_signed`. Waypoint itself never signs or moves money |
| `GET /api/account/export` / `DELETE /api/account` | The owner's data export, and deletion |
| `GET /api/audit/proof` | The owner's tamper-evidence proof: `{chain_intact, message, owner, head: {seq, hash}, pin: "<seq>:<hash>", records: [his audit records], chain: [{seq, prev, owner_tag, digest, hash}, … every link from genesis to the head], how_to_check}`; also in the export as `audit_proof`. `uv run python -m agent.audit check-proof <file> [--head <pin>]` re-derives every link offline, re-hashes his records against them, and fails if one of his links has no record; a lender keeps `pin`, and `uv run python -m agent.audit verify <log> --head <pin>` catches a log cut back below it |
| `GET /api/demo/info` | Demo only: `{demo, mailpit_url, seed, simulated: true, llm, llm_status}` |
| `GET /api/health` | `{ok, llm: {label, provider, ready, last_error}, skills, scheduler}`: the voice model's status (`ready` is false when none is configured, or for 60 s after a provider failure, e.g. a failed startup check), the loaded Skill versions, and whether the weekly scheduler is running |
| `GET /geo/planning_areas.geojson` | Planning-area boundaries (self-hosted) |

## 3. Figures and display text
- Widgets reference numbers by Figure id. `Widget.display[id]` is the formatted text in the session language (e.g. "S$336,400", "about month 12", "3.1%").
- The UI shows `display` text. "Where's this from?" shows `figures[id].source` (`kind`, `ref`, `as_of`, `note`, `url`), `assumptions` and `taint`.
- Chart series are plain numbers with a stated currency, computed by tools. The UI formats axis labels only.
