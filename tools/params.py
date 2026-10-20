"""The one loader for `data/params.yaml` (SPEC §13). Cached, typed accessors; nothing else reads the file.

Every parameter has `value`, `unit`, `source`, `as_of` and `note`. Tests may temporarily replace values
with `overrides({...})`; every cache keyed on parameters includes `version()` so it is invalidated.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from tools.figures import Figure, Source, SourceKind, Unit, dec

PARAMS_PATH = Path(__file__).resolve().parents[1] / "data" / "params.yaml"


class Param(BaseModel):
    key: str
    value: Any
    unit: str
    source: str
    as_of: date | None = None
    note: str | None = None
    url: str | None = None


class Tri(BaseModel):
    """A triangular distribution (low, likely, high)."""

    model_config = ConfigDict(frozen=True)

    low: float
    likely: float
    high: float

    def scaled(self, k: float) -> Tri:
        return Tri(low=self.low * k, likely=self.likely * k, high=self.high * k)


_overrides: dict[str, Any] = {}
_version: list[int] = [0]


@lru_cache(maxsize=1)
def _load_file() -> dict[str, Param]:
    raw = yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))
    out: dict[str, Param] = {}
    for key, entry in raw.items():
        missing = {"value", "unit", "source", "as_of"} - set(entry)
        if missing:
            raise ValueError(f"param {key} is missing {sorted(missing)}")
        out[key] = Param(key=key, **entry)
    return out


def all_params() -> dict[str, Param]:
    base = _load_file()
    if not _overrides:
        return base
    out = dict(base)
    for k, v in _overrides.items():
        out[k] = (
            base[k].model_copy(update={"value": v})
            if k in base
            else Param(key=k, value=v, unit="", source="test override", as_of=None)
        )
    return out


def version() -> int:
    """Changes whenever overrides change; include it in any cache key that depends on parameters."""
    return _version[0]


@contextmanager
def overrides(values: Mapping[str, Any]) -> Iterator[None]:
    """Temporarily replace parameter values (tests and sensitivity runs)."""
    saved = dict(_overrides)
    _overrides.update(values)
    _version[0] += 1
    try:
        yield
    finally:
        _overrides.clear()
        _overrides.update(saved)
        _version[0] += 1


def param(key: str) -> Param:
    try:
        return all_params()[key]
    except KeyError as exc:
        raise KeyError(f"unknown parameter {key!r}: add it to data/params.yaml") from exc


def num(key: str) -> Decimal:
    return dec(param(key).value)


def fnum(key: str) -> float:
    return float(param(key).value)


def inum(key: str) -> int:
    return int(param(key).value)


def tri(key: str, sub: str | None = None) -> Tri:
    v = param(key).value
    if sub is not None:
        v = v[sub]
    return Tri(low=float(v["low"]), likely=float(v["likely"]), high=float(v["high"]))


def table(key: str) -> dict[str, Any]:
    v = param(key).value
    if not isinstance(v, dict):
        raise TypeError(f"param {key} is not a mapping")
    return dict(v)


def items(key: str) -> list[Any]:
    v = param(key).value
    if not isinstance(v, list):
        raise TypeError(f"param {key} is not a list")
    return list(v)


def dated(key: str, on: date) -> Decimal:
    """A value that changes on dates (e.g. PWM wages): the latest entry on or before `on`."""
    tab = table(key)
    best: tuple[date, Any] | None = None
    for k, v in tab.items():
        d = date.fromisoformat(str(k))
        if d <= on and (best is None or d > best[0]):
            best = (d, v)
    if best is None:
        first = min(tab, key=lambda k: date.fromisoformat(str(k)))
        return dec(tab[first])
    return dec(best[1])


def source(key: str) -> Source:
    p = param(key)
    return Source(kind=SourceKind.PARAM, ref=key, as_of=p.as_of, note=p.source, url=p.url)


def param_fig(key: str, label: str, unit: Unit, fig_id: str | None = None) -> Figure:
    """A Figure that shows a parameter as-is (e.g. the FX rate)."""
    return Figure(id=fig_id or f"param.{key}", label=label, unit=unit, value=num(key), source=source(key))


# ------------------------------------------------------------------ frequently used, typed


def fx() -> Decimal:
    return num("fx_cny_per_sgd")


def fx_as_of() -> date | None:
    return param("fx_cny_per_sgd").as_of


def weeks_per_month() -> float:
    return fnum("weeks_per_month")


def default_seed() -> int:
    return inum("default_seed")
