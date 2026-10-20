"""Domain artifacts shared by tools, rules, the orchestrator and the store (SPEC §3.1, §6, §7).

Money fields are Decimal. SGD amounts end in `_sgd`, CNY amounts in `_cny`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- profile


class HostMode(StrEnum):
    EMBEDDED = "embedded"  # inside WeBank's app; feed available with consent
    STANDALONE = "standalone"  # web, email sign-in; owner-typed numbers


class CustomerGroup(StrEnum):
    STUDENTS = "students"
    OFFICE_WORKERS = "office_workers"
    YOUNG_ADULTS = "young_adults"
    FAMILIES = "families"
    TOURISTS = "tourists"


class Priority(StrEnum):
    FOOT_TRAFFIC = "foot_traffic"
    LOW_RENT = "low_rent"
    NEAR_CUSTOMERS = "near_customers"


class MoneyRange(BaseModel):
    low: Decimal
    high: Decimal

    @property
    def mid(self) -> Decimal:
        return (self.low + self.high) / 2


class ProfitMonth(BaseModel):
    month: date  # first day of the month
    revenue_cny: Decimal
    operating_profit_cny: Decimal


class WeekProfit(BaseModel):
    """One week of the (mock) feed: what the Goal Keeper's weekly check reads (added for §7.2)."""

    week_start: date
    revenue_cny: Decimal
    instore_revenue_cny: Decimal
    delivery_revenue_cny: Decimal
    operating_profit_cny: Decimal
    feed_missing: bool = False


class FeedSnapshot(BaseModel):
    """What the (mock) WeBank feed returns with consent. Labelled simulated in the demo."""

    as_of: date
    company_name: str
    shops: int
    business_type: str
    profit_history: list[ProfitMonth]
    cash_balance_cny: Decimal
    monthly_payroll_cny: Decimal
    monthly_loan_repayment_cny: Decimal
    loan_balance_cny: Decimal
    loan_limit_cny: Decimal
    normal_loan_balance_by_month_cny: dict[int, Decimal] = Field(
        description="Usual drawn balance for each calendar month (1-12), from the owner's own history."
    )
    owner_drawings_monthly_cny: Decimal
    home_commitments_monthly_cny: Decimal = Decimal("0")
    best_shop_cups_per_day: int | None = None
    avg_shop_cups_per_day: int | None = None  # the chain-average shop
    simulated: bool = True
    # added: weekly series for the Goal Keeper, and the savings pot sub-account if he uses one
    weekly_profit: list[WeekProfit] = []
    pot_balance_cny: Decimal | None = None
    # the owner said less is spare than the feed implies (money earmarked): plan with the lower figure
    owner_spare_cash_cny: Decimal | None = None


class Profile(BaseModel):
    business_type: str = "tea"
    shops: int | None = None
    monthly_profit_cny: MoneyRange | None = None
    spare_cash_cny: Decimal | None = None
    cash_balance_cny: Decimal | None = None
    monthly_payroll_cny: Decimal | None = None
    monthly_loan_repayment_cny: Decimal | None = None
    owner_drawings_monthly_cny: Decimal | None = None
    customers: list[CustomerGroup] = []
    budget_sgd: MoneyRange | None = None  # None = "not sure"
    opening_window_months: int | None = None  # hoped-for months from now
    best_shop_cups_per_day: int | None = None
    avg_shop_cups_per_day: int | None = None  # the chain-average shop
    expected_sg_cups_per_day: int | None = None  # the owner's own figure for the Singapore shop (cost step)
    sources: dict[str, Literal["feed", "owner", "computed"]] = {}
    # the owner's figure for a field the feed provides, above the feed's: shown as not verified, never used
    unverified: dict[str, str] = {}
    confirmed: bool = False


# ---------------------------------------------------------------- sites


class Area(BaseModel):
    id: str  # planning area code, e.g. "TAMPINES"
    name: str
    region: str
    residents: int | None = None
    age_shares: dict[str, float] = {}  # band -> share of residents, e.g. "20-39": 0.31
    income_shares: dict[str, float] = {}  # band -> share of households
    daytime_proxy: float | None = None  # relative index (workers/students), 0..1
    station_traffic_monthly: int | None = None  # tap-ins+outs at stations in or near the area
    food_outlets: int | None = None
    rent_psf_month_sgd: MoneyRange | None = None  # typical retail rent per sq ft per month
    centroid: tuple[float, float] | None = None  # lat, lng
    sources: dict[str, str] = {}  # field -> dataset id/date
    simulated_fields: list[str] = []


