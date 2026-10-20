"""Widget payload contracts (SPEC §5).

A widget is rendered only from a tool payload built by code. The AI may ask for a widget type,
never supply its contents. Payload numbers are Figure ids (resolved from `figures`) or chart
series computed by tools. `make contracts` exports these models as JSON Schema for the web app.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from tools.figures import Figure

# ------------------------------------------------------------------ shared pieces


class Option(BaseModel):
    value: str
    label: str
    detail: str | None = None


class SourceNote(BaseModel):
    label: str
    url: str | None = None
    as_of: str | None = None
    # for a rule or a legal note: law, Waypoint's own design rule, or both (rules/rules.yaml `kind`)
    kind: Literal["law", "design", "law+design"] | None = None


# ------------------------------------------------------------------ payloads


class QuickReplies(BaseModel):
    type: Literal["quick_replies"] = "quick_replies"
    slot: str
    options: list[Option]
    default: str | None = None
    allow_text: bool = True


class ProfileField(BaseModel):
    key: str
    label: str
    figure: str | None = None  # figure id for numeric fields
    text: str | None = None  # for non-numeric fields (already localised)
    source: Literal["feed", "owner", "computed", "missing"]
    editable: bool = True
    input: Literal["money_cny", "count", "enum", "multi", "text"] = "text"
    options: list[Option] = []


class ProfileCard(BaseModel):
    type: Literal["profile_card"] = "profile_card"
    fields: list[ProfileField]
    simulated_feed: bool = False


class RatioRow(BaseModel):
    """One ratio on the at-a-glance card: a figure, optionally a second one to read it against."""

    key: str
    label: str
    figure: str  # figure id
    compare: str | None = None  # figure id: what it is read against (same months last year, after drawings)
    compare_label: str | None = None
    note: str | None = None  # how it is worked out, or a caveat (already localised)
    caveat: bool = False  # the note is a warning (e.g. the runway is overstated)


class BusinessGlance(BaseModel):
    """"Your business at a glance": ratios computed from the (mock) feed alone (tools/ratios.py)."""

    type: Literal["business_glance"] = "business_glance"
    rows: list[RatioRow]
    singapore: list[RatioRow] = []  # the Singapore shop against the chain, once its costs are known
    as_of: str
    simulated_feed: bool = True
    note: str | None = None


class ConsentCard(BaseModel):
    type: Literal["consent_card"] = "consent_card"
    reads: list[str]
    never: list[str]
    withdraw: str


class MapArea(BaseModel):
    id: str
    name: str
    score: float | None = None
    rank: int | None = None


class AreaMap(BaseModel):
    type: Literal["area_map"] = "area_map"
    geojson_url: str
    areas: list[MapArea]
    top: list[str]
    reasons: dict[str, list[str]]  # area id -> localised reason lines (from reason codes)
    sources: list[SourceNote]


class Factor(BaseModel):
    key: str
    label: str
    points: float
    max_points: float
    detail: str


class AreaCard(BaseModel):
    type: Literal["area_card"] = "area_card"
    area_id: str
    name: str
    score: float
    factors: list[Factor]
    stats: list[str]  # figure ids: residents, share in customer group, rent range, station traffic, outlets
    age_bands: dict[str, float] = {}
    sources: list[SourceNote]
    simulated_fields: list[str] = []


class UnitRow(BaseModel):
    id: str
    mall: str
    unit_no: str
    area_name: str
    size_sqft: int
    rent: str  # figure id (rent + service charge, SGD/month)
    gto_pct: float | None = None
    breakeven: str  # figure id, cups/day
    best_shop_cups: str | None = None  # figure id
    avg_shop_cups: str | None = None  # figure id, the chain-average shop
    early_cost: str  # figure id, SGD likely
    lat: float | None = None
    lng: float | None = None
    simulated: bool = True


class UnitCompare(BaseModel):
    type: Literal["unit_compare"] = "unit_compare"
    units: list[UnitRow]
    chosen: str | None = None


class CostLineRow(BaseModel):
    key: str
    label: str
    likely: str  # figure id
    bad: str  # figure id
    source: SourceNote
    from_quote: bool = False
    editable: bool = True
    flags: list[Literal["partial", "below_estimate", "conflict"]] = []  # quotes to check on this line


class CostGroupRow(BaseModel):
    key: str
    label: str
    likely: str
    bad: str
    lines: list[CostLineRow]


class CostBreakdown(BaseModel):
    type: Literal["cost_breakdown"] = "cost_breakdown"
    groups: list[CostGroupRow]
    total_likely: str
    total_bad: str
    total_likely_cny: str
    total_bad_cny: str
    read_only: bool = False


class EconLine(BaseModel):
    """One labelled figure on the unit-economics card."""

    key: str
    label: str
    figure: str  # figure id
    estimate: bool = False  # depends on build-team assumptions: shown with an "estimate" chip
    note: str | None = None


class PnlRow(BaseModel):
    """The store P&L at one steady cups-a-day level (a month at steady state), payback and NPV."""

    key: str  # "300", or "owner" for the owner's own figure
    cups: str  # figure ids from here on
    owner: bool = False
    registered: bool = False  # sales over the GST threshold: treated as GST-registered
    revenue: str
    ebitda: str
    margin: str
    depreciation: str
    tax: str
    net: str
    payback_likely: str
    payback_bad: str
    npv: str
    npv_bad: str


class Benchmark(BaseModel):
    label: str
    figure: str
    source: SourceNote


class UnitEconomics(BaseModel):
    """"Unit economics & payback" for the chosen unit (tools/unit_econ.py)."""

    type: Literal["unit_economics"] = "unit_economics"
    unit_id: str
    unit_name: str
    headline: list[EconLine]
    per_cup: list[EconLine]
    fixed: list[EconLine]
    investment: list[EconLine]
    rows: list[PnlRow]
    sensitivity: list[EconLine]
    ramp_likely: list[float]  # share of steady cups in months 1..n (an estimate)
    ramp_bad: list[float]
    benchmarks: list[Benchmark]
    chain: list[RatioRow] = []  # the shop against the chain (with the feed only; tools/ratios.py)
    notes: list[str] = []  # how it is worked out (already localised)
    owner_cups: int | None = None
    editable: bool = True  # the owner can type their own cups-a-day figure


class ExtractedRow(BaseModel):
    id: str
    label: str
    amount: str | None  # figure id (untrusted until accepted)
    bbox: tuple[float, float, float, float] | None = None
    confidence: float
    status: Literal["pending", "accepted", "rejected", "check"]
    matched_label: str | None = None
    matched_key: str | None = None  # None: no cost line matched; the owner assigns it
    part: bool = False  # prices only part of the matched cost line


class CoverageRow(BaseModel):
    """A cost line this quote touches, and whether it covers all of it (the owner can change it)."""

    key: str
    label: str
    whole: bool


class UploadPrompt(BaseModel):
    type: Literal["upload_prompt"] = "upload_prompt"
    accept: list[str] = ["image/jpeg", "image/png", "image/heic", "application/pdf"]
    max_mb: int = 10
    doc_id: str | None = None
    image_url: str | None = None
    extracted: list[ExtractedRow] = []
    exclusions: list[str] = []
    reader_mode: Literal["model", "replay", "none"] = "none"
    coverage: list[CoverageRow] = []
    assignable: list[Option] = []  # cost lines an unmatched quote line can be assigned to


class MissingItems(BaseModel):
    type: Literal["missing_items"] = "missing_items"
    items: list[Option]  # value = cost line key, label, detail = why it's flagged


class RankWhy(BaseModel):
    """Figure ids behind a ranked route's words, in the order the ranking compares them."""

    cost: str
    weeks: str | None = None
    dilution: str
    floor_change: str | None = None


