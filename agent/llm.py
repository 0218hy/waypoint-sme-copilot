"""Provider-agnostic model layer (SPEC §0.8, §2.1).

Providers, chosen per role in `config/models.yaml` (overridable by environment):
- `anthropic` / `openai`: through Pydantic AI, with an API key (or a gateway's auth token);
- `claude_code`: through the Claude Agent SDK, using the local Claude Code login (`claude /login`)
  or `CLAUDE_CODE_OAUTH_TOKEN`; run with no tools, no project settings and a temp working directory;
- `auto`: `claude_code` if the Claude Code CLI is installed, else `anthropic` if a key or token is set,
  else off.

Every call returns a validated pydantic model (structured output) or None on any failure, so the
caller can fall back or show a retry. Models never call tools; code does.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal, TypeVar

import yaml
from pydantic import BaseModel, Field, ValidationError
from pydantic_ai.models import Model

log = logging.getLogger(__name__)
CONFIG = Path(__file__).resolve().parents[1] / "config" / "models.yaml"
Role = Literal["turn", "voice", "intent", "reader", "judge"]
M = TypeVar("M", bound=BaseModel)


@dataclass(frozen=True)
class RoleConfig:
    role: str
    provider: str
    model: str | None
    base_url: str | None
    api_key: str | None
    auth_token: str | None
    cli_path: str | None
    timeout_s: float
    retries: int

    @property
    def enabled(self) -> bool:
        if self.provider == "claude_code":
            return bool(self.cli_path)
        return self.provider not in ("none", "") and bool(self.api_key or self.auth_token)

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model or 'default'}" if self.enabled else "off"


@cache
def _config() -> dict[str, Any]:
    return dict(yaml.safe_load(CONFIG.read_text(encoding="utf-8")))


def _cli_path(env: dict[str, str] | os._Environ[str]) -> str | None:
    p = env.get("WAYPOINT_CLAUDE_CLI") or shutil.which("claude")
    return p if p and Path(p).exists() else None


def role_config(role: Role) -> RoleConfig:
    cfg = _config()
    d = {**cfg["defaults"], **(cfg["roles"].get(role) or {})}
    env = os.environ
    up = role.upper()
    provider = env.get(f"WAYPOINT_LLM_{up}_PROVIDER") or env.get("WAYPOINT_LLM_PROVIDER") or d["provider"]
    creds_all = cfg["credentials"]
    if provider == "auto":
        a = creds_all["anthropic"]
        if _cli_path(env):
            provider = "claude_code"  # uses whatever Claude Code is signed in with (login, token or gateway)
        elif env.get(a["api_key_env"]) or env.get(a["auth_token_env"]):
            provider = "anthropic"
        else:
            provider = "none"
    creds = creds_all.get(provider, {})
    model = (
        env.get(f"WAYPOINT_LLM_{up}_MODEL")
        or env.get(d.get("model_env", ""), "")
        or d.get(f"model_{provider}")
    )
    return RoleConfig(
        role=role,
        provider=provider,
        model=model or None,
        base_url=env.get(f"WAYPOINT_LLM_{up}_BASE_URL") or env.get(creds.get("base_url_env", "")) or None,
        api_key=env.get(f"WAYPOINT_LLM_{up}_API_KEY") or env.get(creds.get("api_key_env", "")) or None,
        auth_token=env.get(creds.get("auth_token_env", "")) or None,
        cli_path=_cli_path(env) if provider == "claude_code" else None,
        timeout_s=float(d.get("timeout_s", 30)),
        retries=int(d.get("retries", 1)),
    )


def build_model(rc: RoleConfig) -> Model:
    if rc.provider == "anthropic":
        from anthropic import AsyncAnthropic
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        name = rc.model or "claude-sonnet-5-5"
        if rc.auth_token and not rc.api_key:
            client = AsyncAnthropic(auth_token=rc.auth_token, base_url=rc.base_url, timeout=rc.timeout_s)
            return AnthropicModel(name, provider=AnthropicProvider(anthropic_client=client))
        return AnthropicModel(name, provider=AnthropicProvider(api_key=rc.api_key, base_url=rc.base_url))
    if rc.provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            rc.model or "gpt-4o", provider=OpenAIProvider(base_url=rc.base_url, api_key=rc.api_key)
        )
    raise ValueError(f"unsupported provider {rc.provider!r}")


# ------------------------------------------------------------------ test hooks

_TEST_MODEL: Model | None = None
_TEST_DECIDER: Callable[..., TurnDecision | None] | None = None


def set_test_model(model: Model | None) -> None:
    """Tests may inject a Pydantic AI TestModel/FunctionModel for every role."""
    global _TEST_MODEL
    _TEST_MODEL = model


def set_test_decider(fn: Callable[..., TurnDecision | None] | None) -> None:
    """Tests and evals may inject a deterministic decider for free-text turns."""
    global _TEST_DECIDER
    _TEST_DECIDER = fn


def enabled(role: Role) -> bool:
    return _TEST_MODEL is not None or role_config(role).enabled


def model_label(role: Role = "voice") -> str:
    if _TEST_MODEL is not None:
        return "test-model"
    return role_config(role).label


# ------------------------------------------------------------------ one structured call


class ModelUnavailable(RuntimeError):
    pass


_CALLS: dict[str, int] = {"calls": 0, "failed": 0, "cooling_refusals": 0}


def call_stats() -> dict[str, int]:
    """Model calls made by this process, and how many failed (evals report it with every model arm)."""
    return dict(_CALLS)


_COOLDOWN_S = 60.0
_ONE_OFF = ("invalid_output", "error_max_turns", "no_result")
_last_failure: dict[str, tuple[float, str]] = {}


def _cooling(provider: str) -> str | None:
    import time

    hit = _last_failure.get(provider)
    if hit and time.monotonic() - hit[0] < _COOLDOWN_S:
        return hit[1]
    return None


def _failed(provider: str, why: str) -> None:
    import time

    _last_failure[provider] = (time.monotonic(), why)


class Ping(BaseModel):
    ok: bool


def status(role: Role = "voice") -> dict[str, Any]:
    """Configured provider, and whether it failed recently (for the UI and /api/health)."""
    rc = role_config(role)
    cooling = _cooling(rc.provider) if _TEST_MODEL is None else None
    return {
        "label": model_label(role),
        "provider": rc.provider,
        "ready": rc.enabled and not cooling,
        "last_error": cooling,
    }


async def preflight(role: Role = "voice") -> tuple[bool, str]:
    """One tiny call to check the provider really answers (auth, CLI, network)."""
    try:
        await structured(role, "Reply with ok=true.", "ping", Ping)
        return True, model_label(role)
    except ModelUnavailable as exc:
        return False, str(exc)


async def structured(
    role: Role, instructions: str, prompt: str, output: type[M], images: list[tuple[bytes, str]] | None = None
) -> M:
    """One call that must return `output`. Raises ModelUnavailable on any provider failure."""
    rc = role_config(role)
    if _TEST_MODEL is None and not rc.enabled:
        raise ModelUnavailable("no model configured")
    cooling = _cooling(rc.provider) if _TEST_MODEL is None else None
    if cooling:
        _CALLS["cooling_refusals"] += 1
        raise ModelUnavailable(f"recently failed: {cooling}")
    _CALLS["calls"] += 1
    try:
        if _TEST_MODEL is None and rc.provider == "claude_code":
            return await asyncio.wait_for(
                _claude_code(rc, instructions, prompt, output, images), timeout=rc.timeout_s * 3
            )
        from pydantic_ai import Agent, BinaryContent

        model = _TEST_MODEL or build_model(rc)
        agent: Agent[None, M] = Agent(
            model, output_type=output, instructions=instructions, retries=rc.retries
        )
        parts: list[Any] = [prompt, *[BinaryContent(data=b, media_type=mt) for b, mt in images or []]]
        res = await asyncio.wait_for(agent.run(parts if images else prompt), timeout=rc.timeout_s * 2)
        return res.output
    except ModelUnavailable as exc:
        _CALLS["failed"] += 1
        # one malformed or unfinished answer is not an outage: only cool down when the provider itself
        # failed (an error result, no answer at all), so the next owner message still reaches the model
        if not any(k in str(exc) for k in _ONE_OFF):
            _failed(rc.provider, str(exc))
        raise
    except Exception as exc:  # timeouts, rate limits, auth, unavailable model, malformed output
        _CALLS["failed"] += 1
        why = f"{type(exc).__name__}: {str(exc)[:160]}"
        log.warning("model call failed (%s, %s): %s", role, rc.provider, why)
        if "auth" in str(exc).lower() or "login" in str(exc).lower() or "ProcessError" in type(exc).__name__:
            _failed(rc.provider, why)
        raise ModelUnavailable(why) from exc


async def _claude_code(
    rc: RoleConfig, instructions: str, prompt: str, output: type[M], images: list[tuple[bytes, str]] | None
) -> M:
    """Claude Agent SDK: no tools, no settings, a temp cwd. One model turn asking for plain JSON, which
    code validates; if it doesn't validate, the same call again with the SDK's JSON-schema output (that
    costs a second model turn, so it is the fallback, not the default)."""
    try:
        return await _claude_code_once(rc, instructions, prompt, output, images, structured=False)
    except ModelUnavailable as exc:
        if not any(k in str(exc) for k in _ONE_OFF):
            raise
        return await _claude_code_once(rc, instructions, prompt, output, images, structured=True)


def _json_text(text: str) -> Any:
    import json

    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    start, end = t.find("{"), t.rfind("}")
    return json.loads(t[start : end + 1] if start >= 0 and end > start else t)


async def _claude_code_once(
    rc: RoleConfig,
    instructions: str,
    prompt: str,
    output: type[M],
    images: list[tuple[bytes, str]] | None,
    structured: bool,
) -> M:
    import json

    from claude_agent_sdk import ClaudeAgentOptions, query
    from claude_agent_sdk.types import ResultMessage

    schema = output.model_json_schema()
    system = instructions
    if not structured:
        system += (
            "\n\nReply with only one JSON object that matches this JSON Schema: no prose, no code fences.\n"
            + json.dumps(schema, ensure_ascii=False)
        )
    opts = ClaudeAgentOptions(
        system_prompt=system,
        tools=[],
        allowed_tools=[],
        max_turns=2,  # one is the norm; the second absorbs a rare extra turn instead of failing
        setting_sources=[],
        cwd=tempfile.mkdtemp(prefix="waypoint-llm-"),
        cli_path=rc.cli_path,
        model=rc.model,
        output_format={"type": "json_schema", "schema": schema} if structured else None,
    )

    async def stream() -> AsyncIterator[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for data, mt in images or []:
            content.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": mt, "data": base64.b64encode(data).decode()},
                }
            )
        yield {
            "type": "user",
            "message": {"role": "user", "content": content},
            "parent_tool_use_id": None,
            "session_id": "waypoint",
        }

    result: Any = None
    async for msg in query(prompt=stream() if images else prompt, options=opts):
        if isinstance(msg, ResultMessage):
            if msg.is_error:
                raise ModelUnavailable(f"claude_code: {(msg.result or msg.subtype or 'error')[:160]}")
            result = getattr(msg, "structured_output", None)
            if result is None and msg.result:
                try:
                    result = _json_text(msg.result)
                except ValueError as exc:
                    raise ModelUnavailable("claude_code:invalid_output") from exc
    if result is None:
        raise ModelUnavailable("claude_code:no_result")
    try:
        return output.model_validate(result)
    except ValidationError as exc:
        raise ModelUnavailable("claude_code:invalid_output") from exc


# ------------------------------------------------------------------ the turn decision (understanding)


class TurnDecision(BaseModel):
    """What the model may decide for one owner message. Validated against the active Skill."""

    action: str = Field(description="One of the allowed actions listed in the prompt.")
    slot_value: str | None = Field(
        default=None,
        description=(
            "For answer_slot: exactly one of the listed option values; for money questions, "
            "'low|high' in plain digits (e.g. '200000|250000'); for counts, digits."
        ),
    )
    topic_id: str | None = Field(default=None, description="A topic id from the allowed list, if one fits.")
    step: str | None = Field(default=None, description="For go_back: the step to reopen.")
    fills: dict[str, str] | None = Field(
        default=None,
        description=(
            "When one message answers several of the listed questions at once (e.g. 'thirty shops, about "
            "two hundred thousand profit a month, young customers'), a value per slot id in the same formats "
            "as slot_value."
        ),
    )
    rule_id: str | None = Field(
        default=None, description="If the owner asks for something on the guard list, its rule id (R1-R8)."
    )
    milestone_id: str | None = Field(
        default=None,
        description="For mark_milestone_done: the id of the step the owner says is done, from the listed steps.",  # noqa: E501
    )


async def decide_turn(
    instructions: str,
    owner_text: str,
    allowed_actions: list[str],
    slot: str | None,
    options: list[str],
    topics: list[str],
    steps_done: list[str],
    extra_slots: dict[str, str] | None = None,
    correctable: dict[str, str] | None = None,
    milestones: dict[str, str] | None = None,
) -> TurnDecision | None:
    """Understand one free-text message. None if no model is available or the call failed."""
    if _TEST_DECIDER is not None:
        return _TEST_DECIDER(owner_text, allowed_actions, slot, options, topics, extra_slots or correctable)
    if not enabled("turn"):
        return None
    prompt = (
        f"Owner message: {owner_text!r}\n"
        f"Pending question slot: {slot or 'none'}\n"
        f"Options for it: {options or 'free answer'}\n"
        f"Allowed actions: {allowed_actions}\n"
        f"Topics in the library: {topics}\n"
        f"Steps the owner can go back to: {steps_done}"
        + (f"\nOther open questions this message may also answer (slot: format): {extra_slots}" if extra_slots else "")  # noqa: E501
        + (f"\nBusiness facts the owner can correct with correct_business (field: format): {correctable}" if correctable else "")  # noqa: E501
        + (f"\nGoal steps not yet done, in legal order (id: step), for mark_milestone_done: {milestones}" if milestones else "")  # noqa: E501
    )
    try:
        return await structured("turn", instructions, prompt, TurnDecision)
    except ModelUnavailable:
        return None
