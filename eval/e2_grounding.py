# ruff: noqa: E501
"""E2: every delivered quantity is grounded (results/prereg.md, SPEC §0.3, §8.4).

Method (pre-registered): every bot text in the E1a transcripts is checked: no bare digits or number
words outside Figure placeholders before rendering; every rendered figure resolves to a Figure with a
source. Pass mark: 0 ungrounded quantities.

How it is measured (at the compose boundary): in this build the voice writes every message. Step
handlers emit beats; `agent.voice.compose` returns one pre-render template per beat; the orchestrator then
renders each template through `Turn.text`. With no model configured, E1a ran with the product's
deterministic test composer (`agent.voice.echo_composer`: each beat's key plus its required placeholders),
so this measures the grounding machinery, not a model's writing ("E2 with a model" is reported as not
run). During E1a both `agent.voice.compose` and `Turn.text` are wrapped. For each composed template we
record the beat, the figures the turn offered and the template; for each render, the text variables
substituted into it, every `{{fig:...}}` placeholder with the Figure it resolved to, and the rendered
string. Then:

1. every composed (pre-render) template, with its text-variable slots (`{{unit}}`, `{{area}}`) blanked,
   must pass `render.check_text`, and `agent.voice.validate` must accept it (only offered placeholders,
   every required placeholder present);
2. a text-variable value that contains digits or number words must be a verbatim name from a data record
   (a simulated unit's "mall + unit number", a planning-area name, a step label). Any other is counted
   as ungrounded. Names that carry digits (e.g. "#B1-S03") are counted and reported separately;
3. every figure placeholder must resolve to a Figure whose source has a kind and a ref;
4. no rendered text may still contain "{{";
5. every text actually delivered to the owner must be one of the recorded renders of a composed template
   (nothing reaches the owner without passing the compose boundary and the renderer).
Beats the composer failed (the owner gets a retry notice instead of text) deliver nothing and are
reported separately.
"""

from __future__ import annotations

import re
import time
from contextlib import contextmanager
from typing import Any

from eval import common as C

_TEXT_VAR = re.compile(r"\{\{(?!fig:|rule:|topic:)[a-z_]+\}\}")


class Recorder:
    """Wraps agent.voice.compose and agent.turn.Turn.text; records every template and render per persona."""

    def __init__(self) -> None:
        self.records: dict[str, list[dict[str, Any]]] = {}
        self.composed: dict[str, list[dict[str, Any]]] = {}
        self.current: str | None = None
        self._orig: tuple[Any, Any] | None = None

    def install(self) -> None:
        from agent import render, voice
        from agent.turn import Turn

        if self._orig is not None:
            return
        orig_text, orig_compose = Turn.text, voice.compose
        self._orig = (orig_text, orig_compose)
        rec = self

        def text(self_t: Any, template: str, vars: dict[str, str] | None = None) -> str:  # noqa: A002
            entry: dict[str, Any] = {"template": template, "vars": dict(vars or {}), "figs": []}
            substituted = template
            for k, v in (vars or {}).items():
                substituted = substituted.replace("{{" + k + "}}", v)
            try:
                out = orig_text(self_t, template, vars)
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
                rec.records.setdefault(rec.current or "?", []).append(entry)
                raise
            for m in render.PLACEHOLDER.finditer(substituted):
                if m.group(1) != "fig":
                    continue
                f = self_t.figs.get(m.group(2))
                src = getattr(f, "source", None) if f is not None else None
                entry["figs"].append(
                    {
                        "id": m.group(2),
                        "resolved": f is not None,
                        "source_kind": str(src.kind) if src is not None else None,
                        "source_ref": src.ref if src is not None else None,
                    }
                )
            entry["rendered"] = out
            rec.records.setdefault(rec.current or "?", []).append(entry)
            return out

        async def compose(beats: list[Any], **kw: Any) -> Any:
            texts, report = await orig_compose(beats, **kw)
            figs = set(kw.get("figures") or {})
            for b, tpl in zip(beats, texts, strict=True):
                rec.composed.setdefault(rec.current or "?", []).append(
                    {
                        "beat": b.id,
                        "key": b.key,
                        "must": list(b.must),
                        "vars": dict(b.vars),
                        "allowed_figs": sorted(figs),
                        "template": tpl,
                    }
                )
            return texts, report

        Turn.text = text  # type: ignore[method-assign]
        voice.compose = compose  # type: ignore[assignment]

    def uninstall(self) -> None:
        from agent import voice
        from agent.turn import Turn

        if self._orig is not None:
            Turn.text, voice.compose = self._orig  # type: ignore[method-assign,assignment]
            self._orig = None

    @contextmanager
    def persona(self, pid: str) -> Any:
        prev = self.current
        self.current = pid
        try:
            yield self
        finally:
            self.current = prev