class FundingCard(BaseModel):
    id: str
    label: str
    status: Literal["open", "optional", "closed", "later"]
    covers: str
    available_from: str
    cost: str
    conditions: str
    amount: str | None = None  # figure id
    on: bool = False
    rule_ids: list[str] = []
    source: SourceNote | None = None  # the route's legal note, if it has one
    # plan: a route in the Singapore plan (switchable); webank / partner_bank: what the banks do around
    # the plan, shown read-only and never counted toward Singapore
    variant: Literal["plan", "webank", "partner_bank", "after_opening"] = "plan"
    as_of: str | None = None
    subject_to_approval: bool = False
    product: SourceNote | None = None  # the bank's own product page
    note: str | None = None  # a rule's owner message on the card (the R2 pause on WeBank's home card)
    note_rule: str | None = None
    # per-owner ranking (tools/funding.rank_options): words, never a score; a figure behind each word
    words: list[str] = []
    why: RankWhy | None = None
    why_not: str | None = None  # on a `not_yet` card: what would open the route to this owner


class FundingOptions(BaseModel):
    type: Literal["funding_options"] = "funding_options"
    gap: str  # figure id
    spare: str  # figure id
    options: list[FundingCard]
    webank_role: str
    bank_cards: list[FundingCard] = []  # WeBank / registering-bank cards, never in the plan
    later_cards: list[FundingCard] = []  # after opening (status later), a view never counted (R8)
    not_yet: list[FundingCard] = []  # plan routes not open to this owner yet, each with why_not


