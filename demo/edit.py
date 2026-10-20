"""Cut the raw recordings into the demo video with ffmpeg.

Waits for the model are shortened, not hidden: each keeps its first moment (the typing dots) and its
last moment (the reply landing). Moments the recorder marked as a focus (the quote photo, the slider's
locked zone, a rule card, the fixes, a figure's source) get an eased zoom. The opening borrows three
marked shots as a question-led teaser. Captions come from CAPTIONS, drawn by Chromium. Narration: one WAV
per scene in demo/out/voice/<lang>/ (from demo/tts.py); scenes without one are silent.

    .venv/bin/python demo/edit.py [--silent] [--out demo/out/waypoint-demo.mp4]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

OUT = Path(__file__).parent / "out"
W, H, FPS = 1920, 1080, 30
KEEP_HEAD, KEEP_TAIL = 0.5, 0.9  # seconds of each model wait that stay in the cut
VOICE_IN, VOICE_TAIL = 0.15, 0.35  # narration starts just after the cut and leaves a short breath
MAX_SPEED = 1.5  # footage that outlasts its narration plays up to this much faster (no idle stretches)
FRAME_ZMAX = 1.75  # how far a framing (chat, details panel, email) may zoom; focus zooms go further
EASE_S = 0.5  # a camera move between framings in continuous footage
TICK = "\u2713 "
STEPS = ["Your business", "Where", "What it costs", "How to pay", "Your plan", "Goal Keeper"]
STEP_OF = {"consent": 0, "profile_typed": 0, "site": 1, "cost": 2, "slider": 3, "guard": 3, "goal_plan": 4,
           "goal_tab": 4, "goal_keeper": 5, "email": 5}
TEASER = [("q_where", 3.0), ("q_cost", 3.0), ("q_pay", 4.0)]  # shot marker, seconds borrowed

CAPTIONS = {
    "en": {
        "q_where": "Where should it go?",
        "q_cost": "What will it really cost?",
        "q_pay": "How can he pay for it safely?",
        "sign_in": "Inside the WeBank app (demo sign-in)",
        "consent": "Reads only what the card lists. Never used for credit.",
        "profile_typed": "One typed sentence fills the rest of the profile",
        "site": "Real Singapore data: SingStat, Census 2020, LTA, NEA, URA",
        "cost": "AI reads the quote (planted instruction ignored). Then payback and break-even.",
        "slider": "Set-aside slider: opening date vs home-cash risk, plans side by side.",
        "guard": "Rule R1 (law): a WeBank loan can't fund a company abroad",
        "goal_plan": "Every step in legal order. Nothing starts until the owner approves.",
        "goal_tab": "The goal, after approval",
        "goal_keeper": "Demo clock: four shops dip; flagged at week 4. Fixes come with new dates.",
        "email": "Alerts and check-ins arrive by email (demo inbox)",
        "phone_goal": "The same on a phone",
        "phone_chat": "The same on a phone",
    },
}


@dataclass
class Piece:
    start: float
    end: float
    scene: str
    focus: tuple[float, float, float, float] | None = None  # box to zoom on, then back out
    frame: tuple[tuple[float, float, float, float], str] | None = None  # (box, anchor) to look at; None: full


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duration(f: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]
    )
    return float(out)


def width_of(f: Path) -> int:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width",
         "-of", "csv=p=0", str(f)]
    )
    return int(out)


def pieces(markers: list[dict], total: float) -> list[Piece]:
    """The parts of the raw video that stay in the cut, split at scene, focus and framing boundaries."""
    waits = sorted((m["t"], m["end"]) for m in markers if "wait" in m)
    scenes = sorted((m["t"], m["scene"]) for m in markers if "scene" in m)
    focuses = sorted((m["t"], m["t"] + m["dur"], tuple(m["box"])) for m in markers if "focus" in m)
    frames = [
        (m["t"], (tuple(m["box"]), m.get("anchor", "center")) if m.get("box") else None)
        for m in sorted((m for m in markers if "frame" in m), key=lambda m: m["t"])
    ]

    def scene_at(t: float) -> str:
        cur = scenes[0][1] if scenes else ""
        for st, name in scenes:
            if st <= t:
                cur = name
        return cur

    def focus_at(t: float) -> tuple[float, float, float, float] | None:
        return next((box for a, b, box in focuses if a <= t < b), None)  # type: ignore[misc]

    def frame_at(t: float) -> tuple[tuple[float, float, float, float], str] | None:
        cur = None
        for st, spec in frames:
            if st <= t:
                cur = spec
        return cur  # type: ignore[return-value]

    keep: list[tuple[float, float]] = []
    pos = scenes[0][0] if scenes else 0.0
    for a, b in waits:
        if b - a <= KEEP_HEAD + KEEP_TAIL + 0.5:
            continue
        keep.append((pos, a + KEEP_HEAD))
        pos = b - KEEP_TAIL
    end = next((t for t, n in scenes if n == "end"), total)
    keep.append((pos, min(end, total)))
    bounds = [st for st, _ in scenes] + [t for a, b, _ in focuses for t in (a, b)] + [t for t, _ in frames]
    out: list[Piece] = []
    for a, b in keep:
        cuts = sorted({a, b, *[t for t in bounds if a < t < b]})
        for x, y in zip(cuts, cuts[1:], strict=False):
            if y - x > 0.05:
                out.append(Piece(x, y, scene_at(x), focus_at(x), frame_at(x)))
    return out


def teaser(markers: list[dict]) -> list[Piece]:
    shots = {m["shot"]: m["t"] for m in markers if "shot" in m}
    return [Piece(shots[name], shots[name] + secs, name) for name, secs in TEASER if name in shots]


CAPTION_CSS = """
* { margin: 0; } html, body { background: transparent; width: 1920px; height: 1080px; }
body { font-family: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif; }
span { position: absolute; bottom: 30px; right: 40px; font-size: 30px; padding: 12px 24px; color: #fff;
  background: rgba(22, 32, 29, 0.85); border-radius: 12px; }
