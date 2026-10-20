"""Journey state (SPEC §3.1): one per owner, saved after every turn."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.approval import PendingCard
from tools.models import (
    CostCard,
    ExtractedQuote,
    FundingPlan,
    HostMode,
    PlanResult,
    Profile,
    Shortlist,
)

Step = Literal["welcome", "profile", "site", "cost", "funding", "goal_plan", "goal_keeper"]
STEPS: tuple[Step, ...] = ("welcome", "profile", "site", "cost", "funding", "goal_plan", "goal_keeper")
JOURNEY_STEPS: tuple[Step, ...] = ("profile", "site", "cost", "funding", "goal_plan")
STEP_LABELS: dict[str, dict[str, str]] = {
    "welcome": {"en": "Welcome", "zh": "欢迎"},
    "profile": {"en": "Your business", "zh": "你的生意"},
    "site": {"en": "Where", "zh": "开在哪里"},
    "cost": {"en": "What it costs", "zh": "要花多少"},
    "funding": {"en": "How to pay", "zh": "怎么筹钱"},
    "goal_plan": {"en": "Your plan", "zh": "你的计划"},
    "goal_keeper": {"en": "Goal Keeper", "zh": "目标跟进"},
}
SKILL_FOR_STEP: dict[str, str] = {
    "welcome": "welcome",
    "profile": "profile",
    "site": "site-finder",
    "cost": "cost",
    "funding": "funding",
    "goal_plan": "goal-plan",
    "goal_keeper": "goal-keeper",
}


class Pending(BaseModel):
    """The question the bot is waiting on (re-asked after a detour or a guard card)."""

    skill: str
    slot: str
    line: str
    widget_id: str | None = None
    options: list[dict[str, str | None]] = []
    vars: dict[str, str] = {}


class JourneyState(BaseModel):
    owner_id: str
    lang: Literal["en", "zh"] = "en"
    lang_chosen: bool = False
    host_mode: HostMode = HostMode.STANDALONE
    consent_feed: bool | None = None
    step: Step = "welcome"
    started: bool = False
    start_date: date
    turns_in_step: int = 0

    profile: Profile = Field(default_factory=Profile)
    profile_asked: list[str] = []
    shortlist: Shortlist = Field(default_factory=Shortlist)
    selected_area: str | None = None
    cost_card: CostCard | None = None
    cost_asked: list[str] = []
    quotes: list[ExtractedQuote] = []
    funding: FundingPlan | None = None
    funding_asked: list[str] = []
    plan: PlanResult | None = None
    goal_prefs: dict[str, Any] = {}
    goal_id: str | None = None
    revising: bool = False

    pending: Pending | None = None
    raised_topics: list[str] = []
    stale: list[Step] = []
    done: list[Step] = []
    widget_types: dict[str, str] = {}
    widget_steps: dict[str, str] = {}
    widget_seq: int = 0
    cards: dict[str, PendingCard] = {}
    used_nonces: list[str] = []
    guard_hits: dict[str, int] = {}
    last_alert_id: str | None = None
    pending_milestone: str | None = None  # a step waiting on the owner's "yes, it's done"
    failed_beats: list[dict[str, Any]] = []

    def next_widget_id(self) -> str:
        self.widget_seq += 1
        return f"w{self.widget_seq}"

    def steps_view(self) -> list[dict[str, str]]:
        out = []
        cur = self.step if self.step in JOURNEY_STEPS else None
        for s in JOURNEY_STEPS:
            if s in self.stale:
                status = "stale"
            elif s == cur:
                status = "current"
            elif s in self.done:
                status = "done"
            else:
                status = "todo"
            out.append({"id": s, "label": STEP_LABELS[s][self.lang], "status": status})
        return out

    def snapshot(self, llm_label: str, demo: bool) -> dict[str, Any]:
        return {
            "lang": self.lang,
            "host_mode": self.host_mode.value,
            "step": self.step,
            "steps": self.steps_view(),
            "goal_id": self.goal_id,
            "llm": llm_label,
            "demo": demo,
            "busy_widget": None,
        }
