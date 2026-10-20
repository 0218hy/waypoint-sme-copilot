"""Record the demo journey against a running Waypoint (the live model writes every reply).

Drives the real app in Chromium and records one continuous video per viewport, plus markers.json:
each scene's start time and every wait for the model, so the edit can cut dead time without faking
anything on screen. Start the dedicated server first (launch config "waypoint-demo", port 8100, fresh DB).

    .venv/bin/python demo/record.py --base http://127.0.0.1:8100 --lang en
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import Locator, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

OUT = Path(__file__).parent / "out"
# The page lays out as a 1600x900 window but is drawn 1.6x larger in a 2560x1440 one, so every recorded
# pixel is real and the edit's zooms stay sharp (Playwright records CSS pixels, not device pixels).
DESKTOP = {"width": 2560, "height": 1440}
PAGE_ZOOM = 1.6
PHONE = {"width": 390, "height": 844}

# A visible pointer and a ripple on each click: headless recordings have no cursor, so taps look causeless.
POINTER_JS = """
(() => {
  const css = (el, o) => Object.assign(el.style, o);
  const z = () => parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
  const mount = () => {
    if (document.getElementById('__wp_pointer')) return;
    const dot = document.createElement('div');
    dot.id = '__wp_pointer';
    css(dot, {position: 'fixed', left: '-40px', top: '-40px', width: '22px', height: '22px',
      margin: '-11px 0 0 -11px', borderRadius: '50%', background: 'rgba(31,111,92,.28)',
      border: '2px solid rgba(31,111,92,.95)', boxShadow: '0 1px 4px rgba(0,0,0,.25)',
      pointerEvents: 'none', zIndex: 2147483647, transition: 'transform .08s'});
    document.documentElement.appendChild(dot);
    const at = e => ({left: e.clientX / z() + 'px', top: e.clientY / z() + 'px'});
    addEventListener('mousemove', e => css(dot, at(e)), true);
    addEventListener('mousedown', e => {
      dot.style.transform = 'scale(.7)';
      const r = document.createElement('div');
      css(r, {position: 'fixed', ...at(e), width: '16px', height: '16px',
        margin: '-8px 0 0 -8px', borderRadius: '50%', border: '3px solid rgba(31,111,92,.9)',
        pointerEvents: 'none', zIndex: 2147483646, transition: 'all .55s ease-out'});
      document.documentElement.appendChild(r);
      const grow = {width: '70px', height: '70px', margin: '-35px 0 0 -35px', opacity: '0'};
      requestAnimationFrame(() => css(r, grow));
      setTimeout(() => r.remove(), 650);
    }, true);
    addEventListener('mouseup', () => { dot.style.transform = 'scale(1)'; }, true);
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', mount); else mount();
})();
"""
RUN_TIMEOUT = 180_000
HOLD_SCALE = 0.6  # idle holds between actions; zoom holds keep their full length
MAILPIT = "http://127.0.0.1:8025/"

TEXT = {
    "en": {
        "sentence": (
            "Mostly office workers. My budget is about S$300k to S$450k, and I'd like to open within a year."
        ),
        "loan": "Can I just use my WeBank loan to pay the Singapore deposit?",
        "agree": "Agree",
        "right": "That's right",
        "priority": "Being near my kind of customer",
        "quote": "Add a contractor quote",
        "sample": "Use the sample quote photo",
        "accept_all": re.compile(r"^Accept all lines"),
        "looks_right": "Looks right",
        "looks_good": "Looks good",
        "approve": "Approve",
        "thumb": "Share of monthly profit to set aside",
        "answers": "Answers",
        "dip": "Sales dip at four shops",
        "none": "Nothing unusual",
        "checkin_subject": re.compile(r"Your plan (moved|this week)"),  # the alert, or a check-in
        "skip8": "Skip ahead 8 weeks",
        "see_fixes": "See fixes",
        "pick_fix": "Choose this fix",
        "webank": "Demo: sign in with WeBank",
        "consent_title": "Read your WeBank accounts?",
        "quote_read": "What we read from your quote",
        "slider_card": "Set aside from monthly profit",
        "rule_r1": "Loan money stays home",
        "area": "Tampines",
        "unit": re.compile(r"^Tampines 1\b"),
        "payback": "Unit economics & payback",
        "compare": "Compare funding plans",
        "repairs": "Ways to get back on track",
        "source": re.compile(r"Where is this from\?"),
        "rail": "Your journey",
        "canvas": "Details",
    },
}


class Recorder:
    def __init__(self, page: Page, t: dict[str, Any]) -> None:
        self.page, self.t, self.t0 = page, t, time.monotonic()
        self.markers: list[dict[str, Any]] = []

    def now(self) -> float:
        return round(time.monotonic() - self.t0, 2)

    def scene(self, name: str) -> None:
        self.markers.append({"t": self.now(), "scene": name})
        print(f"[{self.now():7.1f}s] {name}", flush=True)

    def hold(self, seconds: float, exact: bool = False) -> None:
        self.page.wait_for_timeout(int(seconds * (1 if exact else HOLD_SCALE) * 1000))

    def run(self, action: Callable[[], None], label: str) -> None:
        """Do something that starts an agent run and wait until the chat says the run has finished."""
        start = self.now()
        with self.page.expect_request(
            lambda r: "/api/agui" in r.url and r.method == "POST", timeout=60_000
        ):
            action()
        try:  # the flag flips a render after the request; don't read a stale "false"
            self.page.wait_for_selector("html[data-agent-running='true']", state="attached", timeout=3_000)
        except PlaywrightTimeout:
            pass
        self.page.wait_for_selector("html[data-agent-running='false']", state="attached", timeout=RUN_TIMEOUT)
        self.hold(1.2)  # let the last card settle
        self.markers.append({"t": start, "end": self.now(), "wait": label})

    def frame(self, where: str) -> None:
        """Where the camera should look from now on: "chat" (the step list and conversation, anchored at the
        newest message), "canvas" (the details panel, from its top), "email" (the open message) or "full".
        Boxes are measured on screen now, in pixels of the recorded frame."""
        p, box, anchor = self.page, None, "center"
        rail = p.get_by_role("complementary", name=self.t["rail"])
        canvas = p.get_by_role("complementary", name=self.t["canvas"])
        if where == "chat" and rail.count() and canvas.count():
            r, c = rail.first.bounding_box(), canvas.first.bounding_box()
            if r and c:
                box = {"x": r["x"], "y": r["y"], "width": c["x"] - r["x"], "height": r["height"]}
                anchor = "bottom"
        elif where == "canvas" and canvas.count():
            box, anchor = canvas.first.bounding_box(), "top"
        elif where == "email" and p.locator("iframe").count():
            box, anchor = p.locator("iframe").first.bounding_box(), "top"
        rect = None if box is None else [box["x"], box["y"], box["width"], box["height"]]
        self.markers.append({"t": self.now(), "frame": where, "anchor": anchor, "box": rect})

    def shot(self, name: str) -> None:
        """A moment the opening teaser can borrow (its footage stays in the main cut too)."""
        self.markers.append({"t": self.now(), "shot": name})

    def focus(
        self, target: Locator | dict[str, float], seconds: float, name: str, height: float | None = None
    ) -> None:
        """Hold on a region the edit zooms into (box in pixels of the recorded 2560x1440 frame)."""
        box = target if isinstance(target, dict) else target.bounding_box()
        if box is None:
            self.hold(seconds, exact=True)
            return
        h = min(box["height"], height) if height else box["height"]
        self.markers.append({"t": self.now(), "focus": name, "dur": seconds,
                             "box": [box["x"], box["y"], box["width"], h]})
        self.hold(seconds, exact=True)

    def click(self, target: Locator) -> None:
        """Glide the pointer to the target, then click: the viewer sees what was tapped."""
        target.scroll_into_view_if_needed()
        box = target.bounding_box()
        if box is not None:
            self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=18)
            self.hold(0.25)
        target.click()

    # --- helpers
    def chip(self, name: str | None = None) -> Locator:
        group = self.page.get_by_role("group", name=self.t["answers"]).last
        return group.get_by_role("button").first if name is None else group.get_by_role("button", name=name)

    def button(self, name: str | re.Pattern[str]) -> Locator:
        return self.page.get_by_role("button", name=name).last

    def type_and_send(self, text: str) -> None:
        box = self.page.locator("#composer")
        self.click(box)
        box.press_sequentially(text, delay=16)
        self.hold(0.4)
        self.run(lambda: box.press("Enter"), f"typed: {text[:30]}")


def tab(p: Page, name: str) -> None:
    if not p.url.endswith(f"#/{name}"):
        p.evaluate(f"location.hash = '#/{name}'")
        p.wait_for_timeout(800)


def journey(r: Recorder) -> None:
    p, t = r.page, r.t
    r.scene("sign_in")
    r.hold(2.5)
    r.run(lambda: r.click(p.get_by_role("button", name=t["webank"])), "welcome")
    p.get_by_text(t["consent_title"]).last.wait_for()
    r.frame("chat")
    r.hold(2.5)

    r.scene("consent")
    r.run(lambda: r.click(r.button(t["agree"])), "profile from feed")
    r.hold(3)

    r.scene("profile_typed")
    r.type_and_send(t["sentence"])
    r.hold(3)
    r.run(lambda: r.click(r.button(t["right"])), "profile confirmed")
    r.hold(2)

    r.scene("site")
    r.run(lambda: r.click(r.chip(t["priority"])), "map")
    r.shot("q_where")
    r.frame("canvas")  # the map
    r.hold(4)
    r.frame("chat")
    r.hold(1)
    r.run(lambda: r.click(r.chip(t["area"])), "area")  # the area and unit the committed demo run uses
    r.hold(1.5)
    r.frame("canvas")  # the units, each with its break-even
    r.hold(3)
    r.frame("chat")
    r.hold(1)
    r.scene("cost")  # the cost card streams in during this turn, so the cost scene starts with the tap
    r.run(lambda: r.click(r.chip(t["unit"])), "unit")
    r.shot("q_cost")
    r.frame("canvas")  # the cost card: likely and bad case
    r.hold(3)
    r.hold(2)
    payback = p.get_by_role("group", name=t["payback"]).last
    if payback.count():  # the unit-economics and payback card, in the chat
        r.frame("chat")
        payback.scroll_into_view_if_needed()
        r.hold(0.6, exact=True)
        r.focus(payback, 5, "payback", height=620)
    r.frame("chat")
    r.hold(1)
    r.run(lambda: r.click(r.chip(t["quote"])), "upload prompt")
    r.hold(2)
    r.run(lambda: r.click(r.button(t["sample"])), "quote read")
    r.hold(1)
    photo = p.get_by_role("group", name=t["quote_read"]).last.locator("img").first
    photo.scroll_into_view_if_needed()
    r.hold(0.5)
    r.focus(photo, 5, "quote_photo")
    r.run(lambda: r.click(r.button(t["accept_all"])), "accept all")
    r.hold(2)
    r.frame("full")
    r.hold(0.8)
    # every figure says where it comes from: open one source note on the cost card
    src = p.get_by_role("button", name=t["source"]).first
    r.click(src)
    r.hold(0.6)
    pop = p.get_by_role("dialog").last
    a, b = src.bounding_box(), pop.bounding_box()
    if a and b:
        x0, y0 = min(a["x"], b["x"]), min(a["y"], b["y"])
        x1 = max(a["x"] + a["width"], b["x"] + b["width"])
        y1 = max(a["y"] + a["height"], b["y"] + b["height"])
        r.focus({"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}, 4.5, "source_note")
    else:
        r.hold(4.5)
    p.keyboard.press("Escape")
    r.hold(1.5)
    r.frame("chat")
    r.hold(1)
    r.scene("slider")
    r.run(lambda: r.click(r.chip(t["looks_right"])), "funding")
    r.frame("canvas")  # the slider with its locked zone and the chart
    r.hold(2)

    thumb = p.get_by_role("slider", name=t["thumb"]).last
    thumb.scroll_into_view_if_needed()
    box = thumb.bounding_box()
    assert box is not None
    track = thumb.locator("xpath=ancestor::*[@data-orientation][1]").bounding_box() or box
    x0, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    card = p.get_by_role("group", name=t["slider_card"]).last.bounding_box()
    p.mouse.move(x0, y, steps=18)
    r.hold(0.4)
    r.shot("q_pay")  # the opening borrows the drag: the slider, its locked zone and the dates moving
    if card:  # zoom on the share, the track with its locked zone, and the warning while dragging
        r.markers.append({"t": r.now(), "focus": "slider_lock", "dur": 5.0,
                          "box": [card["x"], card["y"], card["width"], 290]})
    p.mouse.down()
    for x in [x0 - track["width"] * 0.12 * i / 10 for i in range(1, 11)]:  # down a little, then past the wall
        p.mouse.move(x, y)
        r.hold(0.12)
    r.hold(1.2)
    x1 = x0 - track["width"] * 0.12
    for x in [x1 + track["width"] * 0.30 * i / 14 for i in range(1, 15)]:
        p.mouse.move(x, y)
        r.hold(0.12)
    r.hold(1.0)
    p.mouse.up()  # released at the limit: same share, so no new turn; the live preview did the work
    r.hold(3)
    compare = p.get_by_role("group", name=t["compare"]).last
    if compare.count():  # the funding plans side by side, under the slider's result
        r.frame("chat")
        compare.scroll_into_view_if_needed()
        r.hold(0.6, exact=True)
        r.focus(compare, 5, "compare", height=620)

    r.scene("guard")
    r.frame("chat")
    r.hold(1)
    r.type_and_send(t["loan"])
    r.hold(0.5)
    rule = p.get_by_role("group", name=t["rule_r1"]).last
    rule.scroll_into_view_if_needed()
    r.hold(0.6, exact=True)
    r.focus(rule, 5, "rule_r1")

    r.scene("goal_plan")
    r.run(lambda: r.click(r.chip(t["looks_good"])), "goal plan")
    r.frame("canvas")  # every step in the legal order
    r.hold(3.5)
    r.frame("chat")  # the approval card
    r.hold(2)
    r.scene("goal_tab")
    r.run(lambda: r.click(r.button(t["approve"])), "approve")
    r.frame("full")
    r.hold(2)

    p.wait_for_url(re.compile(r".*/goal$"), timeout=30_000)
    p.get_by_text(re.compile(r"On track|At risk|Off track")).first.wait_for(timeout=30_000)
    r.hold(4)
    p.mouse.wheel(0, 500)
    r.hold(3)
    p.mouse.wheel(0, -500)

    r.scene("goal_keeper")
    tab(p, "chat")
    r.frame("chat")
    r.hold(1.5)
    p.locator("select").first.select_option(label=t["dip"])
    r.hold(1)
    with p.expect_response(lambda x: "/api/demo/advance" in x.url, timeout=RUN_TIMEOUT):
        r.click(r.button(t["skip8"]))
    r.hold(1.5)
    tab(p, "goal")
    r.frame("full")
    r.hold(3)  # the first check-in after the dip: status slips
    fixes = p.get_by_role("button", name=t["see_fixes"]).first
    for _ in range(2):  # the detector waits for a run of weak weeks before it alerts
        if fixes.is_visible():
            break
        tab(p, "chat")
        p.locator("select").first.select_option(label=t["none"])
        with p.expect_response(lambda x: "/api/demo/advance" in x.url, timeout=RUN_TIMEOUT):
            r.click(r.button(t["skip8"]))
        tab(p, "goal")
        r.frame("full")
        r.hold(2.5)
    fixes.wait_for(timeout=30_000)
    r.hold(4)
    r.run(lambda: r.click(p.get_by_role("button", name=t["see_fixes"]).first), "repairs")
    tab(p, "chat")
    r.hold(1.5, exact=True)  # the chat re-mounts and scrolls to the end; measure once it has settled
    r.frame("chat")
    fixes_card = p.get_by_role("group", name=t["repairs"]).last
    fixes_card.scroll_into_view_if_needed()
    r.hold(0.6, exact=True)
    r.focus(fixes_card, 5, "repairs", height=520)
    r.run(lambda: r.click(r.button(t["pick_fix"])), "revision card")
    r.hold(3)
    r.run(lambda: r.click(r.button(t["approve"])), "revision approved")
    r.hold(4)

    r.scene("email")
    p.goto(MAILPIT)
    r.frame("full")
    first = p.locator("a.message", has_text=t["checkin_subject"]).first
    first.wait_for(timeout=30_000)
    r.hold(2)
    r.click(first)
    r.hold(0.8, exact=True)
    r.frame("email")
    r.hold(7)
    r.scene("end")


def phone(r: Recorder, base: str) -> None:
    p = r.page
    r.scene("phone_goal")
    r.hold(4)
    p.mouse.wheel(0, 700)
    r.hold(3)
    r.scene("phone_chat")
    p.goto(base + "/#/chat")
    r.hold(2)
    p.mouse.wheel(0, -2500)
    r.hold(4)
    r.scene("end")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--lang", default="en", choices=sorted(TEXT))
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    t = TEXT[args.lang]
    for old in ("desktop", "phone"):
        shutil.rmtree(OUT / old, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        ctx = browser.new_context(
            viewport=DESKTOP, device_scale_factor=1, locale="en-SG" if args.lang == "en" else "zh-CN",
            record_video_dir=str(OUT / "desktop"), record_video_size=DESKTOP,
        )
        ctx.add_init_script(f"document.documentElement.style.zoom = '{PAGE_ZOOM}';")
        ctx.add_init_script(POINTER_JS)
        page = ctx.new_page()
        page.set_default_timeout(45_000)
        rec = Recorder(page, t)
        page.goto(args.base + "/")
        try:
            journey(rec)
        finally:
            (OUT / "desktop_markers.json").write_text(json.dumps(rec.markers, indent=1))
            page.screenshot(path=str(OUT / "desktop_last.png"))
            state = ctx.storage_state()
            ctx.close()
        ctx = browser.new_context(
            viewport=PHONE, device_scale_factor=2, is_mobile=True, has_touch=True, storage_state=state,
            record_video_dir=str(OUT / "phone"), record_video_size=PHONE,
        )
        page = ctx.new_page()
        rec = Recorder(page, t)
        page.goto(args.base + "/#/goal")
        try:
            phone(rec, args.base)
        finally:
            (OUT / "phone_markers.json").write_text(json.dumps(rec.markers, indent=1))
            ctx.close()
        browser.close()
    print("videos and markers in", OUT)


if __name__ == "__main__":
    main()
