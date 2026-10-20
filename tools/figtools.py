"""Helpers for building Figures from other Figures with taint carried along (SPEC §6.1)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from tools.figures import Figure, Source, SourceKind, Taint, Unit, dec


def derived(
    fig_id: str,
    label: str,
    unit: Unit,
    value: Decimal | float | int | None,
    *,
    tool: str,
    inputs: Sequence[Figure] = (),
    assumptions: tuple[str, ...] = (),
    low: Decimal | float | int | None = None,
    high: Decimal | float | int | None = None,
    note: str | None = None,
) -> Figure:
    """A tool-computed Figure. It is untrusted if any input is untrusted (taint propagates)."""
    tainted = any(f.taint == Taint.UNTRUSTED for f in inputs)
    return Figure(
        id=fig_id,
        label=label,
        unit=unit,
        value=None if value is None else dec(value),
        low=None if low is None else dec(low),
        high=None if high is None else dec(high),
        source=Source(kind=SourceKind.TOOL, ref=tool, note=note),
        assumptions=assumptions,
        taint=Taint.UNTRUSTED if tainted else Taint.TRUSTED,
        inputs=tuple(f.id for f in inputs),
    )


def sourced(
    fig_id: str,
    label: str,
    unit: Unit,
    value: Decimal | float | int | None,
    source: Source,
    *,
    taint: Taint = Taint.TRUSTED,
    assumptions: tuple[str, ...] = (),
) -> Figure:
    """A Figure read from data (public data, the feed, a document, the owner)."""
    return Figure(
        id=fig_id,
        label=label,
        unit=unit,
        value=None if value is None else dec(value),
        source=source,
        taint=taint,
        assumptions=assumptions,
    )


def by_id(figs: Sequence[Figure]) -> dict[str, Figure]:
    return {f.id: f for f in figs}
