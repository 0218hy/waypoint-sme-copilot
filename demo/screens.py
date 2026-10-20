"""README visuals from the running app: docs/media/screens.jpg (eight panels) and docs/media/slider.gif.

Drives the real app through the demo journey (the same taps and unit as demo/record.py, live model), screenshots
each card as it appears, and composes them. Start a fresh demo server first (as for demo/record.py), then:

    .venv/bin/python demo/screens.py --base http://127.0.0.1:8100
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import Locator, sync_playwright


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demo.record import TEXT, Recorder  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "media"
PANELS = [
    ("map", "Where: 55 planning areas scored on public data"),
    ("cost", "What it costs: likely and if things go badly"),
    ("quote", "A quote read by AI: planted instruction ignored"),
    ("payback", "Unit economics and payback"),
    ("slider", "Set-aside slider: opening date vs home-cash risk"),
    ("compare", "Funding plans side by side"),
    ("rule", "Rule R1: the WeBank loan stays home"),
    ("goal", "The Goal tab after approval"),
]


def shot(loc: Locator) -> Image.Image:
    loc.scroll_into_view_if_needed()
    loc.page.wait_for_timeout(500)
    return Image.open(io.BytesIO(loc.screenshot())).convert("RGB")


def compose(images: dict[str, Image.Image]) -> Image.Image:
    cols, cell_w, cell_h, pad, head = 4, 900, 1100, 40, 70
    rows = (len(PANELS) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell_w + pad) + pad, rows * (cell_h + head + pad) + pad), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    for i, (key, label) in enumerate(PANELS):
        x = pad + (i % cols) * (cell_w + pad)
        y = pad + (i // cols) * (cell_h + head + pad)
        draw.text((x, y), label, fill="#0F172A", font=font)
        im = images[key].copy()
        im.thumbnail((cell_w, cell_h))
        sheet.paste(im, (x, y + head))
    return sheet


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    args = ap.parse_args()
    t = TEXT["en"]
    images: dict[str, Image.Image] = {}
    frames: list[Image.Image] = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page(viewport={"width": 1600, "height": 2200}, device_scale_factor=2)
        p.goto(args.base)
        r = Recorder(p, t)
        r.hold = lambda *a, **k: None  # type: ignore[method-assign]  # no pacing needed for stills
        r.run(lambda: p.get_by_role("button", name=t["webank"]).click(), "welcome")
        p.get_by_text(t["consent_title"]).last.wait_for()
        r.run(lambda: r.button(t["agree"]).click(), "consent")
        r.type_and_send(t["sentence"])
        r.run(lambda: r.button(t["right"]).click(), "profile")
        r.run(lambda: r.chip(t["priority"]).click(), "map")
        images["map"] = shot(p.get_by_role("group", name="Best-matched areas").last)
        r.run(lambda: r.chip(t["area"]).click(), "area")
        r.run(lambda: r.chip(t["unit"]).click(), "unit")
        images["cost"] = shot(p.get_by_role("group", name="What it costs to open").last)
        images["payback"] = shot(p.get_by_role("group", name=t["payback"]).last)
        r.run(lambda: r.chip(t["quote"]).click(), "upload prompt")
        r.run(lambda: r.button(t["sample"]).click(), "quote read")
        images["quote"] = shot(p.get_by_role("group", name=t["quote_read"]).last)
        r.run(lambda: r.button(t["accept_all"]).click(), "accept all")
        r.run(lambda: r.chip(t["looks_right"]).click(), "funding")
        card = p.get_by_role("group", name=t["slider_card"]).last
        images["slider"] = shot(card)
        thumb = p.get_by_role("slider", name=t["thumb"]).last
        thumb.scroll_into_view_if_needed()
        box = thumb.bounding_box()
        track = thumb.locator("xpath=ancestor::*[@data-orientation][1]").bounding_box() or box
        assert box is not None and track is not None
        x0, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        p.mouse.move(x0, y)
        p.mouse.down()
        path = [x0 - track["width"] * 0.15 * i / 8 for i in range(9)]
        path += [path[-1] + track["width"] * 0.30 * i / 12 for i in range(1, 13)]
        path += [path[-1] - track["width"] * 0.15 * i / 6 for i in range(1, 7)]
        for x in path:
            p.mouse.move(x, y)
            p.wait_for_timeout(350)
            frames.append(Image.open(io.BytesIO(card.screenshot())).convert("RGB"))
        p.mouse.up()
        p.wait_for_timeout(1500)
        images["compare"] = shot(p.get_by_role("group", name=t["compare"]).last)
        r.type_and_send(t["loan"])
        images["rule"] = shot(p.get_by_role("group", name=t["rule_r1"]).last)
        r.run(lambda: r.chip(t["looks_good"]).click(), "goal plan")
        r.run(lambda: r.button(t["approve"]).click(), "approve")
        p.wait_for_url("**/goal", timeout=30_000)
        p.get_by_text("On track").first.wait_for(timeout=30_000)
        p.wait_for_timeout(1500)
        images["goal"] = Image.open(io.BytesIO(p.locator("main").first.screenshot())).convert("RGB")
        b.close()
    MEDIA.mkdir(parents=True, exist_ok=True)
    compose(images).save(MEDIA / "screens.jpg", quality=82, optimize=True)
    small = []
    for f in frames:
        f = f.copy()
        f.thumbnail((900, 900))
        small.append(f.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
    small[0].save(MEDIA / "slider.gif", save_all=True, append_images=small[1:], duration=350, loop=0, optimize=True)
    print("wrote", MEDIA / "screens.jpg", "and", MEDIA / "slider.gif", f"({len(frames)} frames)")


if __name__ == "__main__":
    main()
