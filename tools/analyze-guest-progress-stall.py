#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Forensic triage: a running compositor can outlive game/audio progression.

Run on a read-only copy of the PS5's heap.log. No FTP, console I/O, save access,
network, writes to source checkout or screenshots are performed by this tool.

5-second compositor samples and HLE service totals are independent. HLE
statistics count completed service calls, not blocked guest CPU threads.
An absence of audio requests is NOT proof of a deadlock in a muted game.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re

KV = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=(-?[0-9]+(?:\.[0-9]+)?)")
HLE_KEYS = ("IHardwareOpusDecoder/9", "IStorage/0", "IHOSBinderDriver/3")


def values(line: str) -> dict[str, float]:
    return {k: float(v) for k, v in KV.findall(line)}


@dataclass
class Window:
    total: int
    duration: float
    fps: float
    worst_ms: float
    late100: int
    gpu: dict[str, float] = field(default_factory=dict)
    guest: dict[str, float] = field(default_factory=dict)
    hle: dict[str, tuple[int, float]] = field(default_factory=dict)


def parse(log: str) -> tuple[str, list[Window]]:
    sha = ""
    windows: list[Window] = []
    for line in log.splitlines():
        if line.startswith(("EDEN_BUILD_SOURCE ", "EDEN_SESSION_SOURCE ")):
            sha = line.partition("source_sha=")[2].strip()
        elif line.startswith("EDEN_VULKAN_FRAME "):
            kv = values(line)
            if "total" in kv:
                windows.append(Window(
                    int(kv["total"]), kv["seconds"], kv["fps"], kv["worst_ms"],
                    int(kv.get("late100", 0))))
        elif windows and line.startswith("EDEN_DEV_GPU "):
            windows[-1].gpu = values(line)
        elif windows and line.startswith("EDEN_DEV_GUEST "):
            windows[-1].guest = values(line)
        elif windows and line.startswith("EDEN_DEV_HLE "):
            kv = values(line)
            m = re.search(r"service=([^ ]+)\s+cmd=([0-9]+)", line)
            if m and {"calls", "ns"} <= kv.keys():
                windows[-1].hle[m.group(1) + "/" + m.group(2)] = (
                    int(kv["calls"]), kv["ns"])
    return sha, windows


def split_sessions(log: str) -> list[str]:
    """Retain each game's independent five-second windows, even in one heap file.

    The application can return to the launcher and start another game without
    restarting the process. Frame totals then reset, and naive whole-file
    comparisons either raise or falsely merge independent HLE counters.
    A late tail-only file may lack the boot SHA; copy the last known source
    identity into the next segment, or report it as unknown.
    """
    sessions: list[str] = []
    active: list[str] = []
    source = ""
    has_frames = False
    last_total: int | None = None
    for line in log.splitlines():
        if line.startswith(("EDEN_BUILD_SOURCE ", "EDEN_SESSION_SOURCE ")):
            source = line
        new_game = line.startswith("EDEN_STAGE ") and "phase=session_start" in line
        frame_total: int | None = None
        if line.startswith("EDEN_VULKAN_FRAME "):
            frame_kv = values(line)
            if "total" in frame_kv:
                frame_total = int(frame_kv["total"])
        reset = frame_total is not None and last_total is not None and frame_total <= last_total
        if has_frames and (new_game or reset):
            sessions.append("\n".join(active))
            active = [source] if source else []
            has_frames = False
            last_total = None
        active.append(line)
        if frame_total is not None:
            has_frames = True
            last_total = frame_total
    if has_frames:
        sessions.append("\n".join(active))
    return sessions


def analyze_sessions(log: str, minimum_still_seconds: float = 300.0) -> list[dict]:
    return [analyze(part, minimum_still_seconds) for part in split_sessions(log)]


def tail_since_last_advance(windows: list[Window], key: str) -> tuple[int, float] | None:
    # Require the service to remain in every reported top-32 HLE snapshot.
    # A missing snapshot is unknown, NOT evidence the service stopped.
    if not windows or any(key not in w.hle for w in windows[-10:]):
        return None
    last_calls = windows[-1].hle[key][0]
    start = len(windows) - 1
    while start > 0 and key in windows[start - 1].hle and (
        windows[start - 1].hle[key][0] == last_calls):
        start -= 1
    return start, sum(w.duration for w in windows[start:])


