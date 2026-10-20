"""Synthesize the narration (demo/narration.json), one WAV per scene, with ElevenLabs or Azure AI Speech.

Keys come from the environment and are sent only to that provider, never printed:
- ElevenLabs: ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID (your own voice's ID, from its page in Voices).
- Azure: AZURE_SPEECH_KEY (or AZURE_SPEECH_TOKEN) and AZURE_SPEECH_REGION.
`--provider auto` (the default) uses ElevenLabs when both of its variables are set, else Azure.

    .venv/bin/python demo/tts.py [--provider elevenlabs] [--speed 1.0] [--pitch 1.5]
"""

from __future__ import annotations

import argparse
import html
import http.client
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "out" / "voice"


def azure(text: str, voice: str, lang: str, rate: str, key: str, region: str) -> bytes:
    locale = {"en": "en-US", "zh": "zh-CN"}[lang]
    ssml = (
        f"<speak version='1.0' xml:lang='{locale}' xmlns='http://www.w3.org/2001/10/synthesis'>"
        f"<voice name='{voice}'><prosody rate='{rate}'>{html.escape(text)}</prosody></voice></speak>"
    )
    req = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml.encode(),
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-48khz-16bit-mono-pcm",
            "User-Agent": "waypoint-demo",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return bytes(r.read())


def elevenlabs(
    text: str, voice_id: str, key: str, model: str, speed: float, previous: str, following: str,
    seed: int | None = None,
) -> bytes:
    """One line as WAV. The neighbouring lines go along as context, so delivery flows across scenes, and
    one seed for every line keeps the takes alike."""
    body = {
        "text": text,
        "model_id": model,
        "seed": seed,
        # v3 takes no neighbouring-line context (it reads each line on its own); earlier models do
        "previous_text": (previous or None) if not model.startswith("eleven_v3") else None,
        "next_text": (following or None) if not model.startswith("eleven_v3") else None,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.0,
                           "use_speaker_boost": True, "speed": speed},
    }
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
        data=json.dumps({k: v for k, v in body.items() if v is not None}).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        mp3 = r.read()
    with tempfile.TemporaryDirectory() as d:  # the edit expects WAV
        src, dst = Path(d) / "line.mp3", Path(d) / "line.wav"
        src.write_bytes(mp3)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ar", "48000", "-ac", "1", str(dst)],
                       check=True)
        return dst.read_bytes()


def elevenlabs_one_take(
    lines: list[tuple[str, str]], voice_id: str, key: str, model: str, speed: float, seed: int | None,
    out: Path, language: str = "en",
) -> None:
    """The whole script in one request, so the voice stays the same throughout; then each line is cut out
    at its own start and end, from the per-character timestamps ElevenLabs returns with the audio."""
    import base64

    joiner = "\n\n"
    full = joiner.join(text for _, text in lines)
    body = {"text": full, "model_id": model, "seed": seed, "language_code": language,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.0,
                               "use_speaker_boost": True, "speed": speed}}
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128",
        data=json.dumps(body).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json"},
    )
    for attempt in range(3):  # a long response can be cut off in transit; try again
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                res = json.loads(r.read())
            break
        except (http.client.IncompleteRead, ConnectionError, TimeoutError):
            if attempt == 2:
                raise
    al = res.get("alignment") or res["normalized_alignment"]
    chars = al["characters"]
    starts, ends = al["character_start_times_seconds"], al["character_end_times_seconds"]
    if "".join(chars) != full:
        raise SystemExit("ElevenLabs' timestamps don't line up with the script; voice the lines separately.")
    take = out / "_full_take.wav"
    with tempfile.TemporaryDirectory() as d:
        mp3 = Path(d) / "take.mp3"
        mp3.write_bytes(base64.b64decode(res["audio_base64"]))
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ar", "48000", "-ac", "1", str(take)],
                       check=True)
    pos = 0
    spans = []
    for _, text in lines:
        spans.append((starts[pos], ends[pos + len(text) - 1]))
        pos += len(text) + len(joiner)
    for i, ((scene, _), (a, b)) in enumerate(zip(lines, spans, strict=True)):
        lo = max(0.0, a - 0.06)  # a breath of room either side, never into the neighbouring line
        hi = min(b + 0.18, spans[i + 1][0] - 0.02) if i + 1 < len(spans) else b + 0.3
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(take), "-ss", f"{lo:.3f}",
                        "-to", f"{hi:.3f}", "-af", "afade=t=in:d=0.02,areverse,afade=t=in:d=0.04,areverse",
                        str(out / f"{scene}.wav")], check=True)