class Unit(BaseModel):
    id: str
    mall: str
    unit_no: str
    area_id: str
    size_sqft: int
    rent_monthly_sgd: Decimal
    service_charge_monthly_sgd: Decimal
    gto_pct: Decimal | None = None  # turnover rent, share of gross sales above the base
    lease_years: int = 3
    available_from: date | None = None
    lat: float | None = None
    lng: float | None = None
    simulated: bool = True


class AreaScore(BaseModel):
    area_id: str
    score: float  # 0..100
    contributions: dict[str, float]  # factor -> points
    reasons: list[str]  # reason codes, rendered by the UI/explainer, e.g. "many_young_adults"


class Shortlist(BaseModel):
    priority: Priority | None = None
    ruled_out_areas: list[str] = []
    size_range_sqft: tuple[int, int] = (400, 900)
    ranked: list[AreaScore] = []
    area_ids: list[str] = []
    unit_ids: list[str] = []
    chosen_unit_id: str | None = None
    confirmed: bool = False


# ---------------------------------------------------------------- costs

CostGroup = Literal["lease", "fitout", "setup", "people", "reserve", "gst"]
Milestone_ = Literal["incorporate", "setup_transfer", "first_transfer", "sign_lease", "fitout", "opening"]


class CostLine(BaseModel):
    key: str
    group: CostGroup
    label: str
    likely_sgd: Decimal
    bad_sgd: Decimal
    due: Milestone_ = "first_transfer"
    source: str  # cost_key line id, or "quote:<doc_id>"
    from_quote: bool = False
    note: str | None = None
    # added: the triangular range behind likely/bad, so the plan model can re-sample the line
    low_sgd: Decimal | None = None
    high_sgd: Decimal | None = None
    overrun: bool = False  # in the correlated-overrun group (Gaussian copula)
    label_zh: str | None = None
    # added: likely is the line's share of the median total; mode is the line at every input's most likely
    # value (the triangular mode the plan model re-samples around)
    mode_sgd: Decimal | None = None
    quote_sgd: Decimal | None = None  # accepted quote (whole line, or the quoted parts), before allowance
    quote_cover: Literal["whole", "part"] | None = None
    flags: list[Literal["partial", "below_estimate", "conflict"]] = []


class CostCard(BaseModel):
    unit_id: str
    fitout_level: Literal["basic", "standard", "premium"] = "standard"
    manager_plan: Literal["send_own", "hire_local"] = "hire_local"
    lines: list[CostLine]
    total_likely_sgd: Decimal
    total_bad_sgd: Decimal
    fx_cny_per_sgd: Decimal
    missing: list[str] = []
    confirmed: bool = False
    # added: what the card was built from, so plans and repairs can re-derive rent-dependent lines
    rent_monthly_sgd: Decimal | None = None  # base rent + service charge
    rent_free_months: Decimal | None = None
    size_sqft: int | None = None
    bad_quantile: Decimal | None = None
    seed: int | None = None
    total_base_sgd: Decimal | None = None  # sum of each line at every input's most likely value

    def by_group(self) -> dict[str, list[CostLine]]:
        out: dict[str, list[CostLine]] = {}
        for ln in self.lines:
            out.setdefault(ln.group, []).append(ln)
        return out


class ExtractedLine(BaseModel):
    id: str
    label: str
    amount: Decimal | None
    currency: Literal["SGD", "CNY"] = "SGD"
    bbox: tuple[float, float, float, float] | None = None  # x, y, w, h as fractions of the image
    confidence: float = 0.0
    matched_key: str | None = None  # None = no keyword matched; the owner assigns it
    part: bool = False  # prices only part of the matched cost line
    status: Literal["pending", "accepted", "rejected", "check"] = "pending"


class ExtractedQuote(BaseModel):
    doc_id: str
    lines: list[ExtractedLine]
    exclusions: list[str] = []
    dates: list[str] = []
    taint: Literal["untrusted"] = "untrusted"


# ---------------------------------------------------------------- funding and plan


class FundingOption(BaseModel):
    id: str
    label: str
    status: Literal["open", "optional", "closed", "later"]
    covers: str
    available_from: str
    cost: str
    conditions: str
    rule_ids: list[str] = []
    on: bool = False
    source: str | None = None  # the route's legal note, if it has one
    source_url: str | None = None
    source_kind: Literal["law", "design", "law+design"] | None = None
    card: Literal["plan", "webank", "partner_bank", "after_opening"] = "plan"  # only `plan` routes count
    as_of: date | None = None
    subject_to_approval: bool = False
    product: str | None = None  # the bank's own product page
    product_url: str | None = None
    note: str | None = None  # a rule's owner message shown on the card (e.g. the R2 pause)
    note_rule: str | None = None


