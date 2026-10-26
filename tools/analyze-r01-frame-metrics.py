#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize CPU-observed Vulkan frame rates from opt-in Encore R01 logs.

R01 does NOT measure guest simulation FPS, HDMI scanout, latency, or GPU frame
time. Input may include multiple sessions and rotated log files; a frame-number
reset indicates a new session, so rate averages are never silently mixed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

TAG = "EDEN_R01_FRAME_METRICS "
METRICS = ("source_composites", "real_queued", "generated_queued",
           "source_skipped", "loading_queued", "present_returned")
SCOPE = "cpu_observed_not_guest_fps_not_scanout_not_latency"
MAX_INTERVAL_NS = 120_000_000_000  # avoid counting clearly corrupt >2min windows


def parse_logs(lines):
    sessions = []
    current = []
    bad = []
    last_frame = -1
    for lineno, text in enumerate(lines, 1):
        if TAG not in text:
            continue
        tokens = text.split(TAG, 1)[1].strip().split()
        data = {}
        try:
            for token in tokens:
                key, value = token.split("=", 1)
                if key in data:
                    raise ValueError("duplicate key")
                data[key] = value
            if data.get("scope") != SCOPE:
                raise ValueError("unqualified telemetry scope")
            frame = int(data["frame"])
            ns = int(data["interval_ns"])
            if frame < 0 or ns <= 0 or ns > MAX_INTERVAL_NS:
                raise ValueError("invalid frame/window interval")
            counts = {name: int(data[name]) for name in METRICS}
            if any(n < 0 for n in counts.values()):
                raise ValueError("negative frame count")
        except (ValueError, KeyError) as exc:
            bad.append({"line": lineno, "reason": str(exc)})
            continue
        if current and frame < last_frame:
            sessions.append(current)
            current = []
        last_frame = frame
        current.append({"frame": frame, "interval_ns": ns, **counts})
    if current:
        sessions.append(current)
    return sessions, bad


def summary(sessions, bad):
    output = []
    for index, rows in enumerate(sessions, 1):
        total_ns = sum(row["interval_ns"] for row in rows)
        counters = {k: sum(row[k] for row in rows) for k in METRICS}
        rates = {
            "source_callback_fps": round(counters["source_composites"] * 1e9 / total_ns, 3),
            "real_queued_fps": round(counters["real_queued"] * 1e9 / total_ns, 3),
            "generated_queued_fps": round(counters["generated_queued"] * 1e9 / total_ns, 3),
            "present_return_fps": round(counters["present_returned"] * 1e9 / total_ns, 3),
        }
        output.append({"index": index, "samples": len(rows), "duration_ns": total_ns,
                       "counts": counters, "rates": rates, "frame_first": rows[0]["frame"],
                       "frame_last": rows[-1]["frame"]})
    return {
        "schema": "eden-encore-r01-v1",
        "measurement": "cpu_observed_vulkan_callbacks_not_guest_simulation_or_scanout",
        "input_to_photon_latency": None,
        "actual_guest_fps": None,
        "gpu_render_time_ms": None,
        "sessions": output,
        "rejected_lines": bad,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("logs", type=Path, nargs="+", help="native stdout/boot trace log(s)")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    args = ap.parse_args(argv)
    lines = []
    for path in args.logs:
        lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
    report = summary(*parse_logs(lines))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("R01 measured source/queued/Present API callbacks; NOT game FPS, latency or display scanout.")
        for s in report["sessions"]:
            q=s["rates"]
            print(f"session={s['index']} samples={s['samples']} "
                  f"source_callback_fps={q['source_callback_fps']:.3f} "
                  f"real_queue_fps={q['real_queued_fps']:.3f} "
                  f"generated_queue_fps={q['generated_queued_fps']:.3f} "
                  f"present_return_fps={q['present_return_fps']:.3f}")
        if report["rejected_lines"]:
            print(f"Rejected malformed samples: {len(report['rejected_lines'])}", file=sys.stderr)
    return 0 if report["sessions"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