def analyze(log: str, minimum_still_seconds: float = 300.0) -> dict:
    sha, w = parse(log)
    assert w, "no measured five-second frames"
    assert all(b.total > a.total for a, b in zip(w, w[1:])), (
        "session has frame reset or repeated sample: split by game session")
    late = sum(x.late100 for x in w)
    stable = sum(29.95 <= x.fps <= 30.05 and x.worst_ms < 38 for x in w)
    media = {key: tail_since_last_advance(w, key) for key in HLE_KEYS}
    pairs = []
    for key in ("IHardwareOpusDecoder/9", "IStorage/0"):
        if media[key] and media[key][1] >= minimum_still_seconds:
            pairs.append(key)
    gpu_active = bool(w[0].gpu and w[-1].gpu) and (
        w[-1].gpu.get("draws", 0) > w[0].gpu.get("draws", 0) and
        w[-1].gpu.get("dispatch_calls", 0) > w[0].gpu.get("dispatch_calls", 0))
    guest_active = bool(w[0].guest and w[-1].guest) and (
        w[-1].guest.get("ipc_calls", 0) > w[0].guest.get("ipc_calls", 0) and
        w[-1].guest.get("cpu_write_calls", 0) > w[0].guest.get("cpu_write_calls", 0))
    # A whole-session increase is not proof that the compositor and guest
    # were STILL progressing during the suspected frozen end-of-match tail.
    # Require both media plateaus to overlap for the requested duration,
    # and actual monotonic progress in the last ten windows of that overlap.
    overlap_start = max((media[k][0] for k in pairs), default=len(w))
    overlap_seconds = sum(x.duration for x in w[overlap_start:])
    recent = w[max(overlap_start, len(w) - 10):]
    def advancing(kind: str, keys: tuple[str, ...]) -> bool:
        rows = [getattr(x, kind) for x in recent]
        return (len(rows) >= 2 and
                all(row and all(k in row for k in keys) for row in rows) and
                all(all(b[k] >= a[k] for k in keys)
                    for a, b in zip(rows, rows[1:])) and
                all(rows[-1][k] > rows[0][k] for k in keys))
    tail_gpu_active = advancing("gpu", ("draws", "dispatch_calls"))
    tail_guest_active = advancing("guest", ("ipc_calls", "cpu_write_calls"))
    candidate = (len(pairs) == 2 and
                 overlap_seconds >= minimum_still_seconds and
                 tail_gpu_active and tail_guest_active)
    # F05: DequeueBuffer completed-call counters cannot identify an
    # outstanding condition wait. The opt-in active gauge is sampled with
    # EDEN_DEV_GUEST; absence of that field on older/quiet builds is UNKNOWN,
    # never zero. A nonzero host waiter does not prove a guest-thread deadlock.
    dequeue_tail = w[-10:]
    dequeue_samples = [
        (row.duration, int(row.guest["dequeue_blocked"]))
        for row in dequeue_tail if "dequeue_blocked" in row.guest
    ]
    consecutive_blocked_seconds = 0.0
    for row in reversed(dequeue_tail):
        if "dequeue_blocked" not in row.guest or row.guest["dequeue_blocked"] <= 0:
            break
        consecutive_blocked_seconds += row.duration
    latest_dequeue = (
        int(w[-1].guest["dequeue_blocked"])
        if "dequeue_blocked" in w[-1].guest else None
    )
    # The 2 media services are function-specific, and a title may normally
    # stop them in silent menus. This is a diagnostic CANDIDATE, not a root cause.
    return {
        "source_sha": sha,
        "windows": len(w),
        "sample_seconds": round(sum(x.duration for x in w), 3),
        "total_frames": w[-1].total,
        "stable_callback_windows": stable,
        "late100_frames": late,
        "largest_frame_gap_ms": max(x.worst_ms for x in w),
        "gpu_progress": gpu_active,
        "guest_ipc_writes_progress": guest_active,
        "both_media_flat_seconds": round(overlap_seconds, 1) if len(pairs) == 2 else 0,
        "gpu_progress_in_last_plateau": tail_gpu_active if len(pairs) == 2 else False,
        "guest_progress_in_last_plateau": tail_guest_active if len(pairs) == 2 else False,
        "dequeue_blocked_latest": latest_dequeue,
        "dequeue_blocked_tail_samples": len(dequeue_samples),
        "dequeue_blocked_tail_peak": (
            max(value for _, value in dequeue_samples) if dequeue_samples else None
        ),
        "dequeue_blocked_consecutive_tail_seconds": round(consecutive_blocked_seconds, 1),
        "dequeue_blocked_interpretation": (
            "not_measured" if latest_dequeue is None else
            "host_slot_wait_active_not_guest_deadlock_proof" if latest_dequeue > 0 else
            "no_active_host_slot_wait_at_last_snapshot"
        ),
        "media_last_change": {
            key: {
                "first_flat_frame": w[item[0]].total,
                "approx_flat_seconds": round(item[1], 1)
            } for key, item in media.items() if item
        },
        "candidate_still_media_while_compositor_active": candidate
    }


