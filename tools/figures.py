"""Figures: every number Waypoint shows, with its unit, source, date and taint (SPEC §6.1).

Money is Decimal with an explicit currency. A missing value is None, never zero.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Unit = Literal[
    "SGD", "CNY", "weeks", "months", "pct", "count", "cups_per_day", "sqft", "people", "score", "times"
]


class SourceKind(StrEnum):
    TOOL = "tool"
    FEED = "feed"
    DOCUMENT = "document"
    PUBLIC_DATA = "public_data"
    OWNER = "owner"
    PARAM = "param"
    SIMULATED = "simulated"


class Taint(StrEnum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class Source(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: SourceKind
    ref: str = Field(description="Tool name, dataset id, document id, parameter key or 'owner'.")
    as_of: date | None = None
    note: str | None = None
    url: str | None = None


class Figure(BaseModel):
    """One displayed quantity. `value` is the point value; `low`/`high` give a range when known."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    unit: Unit
    value: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None
    source: Source
    assumptions: tuple[str, ...] = ()
    taint: Taint = Taint.TRUSTED
    inputs: tuple[str, ...] = Field(default=(), description="Ids of the Figures this one was computed from.")

    @property
    def is_missing(self) -> bool:
        return self.value is None and self.low is None and self.high is None


class FigureStore:
    """Per-turn registry of Figures. Computed Figures inherit taint from their inputs."""

    def __init__(self) -> None:
        self._figs: dict[str, Figure] = {}

    def add(self, fig: Figure) -> Figure:
        if fig.inputs:
            tainted = any(
                (src := self._figs.get(i)) is not None and src.taint == Taint.UNTRUSTED for i in fig.inputs
            )
            if tainted and fig.taint != Taint.UNTRUSTED:
                fig = fig.model_copy(update={"taint": Taint.UNTRUSTED})
        self._figs[fig.id] = fig
        return fig

    def get(self, fig_id: str) -> Figure | None:
        return self._figs.get(fig_id)

    def __contains__(self, fig_id: object) -> bool:
        return fig_id in self._figs

    def all(self) -> dict[str, Figure]:
        return dict(self._figs)

    def update(self, other: FigureStore) -> None:
        for f in other.all().values():
            self.add(f)


def q2(x: Decimal) -> Decimal:
    """Round money to cents."""
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def q0(x: Decimal) -> Decimal:
    return x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def dec(x: float | int | str | Decimal) -> Decimal:
    """Convert a model output to Decimal via str, so binary float noise never reaches money."""
    if isinstance(x, Decimal):
        return x
    if isinstance(x, float):
        return Decimal(repr(round(x, 6)))
    return Decimal(str(x))


def tool_fig(
    fig_id: str,
    label: str,
    unit: Unit,
    value: Decimal | float | int | None,
    *,
    tool: str,
    low: Decimal | float | int | None = None,
    high: Decimal | float | int | None = None,
    assumptions: tuple[str, ...] = (),
    inputs: tuple[str, ...] = (),
    note: str | None = None,
    as_of: date | None = None,
) -> Figure:
    return Figure(
        id=fig_id,
        label=label,
        unit=unit,
        value=None if value is None else dec(value),
        low=None if low is None else dec(low),
        high=None if high is None else dec(high),
        source=Source(kind=SourceKind.TOOL, ref=tool, note=note, as_of=as_of),
        assumptions=assumptions,
        inputs=inputs,
    )
