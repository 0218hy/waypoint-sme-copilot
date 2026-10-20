"""Skill loader and registry (SPEC §4.1).

The YAML front matter of `skills/<name>/SKILL.md` is machine-read and enforced by the orchestrator:
the allowlists of tools, widgets and topics, the preconditions, the slot order, `max_turns`, and the
scripted lines (EN/ZH, number-free except placeholders). The Markdown body is the playbook the
model reads.
"""

from __future__ import annotations

import hashlib
import re
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from agent.render import check_text
from agent.widgets import WIDGET_TYPES

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
TOPICS_FILE = ROOT / "data" / "topics.yaml"

_FRONT = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_TEXT_VAR = re.compile(r"\{\{(?!fig:|rule:|topic:)[a-z_]+\}\}")
_MUST = re.compile(r"\{\{fig:[A-Za-z0-9_.:\-]+\}\}")

Step = Literal["welcome", "profile", "site", "cost", "funding", "goal_plan", "goal_keeper", "any"]


class Slot(BaseModel):
    id: str
    type: str
    ask: str | None = None
    default: str | None = None
    when: str | None = None
    skip_if: str | None = None
    optional: bool = False


class BeatSpec(BaseModel):
    """What a message must convey; the model writes the words (agent/voice.py)."""

    convey: str
    must: list[str] = []
    ask: bool = False


class SkillSpec(BaseModel):
    name: str
    version: int
    step: Step
    goal: str
    always_loaded: bool = False
    requires: list[str] = []
    produces: str | None = None
    slots: list[Slot] = []
    tools: list[str] = []
    widgets: list[str] = []
    topics: list[str] = []
    actions: list[str] = []
    max_turns: int = 0
    # questions whose answer completes the step: the owner answers them, never the max_turns fallback
    confirms: list[str] = []
    done_when: str
    next: str | None = None
    beats: dict[str, BeatSpec] = Field(default_factory=dict)
    labels: dict[str, dict[str, str]] = Field(default_factory=dict)
    body: str = ""
    sha256: str = ""

    def beat(self, key: str) -> BeatSpec:
        b = self.beats.get(key)
        if b is None:
            raise KeyError(f"skill {self.name!r} has no beat {key!r}")
        return b

    def label(self, key: str, lang: Literal["en", "zh"]) -> str:
        """UI button text (not a message)."""
        entry = self.labels.get(key)
        if entry is None:
            raise KeyError(f"skill {self.name!r} has no label {key!r}")
        return entry[lang]


class SkillError(ValueError):
    pass


def parse_skill(path: Path) -> SkillSpec:
    raw = path.read_text(encoding="utf-8")
    m = _FRONT.match(raw)
    if not m:
        raise SkillError(f"{path}: missing YAML front matter")
    meta: dict[str, Any] = yaml.safe_load(m.group(1))
    spec = SkillSpec(**meta, body=m.group(2).strip(), sha256=hashlib.sha256(raw.encode()).hexdigest())
    return spec


@cache
def topic_ids() -> frozenset[str]:
    data = yaml.safe_load(TOPICS_FILE.read_text(encoding="utf-8"))
    return frozenset(data["topics"].keys())


def validate(spec: SkillSpec, known_tools: frozenset[str]) -> list[str]:
    """Return problems; an empty list means the Skill is loadable."""
    problems: list[str] = []
    for w in spec.widgets:
        if w not in WIDGET_TYPES:
            problems.append(f"{spec.name}: unknown widget {w!r}")
    for t in spec.tools:
        if known_tools and t not in known_tools:
            problems.append(f"{spec.name}: unknown tool {t!r}")
    for t in spec.topics:
        if t not in topic_ids():
            problems.append(f"{spec.name}: unknown topic {t!r}")
    for key, entry in spec.labels.items():
        for lang in ("en", "zh"):
            if lang not in entry:
                problems.append(f"{spec.name}: label {key!r} missing {lang}")
                continue
            res = check_text(_TEXT_VAR.sub(" ", entry[lang]))
            if not res.ok:
                problems.append(f"{spec.name}: label {key!r}/{lang} has quantities {res.hits}")
    for key, b in spec.beats.items():
        for need in b.must:
            if not _MUST.fullmatch(need):
                problems.append(f"{spec.name}: beat {key!r} has a malformed required placeholder {need!r}")
    for slot in spec.slots:
        if slot.ask and slot.ask not in spec.beats:
            problems.append(f"{spec.name}: slot {slot.id!r} asks missing beat {slot.ask!r}")
    return problems


class SkillRegistry:
    def __init__(self, specs: dict[str, SkillSpec]) -> None:
        self.specs = specs
        self.by_step: dict[str, SkillSpec] = {s.step: s for s in specs.values() if s.step != "any"}

    def __getitem__(self, name: str) -> SkillSpec:
        return self.specs[name]

    def for_step(self, step: str) -> SkillSpec:
        return self.by_step[step]

    @property
    def always(self) -> list[SkillSpec]:
        return [s for s in self.specs.values() if s.always_loaded]

    def versions(self) -> dict[str, str]:
        return {name: f"v{s.version}:{s.sha256[:12]}" for name, s in sorted(self.specs.items())}


def load_skills(known_tools: frozenset[str] = frozenset(), directory: Path = SKILLS_DIR) -> SkillRegistry:
    specs = {p.parent.name: parse_skill(p) for p in sorted(directory.glob("*/SKILL.md"))}
    problems = [msg for s in specs.values() for msg in validate(s, known_tools)]
    for name, s in specs.items():
        if s.name != name:
            problems.append(f"{name}: front-matter name {s.name!r} doesn't match its folder")
    if problems:
        raise SkillError("; ".join(problems))
    return SkillRegistry(specs)