def known_identifiers() -> set[str]:
    """Names copied verbatim from data records: unit names, planning-area names, step labels."""
    from agent import toolkit as tk
    from agent.state import STEP_LABELS
    from tools import data as D

    ids: set[str] = set()
    for u in D.load_units():
        ids.add(f"{u.mall} {u.unit_no}")
    ids.update(tk.area_names().values())
    for labels in STEP_LABELS.values():
        ids.update(labels.values())
    return ids


def audit(recorder: Recorder, delivered: dict[str, list[str]]) -> dict[str, Any]:
    """Check every composed template, every render and every delivered text."""
    from agent.render import check_text
    from agent.voice import validate

    idents = known_identifiers()
    n_templates = n_failed_beats = n_renders = n_delivered = n_figs = 0
    template_fail: list[dict[str, Any]] = []
    validate_fail: list[dict[str, Any]] = []
    var_ungrounded: list[dict[str, Any]] = []
    var_identifier: dict[str, int] = {}
    fig_fail: list[dict[str, Any]] = []
    braces_left: list[str] = []
    untraceable: list[str] = []
    render_errors: list[str] = []
    for pid, comps in recorder.composed.items():
        for c in comps:
            if c["template"] is None:
                n_failed_beats += 1
                continue
            n_templates += 1
            res = check_text(_TEXT_VAR.sub(" ", c["template"]))
            if not res.ok:
                template_fail.append(
                    {
                        "persona": pid,
                        "beat": c["key"],
                        "template": c["template"][:160],
                        "hits": list(res.hits),
                    }
                )
            errs = validate(c["template"], set(c["allowed_figs"]), set(c["vars"]), c["must"])
            if errs:
                validate_fail.append({"persona": pid, "beat": c["key"], "errors": errs})
    for pid, recs in recorder.records.items():
        templates = {c["template"] for c in recorder.composed.get(pid, []) if c["template"] is not None}
        composed_renders = set()
        for r in recs:
            n_renders += 1
            if "error" in r:
                render_errors.append(f"{pid}: {r['error']}")
                continue
            if r["template"] in templates:
                composed_renders.add(r["rendered"])
            for k, v in r["vars"].items():
                if f"{{{{{k}}}}}" not in r["template"]:
                    continue  # offered but not used
                vres = check_text(str(v))
                if vres.ok:
                    continue
                if str(v) in idents:
                    var_identifier[k] = var_identifier.get(k, 0) + 1
                else:
                    var_ungrounded.append(
                        {"persona": pid, "var": k, "value": str(v)[:80], "hits": list(vres.hits)}
                    )
            for f in r["figs"]:
                n_figs += 1
                if not (f["resolved"] and f["source_kind"] and f["source_ref"]):
                    fig_fail.append({"persona": pid, **f})
            if "{{" in (r.get("rendered") or ""):
                braces_left.append(f"{pid}: {r['rendered'][:120]}")
        for t in delivered.get(pid, []):
            n_delivered += 1
            if "{{" in t:
                braces_left.append(f"{pid} (delivered): {t[:120]}")
            if t not in composed_renders:
                untraceable.append(f"{pid}: {t[:120]}")
    ungrounded = (
        len(template_fail)
        + len(validate_fail)
        + len(var_ungrounded)
        + len(fig_fail)
        + len(braces_left)
        + len(untraceable)
        + len(render_errors)
    )
    return {
        "composed_templates": n_templates,
        "renders": n_renders,
        "delivered_texts": n_delivered,
        "figure_placeholders": n_figs,
        "ungrounded_total": ungrounded,
        "template_check_failures": len(template_fail),
        "voice_validate_failures": len(validate_fail),
        "text_var_ungrounded": len(var_ungrounded),
        "text_var_identifiers_with_digits": var_identifier,
        "figures_unresolved_or_sourceless": len(fig_fail),
        "placeholders_left_unrendered": len(braces_left),
        "delivered_not_from_compose_and_renderer": len(untraceable),
        "render_errors": len(render_errors),
        "beats_failed_compose_retry_notice": n_failed_beats,
        "examples": {
            "template_fail": template_fail[:5],
            "validate_fail": validate_fail[:5],
            "var_ungrounded": var_ungrounded[:5],
            "fig_fail": fig_fail[:5],
            "braces_left": braces_left[:5],
            "untraceable": untraceable[:5],
            "render_errors": render_errors[:5],
        },
    }