class FundingPlan(BaseModel):
    setaside_share: Decimal = Decimal("0.40")
    own_savings_cny: Decimal = Decimal("0")
    rent_free_months: Decimal = Decimal("1")
    staged_contractor: bool = False
    partner_equity_share: Decimal = Decimal("0")
    partner_considered: bool = False  # the owner said a local partner is possible (opens the compare column)
    options_on: list[str] = []
    floor_cny: Decimal | None = None
    buffer_cny: Decimal | None = None
    confirmed: bool = False
    # added for R4 / R7 checks
    pre_investment_cny: Decimal = Decimal("0")  # 前期费用 remitted before the company exists
    pre_investment_covers: list[str] = []  # cost line keys it pays for
    own_savings_source: Literal["savings", "borrowed"] = "savings"


class PlanChart(BaseModel):
    weeks: list[int]
    pot_p10: list[float]
    pot_p50: list[float]
    pot_p90: list[float]
    need: list[float]  # cumulative money needed in Singapore by each week (median schedule)
    home_p05: list[float]
    home_p50: list[float]
    floor: list[float]
    milestones: list[tuple[int, str]]
    currency: Literal["CNY"] = "CNY"


class PlanResult(BaseModel):
    setaside_share: Decimal
    open_likely_week: int | None  # None = doesn't open within the horizon in the median run
    open_p95_week: int | None
    floor_risk: Decimal  # share of runs dipping below the floor
    opened_share: Decimal  # share of runs that open within the horizon
    wall_share: Decimal  # largest share whose floor risk is <= the limit (Wilson 95% upper bound)
    monthly_setaside_cny: Decimal
    gap_cny: Decimal
    milestone_weeks: dict[str, int]  # median week of each milestone
    chart: PlanChart
    runs: int
    seed: int
    floor_risk_runs: int | None = None  # runs the floor risk is estimated on, if not `runs` (the preview)


class MilestoneStatus(StrEnum):
    UPCOMING = "upcoming"
    DUE = "due"
    DONE = "done"
    LATE = "late"


class Milestone(BaseModel):
    id: str
    order: int
    label: str
    who: str
    likely_week: int
    latest_safe_week: int
    act_by_week: int
    status: MilestoneStatus = MilestoneStatus.UPCOMING
    done_at: date | None = None


# ---------------------------------------------------------------- goal and Goal Keeper


class GoalStatus(StrEnum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OFF_TRACK = "off_track"


class GoalRevision(BaseModel):
    at: datetime
    reason: Literal["created", "checkin", "alert", "owner"]
    summary: str
    approved_card_hash: str
    before: dict[str, str] = {}
    after: dict[str, str] = {}


class Goal(BaseModel):
    id: str
    owner_id: str
    start_date: date
    unit_id: str
    cost_total_likely_sgd: Decimal
    funding: FundingPlan
    target_open_likely_week: int
    target_open_p95_week: int
    setaside_monthly_cny: Decimal
    floor_cny: Decimal
    floor_risk: Decimal
    milestones: list[Milestone]
    status: GoalStatus = GoalStatus.ON_TRACK
    checkin_frequency: Literal["weekly", "fortnightly", "monthly"] = "monthly"
    email_amounts: bool = False
    recurring_setaside: bool = False
    revisions: list[GoalRevision] = []
    created_at: datetime


class CheckIn(BaseModel):
    goal_id: str
    week: int
    on: date
    profit_cny: Decimal | None
    set_aside_cny: Decimal | None
    loan_balance_cny: Decimal | None = None
    source: Literal["feed", "owner"]
    channel_shift: bool = False


class Repair(BaseModel):
    id: str
    kind: Literal["raise_share", "add_savings", "cheaper_unit", "rent_free", "stage_contractor", "move_target"]  # noqa: E501
    params: dict[str, str]
    new_open_likely_week: int | None
    new_open_p95_week: int | None
    new_floor_risk: Decimal
    rules_ok: bool


class Alert(BaseModel):
    id: str
    goal_id: str
    created_at: datetime
    kind: Literal["date_slip", "floor_risk", "milestone_due", "status_worse", "r2_pause"]
    weeks_moved: int = 0
    act_by: date | None = None
    status_before: GoalStatus
    status_after: GoalStatus
    repairs: list[Repair] = []
    resolved_with: str | None = None


# ---------------------------------------------------------------- rules (added)


class Violation(BaseModel):
    """A rule a plan or action breaks (SPEC §8.1). `blocking=False` is a notice (e.g. an R2 pause)."""

    rule_id: str
    blocking: bool = True
    object: str  # what was checked: funding_plan, plan_result, action, funding_source, feed
    title_en: str
    title_zh: str
    message_en: str
    message_zh: str
    consequence_en: str
    consequence_zh: str
    source: str
    source_url: str | None = None
    source_kind: Literal["law", "design", "law+design"] | None = None
    detail: str = ""