class CompareTerms(BaseModel):
    """A route's own cost and conditions in a compare column (the catalogue's words)."""

    id: str
    label: str
    cost: str
    conditions: str


class CompareToggle(BaseModel):
    """One toggle_option action "Choose this funding" sends for its column."""

    id: str
    on: bool


class CompareColumn(BaseModel):
    id: Literal["setaside", "savings", "partner"]
    title: str
    blurb: str
    open: bool = True
    why_not: str | None = None  # the partner column before the owner says a partner is possible
    chosen: bool = False  # the owner's current plan is this column
    savings_editable: bool = False
    # figure ids; None on a column that isn't open
    savings: str | None = None
    monthly: str | None = None
    open_likely: str | None = None
    open_p95: str | None = None
    floor_risk: str | None = None
    floor_risk_upper: str | None = None
    ownership: str | None = None
    profit_share: str | None = None
    pros: list[str] = []  # ranking words (tools/funding.ranking_words, tools/compare.py)
    cons: list[str] = []
    terms: list[CompareTerms] = []
    toggles: list[CompareToggle] = []


class FundingCompare(BaseModel):
    """Compare funding plans: each column one full solve of the plan model at the slider's share."""

    type: Literal["funding_compare"] = "funding_compare"
    share: float  # the slider's committed share, sent back with "Choose this funding"
    share_fig: str  # figure id of that share
    columns: list[CompareColumn]
    savings_max: str  # figure id: the most the savings column takes
    preview_url: str = "/api/preview/compare"


class ClosedRoute(BaseModel):
    id: str
    label: str
    rule_id: str
    reason: str
    source: SourceNote


class ClosedOptions(BaseModel):
    type: Literal["closed_options"] = "closed_options"
    options: list[ClosedRoute]


class ChartSeries(BaseModel):
    weeks: list[int]
    month_labels: list[str]
    pot_p10: list[float]
    pot_p50: list[float]
    pot_p90: list[float]
    need: list[float]
    home_p05: list[float]
    home_p50: list[float]
    floor: list[float]
    milestones: list[tuple[int, str]]
    currency: Literal["CNY"] = "CNY"


class SetasideSlider(BaseModel):
    type: Literal["setaside_slider"] = "setaside_slider"
    share: float
    min: float = 0.0
    max: float = 1.0
    step: float = 0.05
    wall: float
    preview_url: str
    chart: ChartSeries
    open_likely: str  # figure ids
    open_p95: str
    floor_risk: str
    monthly_amount: str
    opened_share: str


