#!/usr/bin/env python3
"""Read-only PS5 Eden Encore log triage: frame-time outliers and duplicate sessions.

This intentionally reads *existing* locally authorized logs, performs no game
execution, no PS5 API calls, no Actions, no builds and no network requests.

Avoid counting the exact same log twice (for example, copied stderr files).
The Vulkan line is an aggregate of presented-frame windows; a window average
near 30 FPS does NOT prove that individual frames are smooth. The lateN
counters are parsed only as reported by the native logger, not reconstructed
from guessed frame durations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MAX_FILES = 32
MAX_LOG_BYTES = 32 * 1024 * 1024
MAX_WINDOWS = 40000
MAX_EVENTS = 100
FRAME = re.compile(r"\bEDEN_VULKAN_FRAME\s+frames=(\d+)\s+seconds=([\d.]+)\s+fps=([\d.]+)\s+worst_ms=([\d.]+)([^\r\n]*)")
LATE = re.compile(r"\b(late38|late50|late100|late200|late500)=(\d+)\b")
SLOW = re.compile(r"\bslow frame:\s*update\s+(\d+)\s+ms,\s*draw\s+(\d+)\s+ms,\s*present\s+(\d+)\s+ms")
PAD = re.compile(r"\bEDEN_PAD_CONTEXT\s+mode=(gameplay|ui)(?:\s+reason=([a-z_]+))?")
JIT = re.compile(r"\bEDEN_PS5_JIT_POLICY\s+(.+)")
JIT_FIELD = re.compile(r"\b(free_mib|admission_budget_mib|safe|sparse)=(\d+)\b")
GPU_ERROR = re.compile(r"PRMT\s*\(imm\)|PRMT_imm|Source depth is not one|EDEN_GPU_FERMI2D_UNSUPPORTED|EDEN_GPU_PRMT_\w+")
GLYPH_ORIGINAL = re.compile(r"glyphs:.*Nintendo original.*rule=unsupported")
# Bounded native-resource diagnostics: these are observed samples, never
# estimates of total unified GPU/CPU memory or proof of an allocation leak.
HEAP_PIECE = re.compile(
    r"\bEDEN_HEAP_PIECE\s+bytes=(\d+)\s+va=\S+\s+pa=\S+\s+"
    r"alloc_ns=(\d+)\s+map_ns=(\d+)\s+zero_ns=(\d+)")
HEAP_LIFETIME = re.compile(
    r"\bEDEN_HEAP_LIFETIME\s+phase=([a-z_]+)\s+pieces=(\d+)\s+"
    r"large=(\d+)\s+large_blocks=(\d+)\s+tcache=(\d+)")
DMEM_FAILED = re.compile(
    r"\bEDEN_PS5_DMEM_PROBE_FAILED\s+consecutive=(\d+)\s+"
    r"fallback=(last_confirmed|conservative)")
DMEM_SLOW = re.compile(r"\bEDEN_PS5_DMEM_PROBE_SLOW\s+latency_ns=(\d+)\s+known=(\d+)")
MEMORY_LIVE = re.compile(
    r"\bEDEN_MEMORY_LIVE\s+frame=(\d+)\s+"
    r"largest_last_confirmed=(\d+)\s+short=(\d+)")
TOPOLOGY = re.compile(r"\bEDEN_WORKER_TOPOLOGY\s+ready=(\d+)([^\r\n]*)")
TOPOLOGY_CORES = re.compile(r"\bdistinct_cores=(\d+)\b")
LINE_LIMIT = 16 * 1024


def parse_log(data: bytes) -> dict:
    if len(data) > MAX_LOG_BYTES or b"\x00" in data:
        raise ValueError("binary or oversized PS5 log")
    text = data.decode("utf-8", "replace")
    frame_windows: list[dict] = []
    slow_updates: list[dict] = []
    pad_context = {"gameplay": 0, "ui": 0}
    pad_events: list[dict] = []
    gpu_errors = []
    jit_policy = []
    glyph_original_count = 0
    oom_hints = 0
    heap_piece_samples: list[dict] = []
    heap_lifetime: list[dict] = []
    dmem_failures: list[dict] = []
    dmem_slow: list[dict] = []
    memory_live: list[dict] = []
    topology_samples: list[dict] = []
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) > LINE_LIMIT:
            raise ValueError("oversized PS5 log line")
        if frame := FRAME.search(line):
            if len(frame_windows) >= MAX_WINDOWS:
                raise ValueError("excessive frame telemetry")
            frames = int(frame[1])
            seconds = float(frame[2])
            fps = float(frame[3])
            worst = float(frame[4])
            if not (0 < seconds < 3600 and 0 <= fps < 1000 and 0 <= worst < 3_600_000
                    and frames <= 1_000_000):
                raise ValueError("invalid reported frame telemetry")
            late = {key: int(value) for key, value in LATE.findall(frame[5])}
            frame_windows.append({"line": number, "frames": frames, "seconds": seconds,
                                  "fps_reported": fps, "worst_ms": worst,
                                  "late": late})
        if slow := SLOW.search(line):
            if len(slow_updates) < MAX_EVENTS:
                slow_updates.append({"line": number, "update_ms": int(slow[1]),
                                     "draw_ms": int(slow[2]), "present_ms": int(slow[3])})
        if context := PAD.search(line):
            pad_context[context[1]] += 1
            if len(pad_events) < MAX_EVENTS:
                pad_events.append({"line": number, "mode": context[1],
                                   "reason": context[2] or "unspecified"})
        if GPU_ERROR.search(line) and len(gpu_errors) < MAX_EVENTS:
            gpu_errors.append({"line": number, "type": "PRMT_or_Fermi2D",
                               "message": line[:240]})
        if match := JIT.search(line):
            if len(jit_policy) < MAX_EVENTS:
                jit_policy.append({"line": number, "fields": {
                    k: int(v) for k, v in JIT_FIELD.findall(match[1])}})
        if GLYPH_ORIGINAL.search(line):
            glyph_original_count += 1
        if "std::bad_alloc" in line or "Direct allocation failed:" in line:
            oom_hints += 1
        if heap := HEAP_PIECE.search(line):
            if len(heap_piece_samples) < MAX_EVENTS:
                size, alloc, mapping, zero = (int(x) for x in heap.groups())
                if size <= 16 * 1024**3 and max(alloc, mapping, zero) <= 600_000_000_000:
                    heap_piece_samples.append({
                        "line": number, "committed_bytes": size,
                        "alloc_ms": round(alloc / 1_000_000, 3),
                        "map_ms": round(mapping / 1_000_000, 3),
                        "zero_ms": round(zero / 1_000_000, 3),
                        "total_ms": round((alloc + mapping + zero) / 1_000_000, 3)})
        if lifetime := HEAP_LIFETIME.search(line):
            if len(heap_lifetime) < MAX_EVENTS:
                phase, pieces, large, blocks, tcache = lifetime.groups()
                heap_lifetime.append({
                    "line": number, "phase": phase,
                    "committed_heap_bytes": int(pieces),
                    "large_live_bytes": int(large),
                    "large_live_blocks": int(blocks),
                    "tcache_approx_bytes": int(tcache)})
        if fail := DMEM_FAILED.search(line):
            if len(dmem_failures) < MAX_EVENTS:
                dmem_failures.append({
                    "line": number, "consecutive": int(fail[1]),
                    "fallback": fail[2]})
        if slow_probe := DMEM_SLOW.search(line):
            if len(dmem_slow) < MAX_EVENTS:
                dmem_slow.append({
                    "line": number, "latency_ms": round(int(slow_probe[1]) / 1_000_000, 3),
                    "known": bool(int(slow_probe[2]))})
        if live := MEMORY_LIVE.search(line):
            if len(memory_live) < MAX_EVENTS:
                memory_live.append({
                    "line": number, "frame": int(live[1]),
                    "last_confirmed_largest_bytes": int(live[2]),
                    "short": bool(int(live[3]))})
        if topology := TOPOLOGY.search(line):
            if len(topology_samples) < MAX_EVENTS:
                cores = TOPOLOGY_CORES.search(topology[2])
                topology_samples.append({
                    "line": number, "ready": bool(int(topology[1])),
                    "distinct_cores": int(cores[1]) if cores else None})

    frame_count = sum(x["frames"] for x in frame_windows)
    seconds = sum(x["seconds"] for x in frame_windows)
    late_total = {key: sum(x["late"].get(key, 0) for x in frame_windows)
                  for key in ("late38", "late50", "late100", "late200", "late500")}
    slowest = min(frame_windows, key=lambda x: x["fps_reported"]) if frame_windows else None
    worst = max(frame_windows, key=lambda x: x["worst_ms"]) if frame_windows else None
    return {
        "frame_windows": len(frame_windows),
        "aggregate_frames": frame_count,
        "aggregate_seconds": round(seconds, 6),
        "weighted_fps": round(frame_count / seconds, 3) if seconds else None,
        "minimum_5s_fps_window": slowest,
        "largest_single_worst_frame_window": worst,
        "late_frame_counts": late_total,
        "slow_launcher_update_frames": slow_updates,
        "pad_context_transitions": pad_context,
        "pad_context_events": pad_events,
        "jit_policy_samples": jit_policy,
        "gpu_compatibility_diagnostics": gpu_errors,
        "original_nintendo_glyph_events": glyph_original_count,
        "out_of_memory_hints": oom_hints,
        "resource_pressure": {
            "heap_piece_commit_samples": heap_piece_samples,
            "heap_piece_commits_over_16ms": sum(
                sample["total_ms"] >= 16 for sample in heap_piece_samples),
            "heap_lifetime_samples": heap_lifetime,
            "direct_memory_probe_failures": dmem_failures,
            "direct_memory_slow_probe_samples": dmem_slow,
            "gpu_last_confirmed_memory_samples": memory_live,
            "worker_topology_samples": topology_samples,
            "warning": ("Heap pieces are retained physical backing, not live bytes. "
                        "A largest contiguous direct-memory block is not total free "
                        "GPU VRAM; samples may be incomplete or from other sessions.")
        },
        "frame_samples_absent_does_not_imply_smooth": True,
    }


def analyze(paths: list[Path]) -> dict:
    if not 1 <= len(paths) <= MAX_FILES:
        raise ValueError("provide between 1 and 32 local logs")
    dedup: dict[str, str] = {}
    documents = []
    duplicates = []
    for file in paths:
        if not file.is_file() or file.is_symlink() or not 1 <= file.stat().st_size <= MAX_LOG_BYTES:
            raise ValueError(f"missing, unsafe or oversized input: {file.name}")
        # A pre-open stat is not a memory limit: the log writer could
        # append concurrently. Bound the actual read too.
        with file.open("rb") as source:
            raw = source.read(MAX_LOG_BYTES + 1)
        if len(raw) > MAX_LOG_BYTES:
            raise ValueError("input grew beyond size guard")
        digest = hashlib.sha256(raw).hexdigest()
        if digest in dedup:
            duplicates.append({"duplicate_file": file.name,
                               "same_content_as": dedup[digest],
                               "sha256": digest})
            continue
        dedup[digest] = file.name
        documents.append({"file": file.name, "bytes": len(raw),
                          "sha256": digest, "telemetry": parse_log(raw)})
    return {
        "schema": 1, "source": "locally supplied existing PS5 logs",
        "input_file_count": len(paths), "unique_file_count": len(documents),
        "duplicate_files_not_counted_twice": duplicates, "unique_logs": documents,
        "warning": "Logs can belong to different builds and phases. Never combine FPS from independent sessions as if it were a controlled A/B test. Native FW13.60 retest needed for all new fixes.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path, help="preexisting local log files")
    parser.add_argument("--out", type=Path, help="NEW JSON report; never overwrite")
    args = parser.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("invalid/existing report path")
        report = json.dumps(analyze(args.logs), indent=2, ensure_ascii=False) + "\n"
        if args.out:
            with args.out.open("x", encoding="utf-8") as target:
                target.write(report)
            print(f"READ-ONLY PS5 LOG TRIAGE {args.out}")
        else:
            print(report, end="")
        return 0
    except (ValueError, OSError) as error:
        print(f"REJECTED PS5 log analysis: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
