#!/usr/bin/env python3
"""Inspect existing FC27/Eden Encore text logs for freeze hypotheses.

This does not infer guest progress from a 30 FPS counter. It correlates sampled
guest program counters, per-core CPU-time progress, release present gaps and
optional HLE timings. Samples are diagnostic clues, not proof of causality.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

PATTERN = re.compile(r"([a-zA-Z_][a-zA-Z_0-9]*)=([^\s]+)")

def attributes(line: str) -> dict[str, str]:
    return dict(PATTERN.findall(line))

def number(fields: dict[str, str], key: str, fallback: float = 0) -> float:
    try:
        return float(fields.get(key, fallback))
    except ValueError:
        return fallback

def analyze(lines: list[str], repeated_pc_seconds: float = 10.0) -> dict:
    frames: list[dict] = []
    pc_points: dict[str, list[dict]] = {}
    hle: list[dict] = []
    queue: list[dict] = []
    for line in lines:
        if "EDEN_GAME_FRAME " in line or "EDEN_DEV_FRAME " in line:
            f = attributes(line)
            frames.append({"fps": number(f, "fps"), "worst_ms": number(f, "worst_ms"),
                           "seconds": number(f, "seconds"), "frames": number(f, "frames")})
        if "EDEN_PERF_CPU_POINT " in line:
            f = attributes(line)
            if "core" in f and "mono_ns" in f and "pc" in f:
                pc_points.setdefault(f["core"], []).append({
                    "mono_ns": number(f, "mono_ns"), "pc": f["pc"].lower().removeprefix("0x"),
                    "cpu_ns": number(f, "cpu_ns", -1), "svc": f.get("svc", "?")})
        if "EDEN_DEV_HLE " in line:
            f = attributes(line)
            hle.append({"service": f.get("service", "?"), "cmd": f.get("cmd", "?"),
                        "calls": number(f, "calls"), "ns": number(f, "ns")})
        if "EDEN_DEV_QUEUE " in line:
            f = attributes(line)
            queue.append({"idle_ns": number(f, "idle_ns"),
                          "dispatch_ns": number(f, "dispatch_ns")})
    spans: list[dict] = []
    for core, points in pc_points.items():
        points.sort(key=lambda p: p["mono_ns"])
        start = 0
        # Consecutive observations only. Repeated PCs alone may be legitimate.
        for end in range(1, len(points) + 1):
            boundary = end == len(points) or points[end]["pc"] != points[start]["pc"]
            if not boundary:
                continue
            first, last = points[start], points[end - 1]
            seconds = (last["mono_ns"] - first["mono_ns"]) / 1_000_000_000
            if end - start >= 3 and seconds >= repeated_pc_seconds:
                cpu_delta = last["cpu_ns"] - first["cpu_ns"] if first["cpu_ns"] >= 0 and last["cpu_ns"] >= 0 else None
                spans.append({"core": core, "guest_pc": first["pc"], "samples": end - start,
                              "seconds": round(seconds, 3), "cpu_delta_ns": cpu_delta,
                              "hypothesis": "busy_guest_loop" if cpu_delta and cpu_delta > 0
                              else "wait_or_unknown"})
            start = end
    gaps = [{"fps": x["fps"], "worst_ms": x["worst_ms"]}
            for x in frames if x["worst_ms"] >= 500]
    spans.sort(key=lambda x: x["seconds"], reverse=True)
    hle.sort(key=lambda x: x["ns"], reverse=True)
    mean_fps = round(sum(x["frames"] for x in frames) / sum(x["seconds"] for x in frames), 2) if frames and sum(x["seconds"] for x in frames) > 0 else None
    return {
        "present_windows": len(frames), "mean_present_fps": mean_fps,
        "long_present_gaps": gaps[:20], "repeated_guest_pc_spans": spans[:20],
        "most_expensive_hle_samples": hle[:10], "queue_samples": queue[-10:],
        "can_prove_gameplay_liveness": False,
        "caveat": ("Presented frames can repeat an unchanged game image; repeated guest PCs can "
                   "be legitimate. Require PS5 capture, synchronized guest progress and an "
                   "isolated A/B test before attributing a freeze to JIT, HLE or GPU."),
    }

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log", type=Path, help="existing console log text; no game content required")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.log.is_file():
        ap.error(f"no log file: {args.log}")
    data = analyze(args.log.read_text(errors="replace").splitlines())
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Present windows: {data['present_windows']}; average presented FPS: "
              f"{data['mean_present_fps'] if data['mean_present_fps'] is not None else 'unknown'}")
        print(f"Present gaps >= 500 ms: {len(data['long_present_gaps'])}; "
              f"persistent sampled guest PCs: {len(data['repeated_guest_pc_spans'])}")
        for s in data["repeated_guest_pc_spans"]:
            print(f"  core={s['core']} pc={s['guest_pc']} duration={s['seconds']}s "
                  f"guest-thread CPU progress(ns)={s['cpu_delta_ns']} hypothesis={s['hypothesis']}")
        print("CAUTION: neither presented FPS nor a repeated PC proves gameplay is advancing or frozen.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
