#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate Eden Encore launcher SFX from math only.

No samples, recordings, model output, web service, or third-party audio assets are used.
Outputs are deterministic 48 kHz / 16-bit PCM WAV files.
"""
import argparse
import math
import struct
import wave
from pathlib import Path

RATE = 48_000
TAU = math.tau

def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)

def env(t, start, duration, attack=0.004, release=0.12):
    x = t - start
    if x < 0.0 or x >= duration:
        return 0.0
    return smooth(x / min(attack, duration * 0.35)) * smooth(
        (duration - x) / min(release, duration * 0.55))

def tone(t, start, duration, f0, f1, amp, pan=0.0):
    x = t - start
    if x < 0.0 or x >= duration:
        return 0.0, 0.0
    slope = (f1 - f0) / max(duration, 1e-9)
    phase = TAU * (f0 * x + 0.5 * slope * x * x)
    value = amp * env(t, start, duration) * (math.sin(phase) + 0.10 * math.sin(2 * phase + 0.35))
    return value * math.sqrt((1.0 - pan) * 0.5), value * math.sqrt((1.0 + pan) * 0.5)

def noise(t, start, duration, amp, pan=0.0, seed=1):
    if t < start or t >= start + duration:
        return 0.0, 0.0
    n = int((t - start) * RATE)
    x = (n + seed * 0x9E3779B9) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x846CA68B) & 0xFFFFFFFF
    x ^= x >> 16
    value = (((x & 0xFFFF) / 32767.5) - 1.0) * amp * env(
        t, start, duration, 0.002, duration * 0.7)
    return value * math.sqrt((1.0 - pan) * 0.5), value * math.sqrt((1.0 + pan) * 0.5)

def cue(name):
    notes, noises = [], []
    duration, stereo, peak = 0.12, False, 0.25
    if name == "focus_01":
        duration, peak, notes = 0.055, 0.18, [(0, .045, 1250, 1650, .55, 0)]
    elif name == "focus_02":
        duration, peak, notes = 0.055, 0.18, [(0, .045, 1650, 1280, .55, 0)]
    elif name.startswith("slider_"):
        base = (980, 1180, 1380)[int(name[-1]) - 1]
        duration, peak, notes = .060, .17, [(0, .052, base, base * 1.08, .52, 0)]
    elif name.startswith("toggle_"):
        base = (720, 880, 1040)[int(name[-1]) - 1]
        duration, peak, notes = .065, .19, [(0, .055, base, base * 1.35, .58, 0)]
    elif name == "select_01":
        duration, peak = .18, .27
        notes = [(0, .10, 760, 980, .58, 0), (.055, .11, 1220, 1360, .42, 0)]
    elif name == "back_01":
        duration, peak, notes = .18, .25, [(0, .15, 1080, 620, .62, 0)]
    elif name == "page_01":
        duration, stereo, peak = .20, True, .25
        notes = [(0, .17, 650, 1320, .46, -.15), (.04, .13, 880, 1540, .28, .15)]
    elif name == "open_01":
        duration, stereo, peak = .42, True, .25
        notes = [(0, .38, 300, 1120, .34, -.15), (.045, .31, 620, 1780, .24, .20)]
        noises = [(0, .30, .05, 0, 11)]
    elif name == "modal_open_01":
        duration, peak = .32, .24
        notes = [(0, .28, 420, 920, .48, 0), (.07, .18, 1040, 1320, .22, 0)]
    elif name == "modal_close_01":
        duration, peak, notes = .30, .23, [(0, .25, 1050, 430, .50, 0)]
    elif name == "error_01":
        duration, peak = .27, .27
        notes = [(0, .23, 250, 205, .52, -.06), (0, .23, 318, 270, .35, .06)]
    elif name == "saved_01":
        duration, stereo, peak = .72, True, .28
        notes = [(0, .34, 659.25, 659.25, .38, -.25),
                 (.11, .39, 830.61, 830.61, .34, 0),
                 (.22, .45, 987.77, 987.77, .32, .25)]
    elif name == "notify_01":
        duration, stereo, peak = .68, True, .27
        notes = [(0, .36, 784, 805, .38, -.18), (.16, .46, 1174.66, 1190, .33, .18)]
    elif name == "resume_01":
        duration, stereo, peak = .92, True, .31
        notes = [(0, .70, 523.25, 530, .31, -.28),
                 (.07, .72, 659.25, 668, .28, 0),
                 (.14, .72, 783.99, 792, .26, .28)]
    elif name == "launch_01":
        duration, stereo, peak = 1.20, True, .33
        notes = [(0, .55, 392, 523.25, .26, -.30),
                 (.18, .62, 523.25, 659.25, .28, 0),
                 (.38, .73, 659.25, 987.77, .27, .30)]
        noises = [(0, .55, .025, 0, 23)]
    elif name == "welcome_01":
        duration, stereo, peak = 1.95, True, .34
        notes = [(0, .66, 392, 440, .22, -.35),
                 (.22, .76, 523.25, 587.33, .24, -.10),
                 (.48, .82, 659.25, 698.46, .24, .15),
                 (.76, 1.05, 783.99, 880, .24, .35),
                 (1.00, .84, 1046.5, 1046.5, .14, 0)]
        noises = [(0, .80, .018, 0, 37)]
    else:
        raise KeyError(name)
    return duration, stereo, peak, notes, noises

NAMES = [
    "back_01", "error_01", "focus_01", "focus_02", "launch_01",
    "modal_close_01", "modal_open_01", "notify_01", "open_01", "page_01",
    "resume_01", "saved_01", "select_01", "slider_01", "slider_02", "slider_03",
    "toggle_01", "toggle_02", "toggle_03", "welcome_01",
]

def render(name, out_dir):
    duration, stereo, peak, notes, noises = cue(name)
    values = []
    count = int(duration * RATE)
    for index in range(count):
        t = index / RATE
        left = right = 0.0
        for spec in notes:
            l, r = tone(t, *spec)
            left += l
            right += r
        for spec in noises:
            l, r = noise(t, *spec)
            left += l
            right += r
        values.extend((left, right) if stereo else ((left + right) * 0.7071067811865476,))
    maximum = max((abs(x) for x in values), default=1.0)
    gain = peak / maximum if maximum else 1.0
    pcm = bytearray()
    for sample in values:
        sample = max(-1.0, min(1.0, sample * gain))
        pcm += struct.pack("<h", int(round(sample * 32767)))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2 if stereo else 1)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(pcm)
    print(f"{name}: {duration:.3f}s {'stereo' if stereo else 'mono'}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[2] / "headless/prosperoeden/ui/sounds")
    args = parser.parse_args()
    for name in NAMES:
        render(name, args.out)

if __name__ == "__main__":
    main()
