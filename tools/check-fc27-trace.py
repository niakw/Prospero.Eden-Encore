#!/usr/bin/env python3
"""Offline synthetic liveness analysis regression; never builds the PS5 app."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

tool = Path(__file__).with_name("analyze-fc27-trace.py")
with tempfile.TemporaryDirectory(prefix="encore-fc27-trace-") as work:
    path = Path(work) / "repro.log"
    lines = [
        "EDEN_GAME_FRAME frames=150 seconds=5.000000 fps=30.000 worst_ms=34.000 total=150",
        "EDEN_DEV_HLE service=sm: cmd=3 calls=10 ns=5000000",
        "EDEN_DEV_QUEUE idle_ns=1000000 dispatch_ns=1000000",
        "EDEN_GAME_FRAME frames=1 seconds=6.000000 fps=0.167 worst_ms=6000.000 total=151",
    ]
    for i, (pc, t) in enumerate([("124AA117A8", 1), ("124AA117A8", 12),
                                   ("124AA117A8", 24), ("124AA117B0", 25)]):
        lines.append(f"EDEN_PERF_CPU_POINT core=2 mono_ns={t*1000000000} "
                     f"cpu_ns={i*1000000000} pc={pc} svc=0")
    for i, t in enumerate((1, 12, 24)):
        lines.append(f"EDEN_PERF_CPU_POINT core=0 mono_ns={t*1000000000} "
                     f"cpu_ns={i*1000000000} pc={['100','101','102'][i]} svc=0")
    path.write_text("\n".join(lines))
    proc = subprocess.run([sys.executable, "-B", str(tool), str(path), "--json"],
                          capture_output=True, text=True, check=True)
    result = json.loads(proc.stdout)
    assert abs(result["mean_present_fps"] - 151 / 11) < 0.01
    assert len(result["long_present_gaps"]) == 1
    assert result["repeated_guest_pc_spans"][0]["core"] == "2"
    assert result["repeated_guest_pc_spans"][0]["guest_pc"] == "124aa117a8"
    assert result["repeated_guest_pc_spans"][0]["hypothesis"] == "busy_guest_loop"
    assert result["can_prove_gameplay_liveness"] is False
    assert result["present_jitter_intervals"]["over_38ms"] == 0
    assert result["min_window_present_fps"] == 0.167
    # In release, one inexpensive aggregate every five seconds is enough to
    # measure 4-6 FPS dribble dips without spam or gameplay log overhead.
    jitter = Path(work) / "jitter.log"
    jitter.write_text("EDEN_VULKAN_FRAME frames=126 seconds=5 fps=25.2 worst_ms=140 total=126 late38=15 late50=8 late100=2\\n"
                      "EDEN_VULKAN_FRAME frames=149 seconds=5 fps=29.8 worst_ms=35 total=275 late38=0 late50=0 late100=0\\n")
    jitter_result = json.loads(subprocess.check_output(
        [sys.executable, "-B", str(tool), str(jitter), "--json"], text=True))
    assert jitter_result["mean_present_fps"] == 27.5
    assert jitter_result["min_window_present_fps"] == 25.2
    assert jitter_result["present_jitter_intervals"] == {
        "over_38ms": 15, "over_50ms": 8, "over_100ms": 2}
    assert len(result["most_expensive_hle_samples"]) == 1
    assert result["queue_samples"][-1]["idle_ns"] == 1000000
    healthy = Path(work) / "quiet.log"
    healthy.write_text("EDEN_GAME_FRAME frames=150 seconds=5 fps=30 worst_ms=33 total=150\n")
    quiet_result = json.loads(subprocess.check_output(
        [sys.executable, "-B", str(tool), str(healthy), "--json"], text=True))
    assert not quiet_result["repeated_guest_pc_spans"]
    assert not quiet_result["long_present_gaps"]
    assert quiet_result["mean_present_fps"] == 30
    # A repeated guest PC without CPU-time progress is not sufficient to
    # diagnose a busy loop; it could be a legitimate wait or a bad clock.
    waiting = Path(work) / "waiting.log"
    waiting.write_text("\n".join(
        f"EDEN_PERF_CPU_POINT core=3 mono_ns={sec*1000000000} "
        "cpu_ns=1000000 pc=00ABCDEF svc=0" for sec in (1, 13, 25)))
    wait_result = json.loads(subprocess.check_output(
        [sys.executable, "-B", str(tool), str(waiting), "--json"], text=True))
    assert wait_result["repeated_guest_pc_spans"][0]["hypothesis"] == "wait_or_unknown"
    assert wait_result["mean_present_fps"] is None

print("FC27 presentation vs sampled-guest-PC offline diagnostics: PASS")