.bar { position: absolute; top: 74px; left: 50%; transform: translateX(-50%); display: flex; gap: 8px;
  width: max-content; white-space: nowrap;
  padding: 8px; border-radius: 999px; background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12); }
.bar i { font-style: normal; font-size: 21px; padding: 7px 16px; border-radius: 999px; color: #8a9490; }
.bar i.done { color: #1f6f5c; } .bar i.now { background: #1f6f5c; color: #fff; font-weight: 600; }
.bar b.div { width: 2px; margin: 4px 6px; background: #c9d1ce; border-radius: 1px; }
"""


def caption_pngs(texts: dict[str, str], tmp: Path) -> dict[str, Path]:
    """Each caption (and each step-bar state) as a transparent 1920x1080 PNG, drawn by Chromium."""
    import html

    from playwright.sync_api import sync_playwright

    out: dict[str, Path] = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        for i, (key, text) in enumerate(texts.items()):
            pg.set_content(f"<style>{CAPTION_CSS}</style><span>{html.escape(text)}</span>")
            f = tmp / f"cap_{i:02d}.png"
            pg.screenshot(path=str(f), omit_background=True)
            out[key] = f
        for n in range(len(STEPS)):
            # the five journey steps; the Goal Keeper comes after them, behind a divider, once the plan is
            # approved (the narration says "five short steps")
            pills = "".join(
                f"<i class={'now' if j == n else 'done' if j < n else 'todo'}>"
                f"{TICK if j < n else ''}{html.escape(label)}</i>"
                for j, label in enumerate(STEPS[:-1])
            )
            if n == len(STEPS) - 1:
                pills += f"<b class=div></b><i class=now>{html.escape(STEPS[-1])}</i>"
            pg.set_content(f"<style>{CAPTION_CSS}</style><div class=bar>{pills}</div>")
            f = tmp / f"step_{n}.png"
            pg.screenshot(path=str(f), omit_background=True)
            out[f"step:{n}"] = f
        b.close()
    return out


View = tuple[float, float, float]  # zoom, centre x, centre y (source pixels)


def frame_view(spec: tuple[tuple[float, float, float, float], str] | None, sw: int, sh: int) -> View:
    """Where a framing looks: fit the region's width (capped), and keep its top or bottom edge in view."""
    if spec is None:
        return 1.0, sw / 2, sh / 2
    (bx, by, bw, bh), anchor = spec
    z = max(1.0, min(FRAME_ZMAX, 0.97 * sw / max(bw, 1)))
    vis = sh / z
    cy = by + vis / 2 if anchor == "top" else by + bh - vis / 2 if anchor == "bottom" else by + bh / 2
    return z, bx + bw / 2, cy


def focus_view(box: tuple[float, float, float, float], sw: int, sh: int) -> View:
    bx, by, bw, bh = box
    z = max(1.2, min(2.3, 0.86 * sw / max(bw, 1), 0.86 * sh / max(bh, 1)))
    return z, bx + bw / 2, by + bh / 2


def static_filter(v: View, sw: int, sh: int) -> str:
    z, cx, cy = v
    if z <= 1.001:
        return f"scale={W}:{H},fps={FPS}"
    w, h = sw / z, sh / z
    x, y = max(0.0, min(sw - w, cx - w / 2)), max(0.0, min(sh - h, cy - h / 2))
    return f"crop={w:.0f}:{h:.0f}:{x:.0f}:{y:.0f},scale={W}:{H},fps={FPS}"


def move_filter(a: View, b: View, seconds: float, there_and_back: bool) -> str:
    """An eased camera move from view a to view b (smoothstep), held at b; or a -> b -> a for a zoom."""
    n = max(2, round(seconds * FPS))
    e = max(1, min(round(EASE_S * FPS), n // 3 if there_and_back else n - 1))
    u = f"min(1,min(on/{e},({n - 1}-on)/{e}))" if there_and_back else f"min(1,on/{e})"
    s = f"(({u})*({u})*(3-2*({u})))"

    def lerp(p: float, q: float) -> str:
        return f"({p:.4f}+({q - p:.4f})*{s})"

    z = lerp(a[0], b[0])
    x = f"max(0,min(iw-iw/zoom,{lerp(a[1], b[1])}-iw/zoom/2))"
    y = f"max(0,min(ih-ih/zoom,{lerp(a[2], b[2])}-ih/zoom/2))"
    return f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={FPS}"


def cut(
    video: Path, parts: list[Piece], tmp: Path, caps: dict[str, Path], prefix: str, phone: bool
) -> list[tuple[str, Path]]:
    sw = width_of(video)
    sh = round(sw * 9 / 16)
    out: list[tuple[str, Path]] = []
    prev_view: View | None = None
    prev_end = -1.0
    for i, pc in enumerate(parts):
        f = tmp / f"{prefix}_{i:03d}.mp4"
        seconds = pc.end - pc.start
        base = frame_view(pc.frame, sw, sh)
        continuous = abs(prev_end - pc.start) < 0.02  # no cut between this piece and the last
        if phone:
            frame = f"scale=-2:{H},pad={W}:{H}:(ow-iw)/2:0:color=0xf6f7f8,fps={FPS}"
        elif pc.focus:
            frame = move_filter(base, focus_view(pc.focus, sw, sh), seconds, there_and_back=True)
        elif continuous and prev_view is not None and prev_view != base:
            frame = move_filter(prev_view, base, seconds, there_and_back=False)  # the camera moves
        else:
            frame = static_filter(base, sw, sh)  # after a cut, the new framing simply starts
        prev_view, prev_end = base, pc.end
        inputs = ["-ss", f"{pc.start:.2f}", "-to", f"{pc.end:.2f}", "-i", str(video)]
        graph, last, n = f"[0:v]{frame}[v0]", "v0", 1
        overlays = [caps[k] for k in (f"step:{STEP_OF[pc.scene]}" if pc.scene in STEP_OF else "", pc.scene)
                    if k in caps]
        for png in overlays:
            inputs += ["-i", str(png)]
            graph += f";[{last}][{n}:v]overlay=0:0[v{n}]"
            last, n = f"v{n}", n + 1
        run(["ffmpeg", "-y", *inputs, "-filter_complex", graph, "-map", f"[{last}]", "-an",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(f)])
        out.append((pc.scene, f))
    return out


def still(png: Path, seconds: float, out: Path) -> Path:
    run(["ffmpeg", "-y", "-loop", "1", "-t", f"{seconds:.2f}", "-i", str(png), "-vf",
         f"scale={W}:{H},fps={FPS}", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(out)])
    return out


def with_voice(video: Path, voice: Path | None, out: Path) -> Path:
    """One scene: its footage plus its narration. If the voice outlasts the footage, the last frame holds."""
    vdur = duration(video)
    need = duration(voice) + VOICE_IN + VOICE_TAIL if voice else vdur
    speed = min(MAX_SPEED, vdur / need) if voice and vdur > need * 1.08 else 1.0
    vdur /= speed
    target = max(vdur, need)
    hold = max(0.0, target - vdur)
    if voice:
        audio_in = ["-i", str(voice)]
        agraph = f"[1:a]aformat=sample_rates=48000:channel_layouts=mono,adelay={int(VOICE_IN * 1000)},apad[a]"
    else:
        audio_in = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono"]
        agraph = "[1:a]anull[a]"
    graph = f"[0:v]setpts=PTS/{speed:.4f},tpad=stop_mode=clone:stop_duration={hold:.2f}[v];{agraph}"
    run(["ffmpeg", "-y", "-i", str(video), *audio_in, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
         "-t", f"{target:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "1", str(out)])
    return out


def _stamp(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _sentences(text: str) -> list[str]:
    import re

    parts = re.split(r"(?<=[.?!\u3002\uff1f\uff01])\s*", text.strip())
    return [p for p in parts if p]


def _wrap(text: str, width: int) -> str:
    """At most two balanced lines; Latin text breaks at the space nearest the middle, Chinese anywhere."""
    if len(text) <= width:
        return text
    mid = len(text) // 2
    if " " in text:
        spaces = [i for i, ch in enumerate(text) if ch == " "]
        cut = min(spaces, key=lambda i: abs(i - mid))
        return f"{text[:cut]}\n{text[cut + 1:]}"
    return f"{text[:mid + len(text) % 2]}\n{text[mid + len(text) % 2:]}"


def write_srt(path: Path, cues: list[tuple[float, float, str]], texts: dict[str, str], width: int) -> None:
    """One subtitle per sentence, timed in proportion to its length within that scene's narration."""
    out, n = [], 0
    for start, end, scene in cues:
        sents = _sentences(texts.get(scene, ""))
        total = sum(len(x) for x in sents) or 1
        t = start
        for sent in sents:
            span = (end - start) * len(sent) / total
            n += 1
            out.append(f"{n}\n{_stamp(t)} --> {_stamp(t + span)}\n{_wrap(sent, width)}\n")
            t += span
    path.write_text("\n".join(out), encoding="utf-8")


def concat(files: list[Path], out: Path) -> Path:
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in files))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out)])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="en", choices=sorted(CAPTIONS))
    ap.add_argument("--silent", action="store_true", help="ignore demo/out/voice and cut without narration")
    ap.add_argument("--out", type=Path, default=OUT / "waypoint-demo.mp4")
    ap.add_argument("--no-music", action="store_true")
    args = ap.parse_args()
    tmp = OUT / "parts"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    voice_dir = OUT / "voice" / args.lang

    def voice(scene: str) -> Path | None:
        f = voice_dir / f"{scene}.wav"
        return f if f.exists() and not args.silent else None

    def card(name: str, minimum: float) -> tuple[str, Path]:
        v = voice(name)
        secs = max(minimum, duration(v) + VOICE_IN + VOICE_TAIL) if v else minimum
        return name, still(OUT / "cards" / f"{name}.png", secs, tmp / f"card_{name}.mp4")

    caps = caption_pngs(CAPTIONS[args.lang], tmp)
    desk = next((OUT / "desktop").glob("*.webm"))
    phone = next((OUT / "phone").glob("*.webm"))
    dmk = json.loads((OUT / "desktop_markers.json").read_text())
    pmk = json.loads((OUT / "phone_markers.json").read_text())
    clips = [card("title", 3.5)]
    clips += cut(desk, teaser(dmk), tmp, caps, "a", phone=False)
    clips += cut(desk, pieces(dmk, duration(desk)), tmp, caps, "b", phone=False)
    if voice("phone_goal") or voice("phone_chat"):  # without narration it would be a silent gap: leave it out
        clips += cut(phone, pieces(pmk, duration(phone)), tmp, caps, "c", phone=True)
    clips += [card("how", 6), card("evidence", 10), card("end", 4)]
    scenes: list[tuple[str, list[Path]]] = []  # consecutive clips of one scene share its narration
    for name, f in clips:
        if scenes and scenes[-1][0] == name:
            scenes[-1][1].append(f)
        else:
            scenes.append((name, [f]))
    voiced, cues = [], []  # cues: (start, end, scene) of each narration line, for the subtitles
    clock = 0.0
    for k, (name, files) in enumerate(scenes):
        video = files[0] if len(files) == 1 else concat(files, tmp / f"scene_{k:02d}_v.mp4")
        clip = with_voice(video, voice(name), tmp / f"scene_{k:02d}.mp4")
        v = voice(name)
        if v:
            cues.append((clock + VOICE_IN, clock + VOICE_IN + duration(v), name))
        clock += duration(clip)
        voiced.append(clip)
    joined = concat(voiced, tmp / "joined.mp4")
    total = duration(joined)
    graph = "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]"  # EBU R128 loudness for web playback
    inputs = ["-i", str(joined)]
    if not args.no_music:
        import music

        bed = tmp / "music.wav"
        music.write(bed, music.bed(total))
        inputs += ["-i", str(bed)]
        # the bed sits low and ducks further whenever the narrator speaks
        graph = ("[0:a]asplit=2[v][key];[1:a]volume=0.16[m];"
                 "[m][key]sidechaincompress=threshold=0.015:ratio=8:attack=15:release=350[md];"
                 "[v][md]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", str(args.out)])
    lines = json.loads((Path(__file__).parent / "narration.json").read_text())
    for tag, texts, width in (("en", lines[args.lang], 46), ("zh", lines["zh_subtitles"], 22)):
        write_srt(args.out.with_suffix(f".{tag}.srt"), cues, texts, width)
    print(f"wrote {args.out} ({duration(args.out):.0f} s) and .en.srt / .zh.srt")


if __name__ == "__main__":
    main()