def tighten_pauses(wav: Path, max_pause: float) -> None:
    """Shorten any pause inside a line to at most max_pause seconds (a long take drifts into long pauses);
    the speech itself is untouched."""
    if max_pause <= 0:
        return
    tmp = wav.with_suffix(".tight.wav")
    af = (f"silenceremove=start_periods=0:stop_periods=-1:stop_duration={max_pause}:"
          f"stop_threshold=-42dB:stop_silence={max_pause}")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", af, str(tmp)], check=True)
    tmp.replace(wav)


def shift_pitch(wav: Path, semitones: float) -> None:
    """Raise (or lower) the voice without changing its length: resample up, then slow back to time."""
    if not semitones:
        return
    k = 2 ** (semitones / 12)
    tmp = wav.with_suffix(".pitch.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af",
                    f"asetrate=48000*{k:.6f},aresample=48000,atempo={1 / k:.6f}", "-ac", "1", str(tmp)],
                   check=True)
    tmp.replace(wav)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="en")
    ap.add_argument("--provider", default="auto", choices=["auto", "elevenlabs", "azure"])
    ap.add_argument("--voice", default="en-US-AndrewMultilingualNeural", help="Azure voice name")
    ap.add_argument("--rate", default="+12%", help="Azure speaking rate")
    ap.add_argument("--model", default="eleven_v3", help="ElevenLabs model (v3 chosen by ear for the demo)")
    ap.add_argument("--speed", type=float, default=1.1, help="ElevenLabs speed, 0.7 to 1.2")
    ap.add_argument("--pitch", type=float, default=0.0, help="semitones up (negative: down), any provider")
    ap.add_argument("--seed", type=int, default=707, help="ElevenLabs seed for every line (707: by ear)")
    ap.add_argument("--per-line", action="store_true", help="ElevenLabs: one request per line, not one take")
    ap.add_argument("--max-pause", type=float, default=0.3, help="longest pause kept inside a line (0: off)")
    args = ap.parse_args()
    el_key, el_voice = os.environ.get("ELEVENLABS_API_KEY"), os.environ.get("ELEVENLABS_VOICE_ID")
    az_key = os.environ.get("AZURE_SPEECH_KEY") or os.environ.get("AZURE_SPEECH_TOKEN")
    az_region = os.environ.get("AZURE_SPEECH_REGION")
    provider = args.provider
    if provider == "auto":
        provider = "elevenlabs" if el_key and el_voice else "azure"
    if provider == "elevenlabs" and not (el_key and el_voice):
        sys.exit("Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in the environment.")
    if provider == "azure" and not (az_key and az_region):
        sys.exit("Set AZURE_SPEECH_KEY (or AZURE_SPEECH_TOKEN) and AZURE_SPEECH_REGION in the environment.")
    lines = json.loads((HERE / "narration.json").read_text())[args.lang]
    out = OUT / args.lang
    out.mkdir(parents=True, exist_ok=True)
    spoken = [t for t in lines.values() if t]
    for scene, text in lines.items():
        if not text:
            (out / f"{scene}.wav").unlink(missing_ok=True)
    if provider == "elevenlabs" and not args.per_line:
        voiced = [(scene, text) for scene, text in lines.items() if text]
        elevenlabs_one_take(voiced, el_voice or "", el_key or "", args.model, args.speed, args.seed, out,
                            language=args.lang)
        for scene, _ in voiced:
            tighten_pauses(out / f"{scene}.wav", args.max_pause)
            shift_pitch(out / f"{scene}.wav", args.pitch)
        print(f"voice (elevenlabs, one take of {len(voiced)} lines) in", out)
        return
    for scene, text in lines.items():
        target = out / f"{scene}.wav"
        if not text:
            target.unlink(missing_ok=True)
            continue
        if provider == "elevenlabs":
            i = spoken.index(text)
            prev = spoken[i - 1] if i > 0 else ""
            nxt = spoken[i + 1] if i + 1 < len(spoken) else ""
            audio = elevenlabs(
                text, el_voice or "", el_key or "", args.model, args.speed, prev, nxt, args.seed
            )
        else:
            audio = azure(text, args.voice, args.lang, args.rate, az_key or "", az_region or "")
        target.write_bytes(audio)
        shift_pitch(target, args.pitch)
        print(f"{scene}: {len(text.split())} words", flush=True)
    print(f"voice ({provider}) in", out)


if __name__ == "__main__":
    main()