def self_test() -> None:
    def record(i: int, audio: int, storage: int, gpu: int) -> str:
        return "\n".join([
            f"EDEN_VULKAN_FRAME frames=150 seconds=5.0 fps=30.0 worst_ms=33.5 total={gpu} late100=0",
            f"EDEN_DEV_GPU frame={gpu} draws={gpu*4} dispatch_calls={gpu*2}",
            f"EDEN_DEV_GUEST cpu_write_calls={gpu*4} ipc_calls={gpu*8}",
            f"EDEN_DEV_HLE service=IHardwareOpusDecoder cmd=9 calls={audio} ns=100",
            f"EDEN_DEV_HLE service=IStorage cmd=0 calls={storage} ns=100",
            f"EDEN_DEV_HLE service=IHOSBinderDriver cmd=3 calls={gpu*3} ns=100",
        ])
    log = "\n".join(["EDEN_BUILD_SOURCE source_sha=1234abcd"] + [
        record(i, min(i, 9), min(i, 9), 1000+150*i)
        for i in range(95)
    ])
    evidence = analyze(log)
    assert evidence["candidate_still_media_while_compositor_active"]
    assert evidence["stable_callback_windows"] == 95
    assert evidence["source_sha"] == "1234abcd"
    assert evidence["media_last_change"]["IStorage/0"]["approx_flat_seconds"] >= 400
    # Older builds have no active-dequeue gauge. Missing != zero.
    assert evidence["dequeue_blocked_latest"] is None
    assert evidence["dequeue_blocked_tail_samples"] == 0
    assert evidence["dequeue_blocked_tail_peak"] is None
    assert evidence["dequeue_blocked_interpretation"] == "not_measured"
    # Recent builds report a gauge only with detailed profiling.
    # Mixed samples must not hide missing intervals or claim deadlock.
    active = log.replace(
        "EDEN_DEV_GUEST cpu_write_calls=",
        "EDEN_DEV_GUEST dequeue_blocked=2 cpu_write_calls=",
    )
    live = analyze(active)
    assert live["dequeue_blocked_latest"] == 2
    assert live["dequeue_blocked_tail_samples"] == 10
    assert live["dequeue_blocked_tail_peak"] == 2
    assert live["dequeue_blocked_consecutive_tail_seconds"] == 50
    assert live["dequeue_blocked_interpretation"] == (
        "host_slot_wait_active_not_guest_deadlock_proof"
    )
    # An unmeasured last sample invalidates any continuous tail attribution.
    without_last = active.rsplit("EDEN_DEV_GUEST dequeue_blocked=2 ", 1)
    incomplete = analyze(without_last[0] + "EDEN_DEV_GUEST " + without_last[1])
    assert incomplete["dequeue_blocked_latest"] is None
    assert incomplete["dequeue_blocked_tail_samples"] == 9
    assert incomplete["dequeue_blocked_consecutive_tail_seconds"] == 0
    # A gauge that clears must be treated as no active host slot wait, not
    # evidence of game progression (the other counter tests remain separate).
    clear_last = active.rsplit("dequeue_blocked=2 ", 1)
    recovered = analyze(clear_last[0] + "dequeue_blocked=0 " + clear_last[1])
    assert recovered["dequeue_blocked_latest"] == 0
    assert recovered["dequeue_blocked_tail_peak"] == 2
    assert recovered["dequeue_blocked_consecutive_tail_seconds"] == 0
    assert recovered["dequeue_blocked_interpretation"] == (
        "no_active_host_slot_wait_at_last_snapshot"
    )
    healthy = "\n".join(record(i, i, i, 1000+150*i) for i in range(95))
    assert not analyze(healthy)["candidate_still_media_while_compositor_active"]
    # Regress false positives: both media counters become flat AFTER the GPU
    # and guest also stop. A complete-session comparison previously called
    # this "compositor active" because of the earlier gameplay.
    def paused(i: int) -> str:
        # A 30-Hz compositor keeps reporting new frame callbacks, while
        # independent GPU-draw and guest-IPC counters stop after window 9.
        total = 1000 + 150 * i
        work = 1000 + 150 * min(i, 9)
        return (record(i, min(i, 9), min(i, 9), total)
                .replace(f"draws={total*4} dispatch_calls={total*2}",
                         f"draws={work*4} dispatch_calls={work*2}")
                .replace(f"cpu_write_calls={total*4} ipc_calls={total*8}",
                         f"cpu_write_calls={work*4} ipc_calls={work*8}"))
    stopped_tail = "\n".join(paused(i) for i in range(95))
    stopped = analyze(stopped_tail)
    assert stopped["gpu_progress"] and stopped["guest_ipc_writes_progress"]
    assert not stopped["gpu_progress_in_last_plateau"]
    assert not stopped["guest_progress_in_last_plateau"]
    assert not stopped["candidate_still_media_while_compositor_active"]
    # If the last interval lacks counter snapshots, do not manufacture
    # evidence from older completed work.
    last_gpu = log.rsplit("EDEN_DEV_GPU ", 1)
    missing_gpu = last_gpu[0] + last_gpu[1].replace("draws=", "missing_draws=", 1)
    assert not analyze(missing_gpu)["candidate_still_media_while_compositor_active"]
    # Missing HLE service rows have no readable status, never fabricate idle.
    cut = log.rsplit("EDEN_DEV_HLE service=IStorage cmd=0 calls=9 ns=100", 1)[0]
    assert not analyze(cut)["candidate_still_media_while_compositor_active"]
    # The real diagnostic stream may contain two sessions in one heap file.
    multi = log + "\nEDEN_STAGE backend=Vulkan phase=session_start mono_ns=7\n" + healthy
    separate = analyze_sessions(multi)
    assert len(separate) == 2
    assert separate[0]["candidate_still_media_while_compositor_active"]
    assert not separate[1]["candidate_still_media_while_compositor_active"]
    assert all(x["source_sha"] == "1234abcd" for x in separate)
    # Old builds without a session marker can still be separated by reset.
    assert len(analyze_sessions(log + "\n" + healthy)) == 2
    # New per-session SHA overrides the boot SHA for that game's own windows.
    stamped = log + ("\nEDEN_STAGE backend=Vulkan phase=session_start mono_ns=7"
                     "\nEDEN_SESSION_SOURCE source_sha=5678dcba\n" + healthy)
    assert analyze_sessions(stamped)[1]["source_sha"] == "5678dcba"
    print("PASS guest vs compositor liveness: stopped media, progress, normal and missing sample")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("heap_log", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.heap_log:
        sessions = analyze_sessions(args.heap_log.read_text(errors="replace"))
        if not sessions:
            parser.error("no measured five-second game session in heap log")
        for index, result in enumerate(sessions, 1):
            print(f"=== Game session {index}/{len(sessions)} ===")
            for key, val in result.items():
                print(f"{key}: {val}")
        print("CAUTION: a compositor and guest counter advance does not prove "
              "scene progression, guest action-profile persistence or deadlock ownership")
    else:
        parser.error("provide read-only heap log or --self-test")


if __name__ == "__main__":
    main()
