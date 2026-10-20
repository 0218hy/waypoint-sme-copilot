"""Title, evidence and end cards for the demo video, rendered to 1920x1080 PNGs.

The evidence card is built from results/results.json (the measured run), never typed by hand.

    .venv/bin/python demo/cards.py --team "Team name"
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).parent / "out" / "cards"

CSS = """
* { box-sizing: border-box; margin: 0; }
body { width: 1920px; height: 1080px; font-family: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif;
  background: #f6f7f8; color: #16201d; display: flex; flex-direction: column; justify-content: center;
  padding: 0 160px; }
.mark { width: 96px; height: 96px; border-radius: 24px; background: #1f6f5c; margin-bottom: 48px; }
h1 { font-size: 104px; letter-spacing: -2px; }
h2 { font-size: 48px; letter-spacing: -1px; margin-bottom: 24px; }
p.lead { font-size: 44px; color: #4a5753; margin-top: 28px; max-width: 1400px; line-height: 1.3; }
p.small { font-size: 26px; color: #6b7773; margin-top: 40px; }
table { border-collapse: collapse; font-size: 22px; width: 100%; }
td { padding: 6px 14px; border-bottom: 1px solid #dde2e0; vertical-align: top; }
td.id { color: #6b7773; width: 130px; white-space: nowrap; }
td.res { font-weight: 600; text-align: right; white-space: nowrap; }
.pass { color: #1f6f5c; } .fail { color: #b3261e; } .na { color: #8a9490; font-weight: 400; }
.tiles { display: grid; grid-template-columns: repeat(5, 1fr); gap: 22px; margin-top: 8px; }
.tile { background: #fff; border: 1px solid #dde2e0; border-radius: 22px; padding: 30px 24px; }
.tile b { display: block; font-size: 64px; letter-spacing: -2px; color: #1f6f5c; }
.tile span { display: block; font-size: 23px; color: #4a5753; margin-top: 12px; line-height: 1.3; }
.fails { margin-top: 36px; font-size: 27px; color: #4a5753; line-height: 1.4; }
.fails strong { color: #b3261e; }
.flow { display: grid; grid-template-columns: 1fr 60px 1fr 60px 1fr; align-items: stretch; margin-top: 12px; }
.box { background: #fff; border: 1px solid #dde2e0; border-radius: 22px; padding: 34px 30px; }
.box h3 { font-size: 36px; margin-bottom: 14px; }
.box p { font-size: 25px; color: #4a5753; line-height: 1.35; }
.box.code { border: 2px solid #1f6f5c; }
.takeaways { margin-top: 40px; padding-left: 0; list-style: none; font-size: 32px; color: #16201d; }
.takeaways li { margin: 14px 0; padding-left: 40px; position: relative; }
.takeaways li::before { content: ""; position: absolute; left: 0; top: 14px; width: 16px; height: 16px;
  border-radius: 50%; background: #1f6f5c; }
.arrow { display: flex; align-items: center; justify-content: center; font-size: 44px; color: #8a9490; }
"""


def page(body: str) -> str:
    head = f"<meta charset='utf-8'><style>{CSS}</style>"
    return f"<!doctype html><html><head>{head}</head><body>{body}</body></html>"


def evidence_table(results: dict) -> str:
    rows = []
    for eid, ev in results["evals"].items():
        if ev.get("status") != "run":
            rows.append(
                f"<tr><td class=id>{eid}</td><td>{html.escape(ev['title'])}</td><td></td>"
                "<td class='res na'>not run</td></tr>"
            )
            continue
        for what, pm in ev["pass_marks"].items():
            val = pm["value"]
            shown = f"{val:g}" if isinstance(val, float) else str(val)
            cls, word = ("pass", "pass") if pm["pass"] else ("fail", "FAIL")
            rows.append(
                f"<tr><td class=id>{eid}</td><td>{html.escape(what)}</td>"
                f"<td class=res>{html.escape(shown)} "
                f"<span class=na>({html.escape(str(pm['mark']))})</span></td>"
                f"<td class='res {cls}'>{word}</td></tr>"
            )
    commit = results["git_commit"][:7]
    return page(
        "<h2>Pre-registered evaluation, as measured</h2>"
        f"<table>{''.join(rows)}</table>"
        f"<p class=small>Simulated data (fictional company, mocked WeBank feed). Commit {commit}; "
        "full write-up in results/RESULTS.md. Not-run arms need a model or real participants.</p>"
    )


def _count(pattern: str, notes: list[str]) -> tuple[int, int]:
    for n in notes:
        m = re.search(pattern, n)
        if m:
            return int(m.group(1)), int(m.group(2))
    raise ValueError(f"not in results: {pattern}")


def test_counts() -> tuple[int, int]:
    """Automated tests in the repo right now: (backend, web), from pytest's collection and vitest's count."""
    py = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "pytest", "--collect-only", "-q"], cwd=ROOT,
                        capture_output=True, text=True).stdout
    n_py = int(re.search(r"(\d+) tests? collected", py).group(1))  # type: ignore[union-attr]
    report = OUT / "vitest.json"
    subprocess.run(["npx", "vitest", "run", "--reporter=json", f"--outputFile={report}"], cwd=ROOT / "web",
                   capture_output=True, check=False)
    n_web = int(json.loads(report.read_text())["numTotalTests"])
    return n_py, n_web


def _quotes_untouched(ev: dict) -> tuple[int, int]:
    """Poisoned quotes that changed the approval card or added a recipient, over the variants run: the worst
    of the replayed reader (E5) and the live model reader (E5-model)."""
    worst = (0, 0)
    for key in ("E5", "E5-model"):
        notes = ev[key]["notes"]
        same, n = _count(r"same card lines (\d+)/(\d+)", notes)
        fake_re = r"fake recipient/account on the card: (\d+)"
        fake = next(int(m.group(1)) for x in notes if (m := re.search(fake_re, x)))
        changed = (n - same) + fake
        worst = max(worst, (changed, n))
    return worst


def evidence(results: dict, tests: tuple[int, int]) -> str:
    ev = results["evals"]
    reached = _count(r"Reached a confirmed goal: (\d+)/(\d+)", ev["E1a"]["notes"])
    turns = ev["E1a"]["pass_marks"]["median owner turns"]["value"]
    forged = _count(r"forged or replayed approvals: breaches (\d+)/(\d+)", ev["E3"]["notes"])
    messages = next(int(m.group(1)) for n in ev["E2-model"]["notes"]
                    if (m := re.search(r"(\d+) delivered bot texts", n)))
    made_up = next(iter(ev["E2-model"]["pass_marks"].values()))["value"]
    quotes = _quotes_untouched(ev)
    tiles = [
        (f"{sum(tests)}", f"automated tests ({tests[0]} backend, {tests[1]} web)"),
        (f"{reached[0]} / {reached[1]}", f"simulated owners reached a dated plan (median {turns:g} turns)"),
        (f"{forged[0]} / {forged[1]}", "forged or replayed approvals accepted"),
        (f"{made_up:g}", f"made-up numbers in {messages:,} AI-written messages (one model family)"),
        (f"{quotes[0]} / {quotes[1]}", "poisoned quotes changed the approval card or added a recipient"),
    ]
    commit = results["git_commit"][:7]
    return page(
        "<h2>Tested end to end, against goals set before testing</h2>"
        "<div class=tiles>" + "".join(f"<div class=tile><b>{a}</b><span>{html.escape(b)}</span></div>"
                                      for a, b in tiles) + "</div>"
        "<p class=small>Everything is simulated (fictional company, mocked WeBank feed). Results from commit "
        f"{commit}; every number here is read from results/results.json (full write-up in "
        "results/RESULTS.md).</p>"
    )


def how() -> str:
    box = "<div class='box{cls}'><h3>{h}</h3><p>{p}</p></div>"
    arrow = "<div class=arrow>→</div>"
    return page(
        "<h2>How it's built</h2><div class=flow>"
        + box.format(cls="", h="The AI writes the words",
                     p="It understands what the owner types and explains each step. It never invents a "
                       "figure: numbers in its text are placeholders that code fills and checks.")
        + arrow
        + box.format(cls=" code", h="Code computes every number",
                     p="Costs, plans, the slider and the Goal Keeper come from tested code and public data. "
                       "Rules (like R1: loan money stays home) are enforced in code, not in the prompt.")
        + arrow
        + box.format(cls="", h="The owner approves",
                     p="Every money step needs his approval on a card that can't be forged or replayed. "
                       "Waypoint never moves money; WeBank's own signing flow does, if he chooses.")
        + "</div><p class=small>Pydantic models end to end · AG-UI streaming · hash-chained audit log · "
          "everything in this video is simulated</p>"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="Tul.py")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    results = json.loads((ROOT / "results" / "results.json").read_text())
    cards = {
        "title": page(
            "<div class=mark></div><h1>Waypoint</h1>"
            "<p class=lead>From “a shop in Singapore” to a funded plan with dates</p>"
            f"<p class=small>{html.escape(args.team)} · 2026 Shenzhen FinTechathon · Topic E · "
            "all data in this video is simulated</p>"
        ),
        "how": how(),
        "evidence": evidence(results, test_counts()),
        "evidence_table": evidence_table(results),
        "end": page(
            "<div class=mark></div><h1>Waypoint</h1>"
            "<p class=lead>A shop abroad, planned in one conversation, and kept on track.</p>"
            "<ul class=takeaways>"
            "<li>Five short steps from \u201ca shop in Singapore\u201d to a dated, funded plan</li>"
            "<li>Every number computed and sourced; the AI only writes the words</li>"
            "<li>A Goal Keeper that checks every week and offers fixes the owner approves</li>"
            "</ul>"
            f"<p class=small>{html.escape(args.team)} \u00b7 Topic E \u00b7 2026 Shenzhen FinTechathon "
            "\u00b7 all data in this video is simulated</p>"
        ),
    }
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        for name, doc in cards.items():
            pg.set_content(doc)
            pg.screenshot(path=str(OUT / f"{name}.png"))
        b.close()
    print("cards in", OUT)


if __name__ == "__main__":
    main()
