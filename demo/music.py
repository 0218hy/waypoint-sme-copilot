"""A soft ambient music bed, synthesized here (so royalty-free by construction): a slow four-chord pad
(Cmaj7 - Am7 - Fmaj7 - G6) with a quiet bass, gently low-passed, faded in and out.

    .venv/bin/python demo/music.py 230 demo/out/music.wav
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

RATE = 48_000
CHORD_S = 4.0
CHORDS = [  # MIDI notes
    [48, 60, 64, 67, 71],  # Cmaj7
    [45, 57, 60, 64, 67],  # Am7
    [41, 53, 57, 60, 64],  # Fmaj7
    [43, 55, 59, 62, 64],  # G6
]


def hz(midi: int) -> float:
    return float(440.0 * 2 ** ((midi - 69) / 12))


def voice(freq: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """A warm pad note: two slightly detuned sines plus a soft second harmonic, with slow vibrato."""
    t = np.arange(n) / RATE
    vib = 1 + 0.0015 * np.sin(2 * np.pi * 0.2 * t + rng.uniform(0, 6.28))
    tone = np.zeros(n)
    for detune, amp in ((0.997, 0.5), (1.003, 0.5), (2.0, 0.12)):
        tone += amp * np.sin(2 * np.pi * freq * detune * vib * t + rng.uniform(0, 6.28))
    return tone


def bed(seconds: float, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    total = int(seconds * RATE)
    out = np.zeros(total + int(CHORD_S * RATE * 2))
    step, fade = int(CHORD_S * RATE), int(1.6 * RATE)
    n = step + 2 * fade
    env = np.ones(n)
    env[:fade] = np.sin(np.linspace(0, np.pi / 2, fade)) ** 2
    env[-fade:] = np.cos(np.linspace(0, np.pi / 2, fade)) ** 2
    pos, k = 0, 0
    while pos < total:
        notes = CHORDS[k % len(CHORDS)]
        chord = sum(voice(hz(m), n, rng) * (0.55 if m < 50 else 0.3) for m in notes)
        start = max(0, pos - fade)
        out[start : start + n] += chord * env
        pos, k = pos + step, k + 1
    out = out[:total]
    a = np.exp(-2 * np.pi * 1800 / RATE)  # one-pole low-pass, softens the top end
    y = np.empty_like(out)
    acc = 0.0
    for i, x in enumerate(out):
        acc = (1 - a) * x + a * acc
        y[i] = acc
    fin, fout = int(2.0 * RATE), int(3.5 * RATE)
    y[:fin] *= np.linspace(0, 1, fin)
    y[-fout:] *= np.linspace(1, 0, fout)
    return y / (np.max(np.abs(y)) or 1) * 0.5


def write(path: Path, samples: np.ndarray) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    write(Path(sys.argv[2]), bed(float(sys.argv[1])))
