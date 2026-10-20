"""Renderer and number checker (SPEC §0.3, §8.4).

Bot text holds quantities only as placeholders: {{fig:<id>}}, {{rule:<id>}}, {{topic:<id>}}.
`check_text` blocks bare digits (ASCII and full-width) and number words in English and Chinese.
`render` fills placeholders from Figures, formatted in the session language.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from tools.figures import Figure

Lang = Literal["en", "zh"]

PLACEHOLDER = re.compile(r"\{\{(fig|rule|topic):([A-Za-z0-9_.:\-]+)\}\}")

_DIGITS = re.compile(r"[0-9０-９]")
_EN_ALWAYS = (
    r"two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
    r"thousand|million|billion|twice|thrice|half|halves|double|doubled|triple|tripled|quadruple|"
    r"dozen|dozens|percent|third|thirds|quarter|quarters|tenfold|twofold|threefold"
)
_EN_WORDS = re.compile(rf"\b(?:{_EN_ALWAYS})\b", re.IGNORECASE)
_EN_UNIT_AFTER_ONE = re.compile(
    r"\b(?:one)\s+(?:month|week|year|percent|shop|dollar|yuan|thousand|hundred|million|day)s?\b",
    re.IGNORECASE,
)
_ZH_NUM = "零〇一二三四五六七八九十两百千万亿壹贰叁肆伍陆柒捌玖拾佰仟"
_ZH_QUANTITY = re.compile(
    rf"[{_ZH_NUM}]+\s*(?:成|折|倍|个月|周|星期|年|万|千|百|亿|元|块|%|％|岁|家|间|平方|杯|天|人)"
)
_ZH_IDIOMS = re.compile(r"翻番|翻倍|翻一番|过半|半数|一半|加倍|减半|对半|大半|多半|少半|倍增")


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    hits: tuple[str, ...]


def check_text(text: str) -> CheckResult:
    """Return the quantity words or digits found outside placeholders."""
    stripped = PLACEHOLDER.sub(" ", text)
    hits: list[str] = []
    for pat in (_DIGITS, _EN_WORDS, _EN_UNIT_AFTER_ONE, _ZH_QUANTITY, _ZH_IDIOMS):
        hits.extend(m.group(0) for m in pat.finditer(stripped))
    return CheckResult(ok=not hits, hits=tuple(hits))


# ------------------------------------------------------------------ formatting


def _round_money(x: Decimal) -> Decimal:
    step = Decimal("100") if abs(x) >= 10_000 else Decimal("1")
    return (x / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step


def _group(x: Decimal) -> str:
    return f"{int(x):,}"


def money(value: Decimal, currency: Literal["SGD", "CNY"], lang: Lang) -> str:
    if value < 0:
        return "-" + money(-value, currency, lang)
    if abs(value) < 100 and value != value.to_integral_value():
        # a per-cup amount: to the cent
        c = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if lang == "zh":
            return f"人民币{c}元" if currency == "CNY" else f"{c}新元"
        return f"RMB {c}" if currency == "CNY" else f"S${c}"
    v = _round_money(value)
    if lang == "zh":
        if currency == "CNY":
            if abs(v) >= 10_000:
                wan = (v / Decimal("10000")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                return f"人民币{wan.normalize():f}万"
            return f"人民币{_group(v)}元"
        if abs(v) >= 10_000:
            wan = (v / Decimal("10000")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            return f"{wan.normalize():f}万新元"
        return f"{_group(v)}新元"
    if currency == "CNY":
        if abs(v) >= 1_000_000:
            m = (v / Decimal("1000000")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return f"RMB {m.normalize():f}m"
        if abs(v) >= 10_000:
            k = (v / Decimal("1000")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return f"RMB {k}k"
        return f"RMB {_group(v)}"
    return f"S${_group(v)}"


def month_label(start: date, week: int, lang: Lang) -> str:
    d = start + timedelta(weeks=week)
    if lang == "zh":
        return f"{d.year}年{d.month}月"
    return d.strftime("%b %Y")


def week_to_month(week: int) -> Decimal:
    """Months from the start, to the nearest half month."""
    halves = (Decimal(week) / Decimal("4.345") * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return halves / 2


def fmt_value(fig: Figure, value: Decimal, lang: Lang, start: date | None) -> str:
    u = fig.unit
    if u in ("SGD", "CNY"):
        return money(value, u, lang)
    if u == "weeks":
        w = int(value.to_integral_value(rounding=ROUND_HALF_UP))
        m = week_to_month(w)
        m_txt = f"{m.normalize():f}"
        if start is not None:
            cal = month_label(start, w, lang)
            return f"第{m_txt}个月（{cal}）" if lang == "zh" else f"month {m_txt} ({cal})"
        return f"第{m_txt}个月" if lang == "zh" else f"month {m_txt}"
    if u == "months":
        halves = (value * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        m_txt = f"{(halves / 2).normalize():f}"
        return f"{m_txt}个月" if lang == "zh" else f"{m_txt} months"
    if u == "pct":
        pct = (value * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{pct.normalize():f}%"
    if u == "cups_per_day":
        n = int(value.to_integral_value(rounding=ROUND_HALF_UP))
        return f"每天{n:,}杯" if lang == "zh" else f"{n:,} cups a day"
    if u == "sqft":
        n = int(value)
        return f"{n:,}平方英尺" if lang == "zh" else f"{n:,} sq ft"
    if u == "people":
        n = int(value)
        return f"{n:,}人" if lang == "zh" else f"{n:,} people"
    if u == "score":
        return f"{int(value.to_integral_value(rounding=ROUND_HALF_UP))}/100"
    if u == "times":
        x = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{x.normalize():f}倍" if lang == "zh" else f"{x.normalize():f}x"
    n = int(value.to_integral_value(rounding=ROUND_HALF_UP))
    return f"{n:,}"


_OPENING_DATES = ("plan.open_", "goal.open_", "rep.", "funding.compare.")
_PAYBACK = ".payback"  # lvl.<level>.payback_likely / _bad (tools/unit_econ.py)


def fmt_figure(fig: Figure, lang: Lang, start: date | None = None) -> str:
    if fig.is_missing:
        if fig.unit == "weeks" and fig.id.startswith(_OPENING_DATES):
            # an opening date is missing only when that share of runs doesn't open within the horizon
            from tools import params as P

            years = round(P.inum("horizon_weeks") / 52)
            return f"{years}年内开不了业" if lang == "zh" else f"not within {years} years"
        if fig.unit == "months" and _PAYBACK in fig.id:
            # a payback month is missing only when the cash doesn't come back within the lease
            return "租约内收不回" if lang == "zh" else "not within the lease"
        return "未知" if lang == "zh" else "not known yet"
    if fig.value is not None and fig.low is None and fig.high is None:
        return fmt_value(fig, fig.value, lang, start)
    lo = fig.low if fig.low is not None else fig.value
    hi = fig.high if fig.high is not None else fig.value
    assert lo is not None and hi is not None
    if fmt_value(fig, lo, lang, start) == fmt_value(fig, hi, lang, start):
        return fmt_value(fig, lo, lang, start)
    sep = "至" if lang == "zh" else "–"
    return f"{fmt_value(fig, lo, lang, start)}{sep}{fmt_value(fig, hi, lang, start)}"


def display_map(figs: Mapping[str, Figure], lang: Lang, start: date | None = None) -> dict[str, str]:
    return {k: fmt_figure(f, lang, start) for k, f in figs.items()}


class RenderError(ValueError):
    pass


def render(
    text: str,
    figs: Mapping[str, Figure],
    lang: Lang,
    *,
    start: date | None = None,
    rule_title: Callable[[str], str] | None = None,
    topic_title: Callable[[str], str] | None = None,
) -> str:
    """Fill placeholders. An unknown figure id is an error: never show a number without a Figure."""

    def sub(m: re.Match[str]) -> str:
        kind, key = m.group(1), m.group(2)
        if kind == "fig":
            fig = figs.get(key)
            if fig is None:
                raise RenderError(f"unknown figure {key!r}")
            return fmt_figure(fig, lang, start)
        if kind == "rule":
            return rule_title(key) if rule_title else key
        return topic_title(key) if topic_title else key

    return PLACEHOLDER.sub(sub, text)