def evaluate(e1a_payload: dict[str, Any] | None) -> dict[str, Any]:
    t0 = time.time()
    if not e1a_payload or e1a_payload.get("recorder") is None:
        return C.entry(
            "not_run",
            title="Every delivered quantity is grounded",
            reason="E1a transcripts were not available in this run.",
        )
    rec: Recorder = e1a_payload["recorder"]
    a = audit(rec, e1a_payload["delivered"])
    ok = a["ungrounded_total"] == 0
    notes = [
        f"Audited {a['composed_templates']} composed templates, {a['renders']} renders and "
        f"{a['delivered_texts']} delivered bot texts from all {e1a_payload['n']} E1a transcripts; "
        f"{a['figure_placeholders']} figure placeholders were filled. Voice: {e1a_payload.get('voice')} — "
        + (
            "every delivered message was written by the model and checked here."
            if "model writes" in str(e1a_payload.get("voice"))
            else "this checks the grounding machinery end to end, not a model's writing (see E2-model)."
        ),
        f"Template check failures: {a['template_check_failures']}; voice.validate failures: "
        f"{a['voice_validate_failures']}; text variables carrying an ungrounded quantity: {a['text_var_ungrounded']}; "
        f"unresolved or sourceless figures: {a['figures_unresolved_or_sourceless']}; placeholders left unrendered: "
        f"{a['placeholders_left_unrendered']}; delivered texts not traceable to a composed template: "
        f"{a['delivered_not_from_compose_and_renderer']}; render errors: {a['render_errors']}.",
        f"Beats the composer failed (owner shown a retry notice, no text delivered): "
        f"{a['beats_failed_compose_retry_notice']}.",
        "Text variables that contain digits but are verbatim names from data records (simulated unit "
        f"numbers such as '#B1-S03', area names) are not quantities and are not counted: "
        f"{a['text_var_identifiers_with_digits'] or 'none'}.",
        "Scope: bot text only (as pre-registered). Widget payloads (cards, chips, approval lines) are "
        "filled from Figures by code but are not part of this check.",
    ]
    if not ok:
        notes.append(f"Examples of failures: {a['examples']}")
    return C.entry(
        "run",
        n=a["delivered_texts"],
        title="Every delivered quantity is grounded",
        metrics=a,
        pass_marks={
            "ungrounded quantities in delivered bot text": C.mark("0", a["ungrounded_total"], ok),
        },
        seed=C.SEED,
        notes=notes,
        runtime_s=time.time() - t0,
    )
