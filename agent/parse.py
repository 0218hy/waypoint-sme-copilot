"""Parse the owner's typed answers into slot values (code, not the model).

Handles "250k", "25万", "RMB 2.5m", "S$300,000", "两百万", "about 200 to 300k", and option synonyms
in English and Chinese.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from agent.widgets import Option

_FULLWIDTH = str.maketrans("０１２３４５６７８９．，", "0123456789.,")
_ZH_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_ZH_UNITS = {"十": 10, "百": 100, "千": 1000}
_ZH_BIG = {"万": 10_000, "亿": 100_000_000}
_NUM = re.compile(
    r"(\d+(?:\.\d+)?)\s*(k|千|thousand|m|mn|million|百万|w|万|亿)?(?![a-z])",
    re.IGNORECASE,
)
_MULT = {
    None: 1,
    "k": 1_000,
    "千": 1_000,
    "thousand": 1_000,
    "m": 1_000_000,
    "mn": 1_000_000,
    "million": 1_000_000,
    "百万": 1_000_000,
    "w": 10_000,
    "万": 10_000,
    "亿": 100_000_000,
}


def zh_number(text: str) -> int | None:
    """Parse a Chinese numeral like 两百五十万 or 三十."""
    total, section, digit = 0, 0, 0
    seen = False
    for ch in text:
        if ch in _ZH_DIGITS:
            digit = _ZH_DIGITS[ch]
            seen = True
        elif ch in _ZH_UNITS:
            section += (digit or 1) * _ZH_UNITS[ch]
            digit = 0
            seen = True
        elif ch in _ZH_BIG:
            total += (section + digit) * _ZH_BIG[ch]
            section, digit = 0, 0
            seen = True
        else:
            break
    if not seen:
        return None
    return total + section + digit


def _raw(text: str) -> list[tuple[Decimal, str | None]]:
    t = text.translate(_FULLWIDTH).replace(",", "")
    out: list[tuple[Decimal, str | None]] = []
    for m in _NUM.finditer(t):
        try:
            v = Decimal(m.group(1))
        except InvalidOperation:
            continue
        out.append((v, (m.group(2) or "").lower() or None))
    return out


def amounts(text: str) -> list[Decimal]:
    """All amounts in the text, in units (e.g. '25万' -> 250000)."""
    t = text.translate(_FULLWIDTH).replace(",", "")
    out = [v * _MULT.get(unit, 1) for v, unit in _raw(text)]
    if not out:
        for m in re.finditer(r"[零〇一二两三四五六七八九十百千万亿]+", t):
            n = zh_number(m.group(0))
            if n is not None:
                out.append(Decimal(n))
    return out


def money_range(text: str) -> tuple[Decimal, Decimal] | None:
    raw = _raw(text)
    if len(raw) >= 2 and re.search(r"-|–|to|至|到|~", text):
        (v1, u1), (v2, u2) = raw[0], raw[1]
        if u1 is None and u2 is not None:  # "200 to 300k": the second unit applies to both
            u1 = u2
        lo, hi = sorted((v1 * _MULT.get(u1, 1), v2 * _MULT.get(u2, 1)))
        return lo, hi
    vals = amounts(text)
    if not vals:
        return None
    v = vals[0]
    return v, v


def count(text: str) -> int | None:
    vals = amounts(text)
    if vals:
        return int(vals[0])
    return None


_NORMALISE = re.compile(r"[\s\-_/.,!?。！？、]+")


def _norm(s: str) -> str:
    return _NORMALISE.sub(" ", s.lower()).strip()


def match_option(
    text: str, options: list[Option], synonyms: dict[str, list[str]] | None = None, first: bool = False
) -> str | None:
    """Match free text to one option by value, label or synonym. Ambiguity returns None, unless
    `first` is set (for "which is the main one" questions), then the earliest mention wins."""
    t = _norm(text)
    if not t:
        return None
    hits: dict[str, int] = {}
    for opt in options:
        cands = [opt.value, opt.label, *(synonyms or {}).get(opt.value, [])]
        for c in cands:
            c_n = _norm(c)
            if not c_n:
                continue
            m = re.search(rf"(?:^|\s){re.escape(c_n)}(?:$|\s)", t)
            pos = m.start() if m else (t.find(c_n) if len(c_n) >= 2 else -1)
            if t == c_n:
                pos = 0
            if pos >= 0:
                hits[opt.value] = min(pos, hits.get(opt.value, pos))
    if len(hits) == 1:
        return next(iter(hits))
    if hits and first:
        return min(hits, key=lambda v: hits[v])
    return None


YES = re.compile(
    r"^(?:y|yes|yeah|yep|ok|okay|sure|go|good|fine|looks good|right|correct|是|好|好的|可以|行|对|没错|确认|嗯)\b",  # noqa: E501
    re.IGNORECASE,
)
NO = re.compile(r"^(?:n|no|nope|not now|later|不|不要|不用|算了|暂时不|没有)\b", re.IGNORECASE)


def yes_no(text: str) -> bool | None:
    t = text.strip()
    if YES.search(t):
        return True
    if NO.search(t):
        return False
    return None


# Consent to read the WeBank accounts (welcome step). A no wins over a yes ("不同意" holds "同意");
# only short replies count, so a question about consent isn't read as an answer.
CONSENT_NO = re.compile(
    r"\b(?:no|nope|not now|not yet|don'?t|do not|decline|disagree|deny|refuse|rather not|skip)\b"
    r"|不同意|不要|不用|不允许|不授权|不行|不可以|拒绝|算了|暂时不|先不|别读|别看",
    re.IGNORECASE,
)
CONSENT_YES = re.compile(
    r"^(?:yes|y|yeah|yep|ok|okay|sure|fine|go ahead|please do|sounds good|agree|agreed|accept|allow|approve|"
    r"i (?:agree|accept|consent|allow|approve)|you (?:can|may))\b"
    r"|^(?:我)?(?:同意|允许|授权|可以|好|行|确认|没问题|嗯|接受)",
    re.IGNORECASE,
)


def consent(text: str) -> bool | None:
    t = re.sub(r"^[\s,.!，。！]+|[\s,.!?，。！？]+$", "", text)
    if not t or len(t) > 40 or "?" in t or "？" in t:
        return None
    if CONSENT_NO.search(t):
        return False
    if CONSENT_YES.search(t):
        return True
    return None
