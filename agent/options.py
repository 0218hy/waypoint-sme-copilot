"""Quick-reply option sets (labels built by code; bands formatted by the renderer)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from agent.render import money
from agent.widgets import Option

Lang = Literal["en", "zh"]


def _o(value: str, en: str, zh: str, lang: Lang, detail: str | None = None) -> Option:
    return Option(value=value, label=zh if lang == "zh" else en, detail=detail)


def lang_options() -> list[Option]:
    return [Option(value="en", label="English"), Option(value="zh", label="中文")]


def start_option(label: str) -> list[Option]:
    return [Option(value="start", label=label)]


def shops(lang: Lang) -> list[Option]:
    return [
        _o("3", "A few (under 6)", "几家（不到六家）", lang),
        _o("10", "6 to 15", "六到十五家", lang),
        _o("20", "More than 15", "十五家以上", lang),
    ]


PROFIT_BANDS_CNY: dict[str, tuple[Decimal, Decimal]] = {
    "p1": (Decimal("50000"), Decimal("100000")),
    "p2": (Decimal("100000"), Decimal("200000")),
    "p3": (Decimal("200000"), Decimal("300000")),
    "p4": (Decimal("300000"), Decimal("500000")),
}
SPARE_BANDS_CNY: dict[str, tuple[Decimal, Decimal]] = {
    "s1": (Decimal("100000"), Decimal("200000")),
    "s2": (Decimal("200000"), Decimal("500000")),
    "s3": (Decimal("500000"), Decimal("1000000")),
    "s4": (Decimal("1000000"), Decimal("2000000")),
}
BUDGET_BANDS_SGD: dict[str, tuple[Decimal, Decimal]] = {
    "b1": (Decimal("200000"), Decimal("300000")),
    "b2": (Decimal("300000"), Decimal("450000")),
    "b3": (Decimal("450000"), Decimal("600000")),
}


def _band(lo: Decimal, hi: Decimal, cur: Literal["SGD", "CNY"], lang: Lang) -> str:
    sep = "至" if lang == "zh" else "–"
    return f"{money(lo, cur, lang)}{sep}{money(hi, cur, lang)}"


def profit(lang: Lang) -> list[Option]:
    return [Option(value=k, label=_band(lo, hi, "CNY", lang)) for k, (lo, hi) in PROFIT_BANDS_CNY.items()]


def spare(lang: Lang) -> list[Option]:
    return [Option(value=k, label=_band(lo, hi, "CNY", lang)) for k, (lo, hi) in SPARE_BANDS_CNY.items()]


def budget(lang: Lang) -> list[Option]:
    out = [Option(value=k, label=_band(lo, hi, "SGD", lang)) for k, (lo, hi) in BUDGET_BANDS_SGD.items()]
    out.append(_o("not_sure", "Not sure yet", "还不确定", lang))
    return out


def customers(lang: Lang) -> list[Option]:
    return [
        _o("young_adults", "Young adults", "年轻人", lang),
        _o("students", "Students", "学生", lang),
        _o("office_workers", "Office workers", "上班族", lang),
        _o("families", "Families", "家庭", lang),
        _o("tourists", "Tourists", "游客", lang),
    ]


CUSTOMER_SYNONYMS = {
    "young_adults": ["young", "youth", "gen z", "年轻", "年轻人", "20多岁"],
    "students": ["student", "school", "university", "学生", "大学生"],
    "office_workers": ["office", "worker", "white collar", "上班", "白领", "写字楼"],
    "families": ["family", "families", "kids", "parents", "家庭", "家长", "小孩"],
    "tourists": ["tourist", "visitor", "travel", "游客", "旅客"],
}


def window(lang: Lang) -> list[Option]:
    return [
        _o("6_12", "Within a year", "一年内", lang),
        _o("12_18", "In a year to eighteen months", "一年到一年半", lang),
        _o("18_24", "In about two years", "大约两年", lang),
        _o("no_rush", "No rush", "不着急", lang),
    ]


WINDOW_MONTHS = {"6_12": 12, "12_18": 18, "18_24": 24, "no_rush": 30}


def priority(lang: Lang) -> list[Option]:
    return [
        _o("near_customers", "Being near my kind of customer", "靠近我的目标顾客", lang),
        _o("foot_traffic", "Lots of foot traffic", "人流量大", lang),
        _o("low_rent", "Low rent", "租金低", lang),
    ]


PRIORITY_SYNONYMS = {
    "near_customers": ["customer", "near", "顾客", "客群"],
    "foot_traffic": ["traffic", "busy", "crowd", "人流", "热闹"],
    "low_rent": ["rent", "cheap", "low", "租金", "便宜"],
}


def fitout(lang: Lang) -> list[Option]:
    return [
        _o("basic", "Basic and simple", "简洁实用", lang),
        _o("standard", "Standard, like my Shenzhen shops", "标准，和深圳门店一样", lang),
        _o("premium", "Premium, a flagship look", "高端旗舰风格", lang),
    ]


def manager(lang: Lang) -> list[Option]:
    return [
        _o("hire_local", "Hire one in Singapore", "在新加坡招聘", lang),
        _o("send_own", "Send my own manager", "派自己的店长", lang),
    ]


def quotes(lang: Lang, demo: bool) -> list[Option]:
    out = [_o("no_quotes", "No quotes yet", "暂时没有报价", lang)]
    if demo:
        out.insert(0, _o("demo_quote", "Use the sample quote (demo)", "使用示例报价（演示）", lang))
    return out


def levers(lang: Lang) -> list[Option]:
    return [
        _o("looks_good", "Looks good", "可以", lang),
        _o("add_savings", "Add my savings", "加入个人积蓄", lang),
        _o("rent_free", "Ask for rent-free months", "争取免租期", lang),
        _o("partner", "A local partner?", "本地合伙人？", lang),
    ]


SAVINGS_CNY = {
    "none": Decimal("0"),
    "v2": Decimal("200000"),
    "v4": Decimal("400000"),
    "v6": Decimal("600000"),
}


def savings(lang: Lang) -> list[Option]:
    out = [_o("none", "None", "不投入", lang)]
    out += [Option(value=k, label=money(v, "CNY", lang)) for k, v in SAVINGS_CNY.items() if k != "none"]
    return out


def rent_free(lang: Lang) -> list[Option]:
    names_en = {"0": "None", "1": "One month", "2": "Two months", "3": "Three months"}
    names_zh = {"0": "不争取", "1": "一个月", "2": "两个月", "3": "三个月"}
    return [Option(value=k, label=(names_zh if lang == "zh" else names_en)[k]) for k in ("0", "1", "2", "3")]


def partner(lang: Lang) -> list[Option]:
    return [
        _o("include", "Show it with a partner", "看看有合伙人的方案", lang),
        _o("skip", "No, keep it mine", "不用，自己投资", lang),
    ]


def frequency(lang: Lang) -> list[Option]:
    return [
        _o("monthly", "Monthly", "每月", lang),
        _o("fortnightly", "Every fortnight", "每两周", lang),
        _o("weekly", "Weekly", "每周", lang),
    ]


def yes_no(
    lang: Lang, yes_en: str = "Yes", no_en: str = "No", yes_zh: str = "要", no_zh: str = "不要"
) -> list[Option]:
    return [_o("no", no_en, no_zh, lang), _o("yes", yes_en, yes_zh, lang)]


def confirm_done(lang: Lang, money: bool) -> list[Option]:
    if money:
        yes = _o("yes", "Yes, I released it myself", "是的，我本人已确认汇出", lang)
    else:
        yes = _o("yes", "Yes, it's done", "是的，已完成", lang)
    return [_o("no", "Not yet", "还没有", lang), yes]


def confirm(lang: Lang, confirm_label: str, edit_label: str) -> list[Option]:
    return [Option(value="confirm", label=confirm_label), Option(value="edit", label=edit_label)]


def cost_adjust(lang: Lang, level: str, manager: str) -> list[Option]:
    out = [_o("looks_right", "Looks right", "没问题", lang)]
    for v, en, zh in (("basic", "Basic fit-out", "简洁装修"), ("standard", "Standard fit-out", "标准装修"),
                      ("premium", "Premium fit-out", "高端装修")):
        if v != level:
            out.append(_o(v, en, zh, lang))
    if manager == "hire_local":
        out.append(_o("send_own", "Send my own manager", "派自己的店长", lang))
    else:
        out.append(_o("hire_local", "Hire a manager in Singapore", "在新加坡招店长", lang))
    out.append(_o("add_quote", "Add a contractor quote", "添加装修报价", lang))
    return out


def goal_extras(lang: Lang, embedded: bool, transfer_on: bool) -> list[Option]:
    out = [_o("change_reminders", "Change reminders", "修改提醒频率", lang),
           _o("amounts_on", "Show amounts in emails", "邮件里显示金额", lang)]
    if embedded:
        out.append(_o("no_transfer", "No monthly transfer", "不设自动转存", lang) if transfer_on
                   else _o("add_transfer", "Also set up the monthly transfer", "同时设置每月自动转存", lang))
    return out