class MixSegment(BaseModel):
    key: str
    label: str
    amount: str  # figure id (CNY)


class FundingMix(BaseModel):
    type: Literal["funding_mix"] = "funding_mix"
    total: str
    segments: list[MixSegment]


class TimelineItem(BaseModel):
    id: str
    order: int
    label: str
    who: str
    likely: str  # figure id (date as weeks from start) -> rendered as date via start_date
    likely_date: str
    latest_safe_date: str
    act_by_date: str
    status: Literal["upcoming", "due", "done", "late"] = "upcoming"
    detail: str = ""
    done_date: str | None = None  # when the owner marked it done
    can_mark_done: bool = False  # code-checked: every earlier step in legal order is done
    money_step: bool = False  # marking it done asks the owner to confirm they released the money


class MilestoneTimeline(BaseModel):
    type: Literal["milestone_timeline"] = "milestone_timeline"
    start_date: str
    items: list[TimelineItem]
    step: Literal["goal_plan", "goal_keeper"] = "goal_plan"  # goal_keeper: the active goal's own timeline


class GoalSummary(BaseModel):
    type: Literal["goal_summary"] = "goal_summary"
    sentence: str  # rendered text, figures already filled
    figures: list[str]
    assumptions: list[str]


class ApprovalLine(BaseModel):
    label: str
    value: str


class ApprovalCard(BaseModel):
    type: Literal["approval_card"] = "approval_card"
    action: Literal["create_goal", "revise_goal", "recurring_setaside"]
    title: str
    lines: list[ApprovalLine]
    card_hash: str
    nonce: str
    expires_at: str
    state: Literal["pending", "approved", "cancelled", "refused", "expired"] = "pending"
    refusal: str | None = None


class StatusCard(BaseModel):
    type: Literal["status_card"] = "status_card"
    status: Literal["on_track", "at_risk", "off_track"]
    headline: str
    changes: list[str]
    figures: list[str]


class AlertCard(BaseModel):
    type: Literal["alert_card"] = "alert_card"
    alert_id: str
    kind: str
    headline: str
    weeks_moved: str | None = None  # figure id
    act_by_date: str | None = None
    resolved: bool = False  # a fix was chosen for it: shown for the record, no action


class RepairRow(BaseModel):
    id: str
    label: str
    detail: str
    new_open_likely: str  # figure ids
    new_open_p95: str
    new_floor_risk: str


class RepairOptions(BaseModel):
    type: Literal["repair_options"] = "repair_options"
    alert_id: str
    repairs: list[RepairRow]


class RuleCard(BaseModel):
    type: Literal["rule_card"] = "rule_card"
    rule_id: str
    title: str
    message: str
    consequence: str
    source: SourceNote
    options: list[Option]


class TopicCard(BaseModel):
    type: Literal["topic_card"] = "topic_card"
    topic_id: str
    title: str
    say: str
    more: str
    source: SourceNote


class ConfirmCard(BaseModel):
    type: Literal["confirm_card"] = "confirm_card"
    step: str
    title: str
    items: list[ApprovalLine]
    confirm_label: str
    edit_label: str


class CheckinForm(BaseModel):
    type: Literal["checkin_form"] = "checkin_form"
    goal_id: str
    period_label: str
    fields: list[Literal["profit_cny", "set_aside_cny"]] = ["profit_cny", "set_aside_cny"]
    period: str | None = None  # the check-in email's period ("w<n>") when opened from its link


class PlanVsActual(BaseModel):
    type: Literal["plan_vs_actual"] = "plan_vs_actual"
    weeks: list[int]
    month_labels: list[str]
    planned_pot: list[float]
    actual_pot: list[float | None]
    planned_profit: list[float]
    actual_profit: list[float | None]
    milestones: list[tuple[int, str]]
    today_week: int
    currency: Literal["CNY"] = "CNY"


