"""Cached loaders for the data files the tools read (SPEC §10). Pure reads; no network."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from tools.models import Area, CostGroup, Milestone_, Unit

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
AREAS_PATH = DATA / "public" / "areas.json"
UNITS_PATH = DATA / "demo" / "units.yaml"
COST_KEY_PATH = DATA / "cost_key.yaml"
CATALOGUE_PATH = DATA / "funding_catalogue.yaml"
RULES_PATH = ROOT / "rules" / "rules.yaml"


class CostKeyLine(BaseModel):
    key: str
    group: CostGroup
    label_en: str
    label_zh: str
    due: Milestone_
    formula: str
    inputs: dict[str, str] = {}
    overrun: bool = False
    quotable: bool = False
    keywords: list[str] = []  # name the whole line
    part_keywords: list[str] = []  # name only part of it (sets a floor; the estimate stays)
    only_when: str | None = None
    gst_on: list[str] = []
    plus_reserve_rent: bool = False
    plus_reserve_supplies: bool = False  # utilities and other running costs in the reserve
    # how the unit-economics card treats the line: spent (sunk), returned (refundable, at opening or at the
    # end of the lease), working capital recovered at the end, or the running reserve (not an investment:
    # the ramp-up losses it covers are in the monthly cash flows)
    kind: Literal["sunk", "refundable", "working_capital", "reserve"] = "sunk"
    refund_at: Literal["opening", "lease_end"] | None = None
    likely_basis: str
    bad_basis: str
    source: str
    url: str | None = None
    as_of: date


class CostKey(BaseModel):
    as_of: date
    groups: dict[str, dict[str, str]]
    lines: list[CostKeyLine]

    def line(self, key: str) -> CostKeyLine:
        for ln in self.lines:
            if ln.key == key:
                return ln
        raise KeyError(key)


class CatalogueEntry(BaseModel):
    id: str
    status: Literal["open", "optional", "closed", "later"]
    rule_ids: list[str] = []
    variants: list[str] = []
    label_en: str
    label_zh: str
    covers_en: str
    covers_zh: str
    available_from_en: str
    available_from_zh: str
    cost_en: str
    cost_zh: str
    conditions_en: str
    conditions_zh: str
    source: str | None = None  # legal note for the route
    source_kind: Literal["law", "design", "law+design"] | None = None
    source_url: str | None = None
    # where it is shown: only `plan` routes count toward the Singapore plan (see the catalogue header)
    card: Literal["plan", "webank", "partner_bank", "after_opening"] = "plan"
    never_in_plan: str | None = None  # the rule a plan breaks if it counts this route
    note_rule: str | None = None  # a rule whose owner message is shown on the card (e.g. the R2 pause)
    as_of: date | None = None
    subject_to_approval: bool = False
    product_en: str | None = None
    product_zh: str | None = None
    product_url: str | None = None
    # ranking (tools/funding.rank_options): what the route costs the owner, when its money is in hand, what
    # ownership it gives up; `timing` routes change when money is paid, not how much, and aren't ranked
    cost_kind: Literal["own_cash", "terms", "profit_share", "timing"] | None = None
    # weeks from the plan start: a number, a timeline milestone id (its median week in the current plan), or
    # `setaside` (the months of set-aside the current mix needs)
    speed_weeks: int | str | None = None
    dilution: Literal["none", "partner_share"] | None = None
    eligible_when_en: str | None = None  # shown when the route isn't open to this owner yet
    eligible_when_zh: str | None = None

    @property
    def in_plan(self) -> bool:
        return self.card == "plan"

    def text(self, field: str, lang: str) -> str:
        return str(getattr(self, f"{field}_{'zh' if lang == 'zh' else 'en'}"))


class CompareEntry(BaseModel):
    """A column of "Compare funding plans": its plan routes and the toggle_option actions that apply it."""

    id: str
    routes: list[str]
    toggles: dict[str, bool]
    title_en: str
    title_zh: str
    blurb_en: str
    blurb_zh: str

    def text(self, field: str, lang: str) -> str:
        return str(getattr(self, f"{field}_{'zh' if lang == 'zh' else 'en'}"))


class Catalogue(BaseModel):
    as_of: date
    webank_role: dict[str, str]
    options: list[CatalogueEntry]
    compare: list[CompareEntry] = []

    def get(self, option_id: str) -> CatalogueEntry | None:
        for o in self.options:
            if o.id == option_id or option_id in o.variants:
                return o
        return None


def _yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_areas() -> tuple[Area, ...]:
    """Public planning-area data written by the data pipeline; empty if it isn't there yet."""
    if not AREAS_PATH.exists():
        return ()
    raw = json.loads(AREAS_PATH.read_text(encoding="utf-8"))
    rows = raw.get("areas", []) if isinstance(raw, dict) else raw
    return tuple(Area.model_validate(r) for r in rows)


def areas_by_id() -> dict[str, Area]:
    return {a.id: a for a in load_areas()}


@lru_cache(maxsize=1)
def load_units() -> tuple[Unit, ...]:
    raw = _yaml(UNITS_PATH)
    return tuple(Unit.model_validate(u) for u in raw["units"])


def unit_by_id(unit_id: str) -> Unit:
    for u in load_units():
        if u.id == unit_id:
            return u
    raise KeyError(f"unknown unit {unit_id!r}")


@lru_cache(maxsize=1)
def load_cost_key() -> CostKey:
    return CostKey.model_validate(_yaml(COST_KEY_PATH))


@lru_cache(maxsize=1)
def load_catalogue() -> Catalogue:
    return Catalogue.model_validate(_yaml(CATALOGUE_PATH))


@lru_cache(maxsize=1)
def load_rules_yaml() -> dict[str, Any]:
    raw = _yaml(RULES_PATH)
    if not isinstance(raw, dict):
        raise ValueError("rules.yaml must be a mapping")
    return raw