class PlanSummary(BaseModel):
    type: Literal["plan_summary"] = "plan_summary"
    kind: Literal["site", "cost", "funding"]
    title: str
    lines: list[ApprovalLine]
    figures: list[str]
    reopen_step: Literal["site", "cost", "funding"]


class DraftFact(BaseModel):
    """One fact a draft states: a label and either a Figure id (a quantity) or plain text."""

    label: str
    figure: str | None = None
    text: str = ""


class ChecklistItem(BaseModel):
    id: str
    text: str
    who: Literal["owner", "agent", "provider", "bank"]
    source: SourceNote


class DraftCard(BaseModel):
    """A draft the owner sends or a checklist the owner works through (SPEC §7.4, tier T1).

    Waypoint never sends it. For a consent request, `facts` are built by code from the goal and
    `body` is the model-written prose (placeholders filled by code after the number check)."""

    type: Literal["draft_card"] = "draft_card"
    kind: Literal["consent_request", "checklist"]
    milestone_id: str
    title: str
    to: str = ""
    subject: str = ""
    body: str = ""
    facts: list[DraftFact] = []
    items: list[ChecklistItem] = []
    who: str = ""
    sources: list[SourceNote] = []
    as_of: str | None = None
    filename: str


WidgetPayload = Annotated[
    QuickReplies
    | ProfileCard
    | BusinessGlance
    | ConsentCard
    | AreaMap
    | AreaCard
    | UnitCompare
    | CostBreakdown
    | UnitEconomics
    | UploadPrompt
    | MissingItems
    | FundingOptions
    | ClosedOptions
    | SetasideSlider
    | FundingMix
    | FundingCompare
    | MilestoneTimeline
    | GoalSummary
    | ApprovalCard
    | StatusCard
    | AlertCard
    | RepairOptions
    | RuleCard
    | TopicCard
    | ConfirmCard
    | CheckinForm
    | PlanVsActual
    | PlanSummary
    | DraftCard,
    Field(discriminator="type"),
]

WIDGET_TYPES: tuple[str, ...] = (
    "quick_replies",
    "profile_card",
    "business_glance",
    "consent_card",
    "area_map",
    "area_card",
    "unit_compare",
    "cost_breakdown",
    "unit_economics",
    "upload_prompt",
    "missing_items",
    "funding_options",
    "closed_options",
    "setaside_slider",
    "funding_mix",
    "funding_compare",
    "milestone_timeline",
    "goal_summary",
    "approval_card",
    "status_card",
    "alert_card",
    "repair_options",
    "rule_card",
    "topic_card",
    "confirm_card",
    "checkin_form",
    "plan_vs_actual",
    "plan_summary",
    "draft_card",
)


class Widget(BaseModel):
    """What travels to the UI: one payload plus the Figures it references (already formatted)."""

    id: str
    payload: WidgetPayload
    figures: dict[str, Figure] = {}
    display: dict[str, str] = Field(
        default_factory=dict, description="Figure id -> formatted text in the session language."
    )


class WidgetEvent(BaseModel):
    """A structured event from a widget (sent in AG-UI forwardedProps; never parsed from free text)."""

    widget_id: str
    event: Literal[
        "reply",
        "edit",
        "confirm",
        "consent",
        "select_area",
        "shortlist",
        "select_unit",
        "edit_line",
        "upload",
        "accept_line",
        "accept_all",
        "reject_line",
        "assign_line",
        "set_coverage",
        "mark_included",
        "toggle_option",
        "slider_commit",
        "open_milestone",
        "mark_milestone_done",
        "approve",
        "cancel",
        "see_repairs",
        "select_repair",
        "select_option",
        "reopen_step",
        "checkin",
        "back",
    ]
    value: Any = None
    data: dict[str, Any] = {}
