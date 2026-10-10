#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Host-only synthetic fixture: old and new GPU memory/JIT frame logs coexist."""
from __future__ import annotations
import importlib.util
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
name = "eden_frame_window_parser"
spec = importlib.util.spec_from_file_location(name, root / "tools/analyze-ps5-frame-windows.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[name] = module
spec.loader.exec_module(module)

def window(n: int, new: bool) -> str:
    items = [
        f"EDEN_VULKAN_FRAME frames={20+n} seconds=5.000 fps={4+n:.3f} worst_ms=180.000 late50=3 late100=1 late200=0",
        f"EDEN_DEV_GPU frame={20+n} cpu_ns={100_000_000*n} idle_ns={10_000_000*n} full_ns={1_000*n}",
        f"EDEN_DEV_GUEST cpu_write_calls={n} ipc_ns={1000*n} dequeue_ns={100*n} cache_lock_contended={n} cache_lock_blocked={n}",
    ]
    for core in range(3):
        items.append(f"EDEN_PERF_CPU_POINT core={core} cpu_ns={1000000*n}")
        items.append(f"EDEN_PERF_PROGRESS mono_ns={n} core={core} compilations={2*n} compile_ns={2000*n}")
    if new:
        items.append(f"EDEN_MEMORY_LIVE frame={20+n} largest_last_confirmed={33554432*n} short={int(n==2)}")
        items.append(f"EDEN_JIT_SPARSE_MEMORY phase=dev-profile reserved={134217728} committed={2097152*n}")
        items.append(f"EDEN_DEV_SNAPSHOT_COST mono_ns={123456789*n} elapsed_ns={3500000*n}")
    return "\n".join(items) + "\n"

with tempfile.TemporaryDirectory(prefix="eden-ps5-window-test-") as directory:
    original = Path(directory)/"old.log"
    updated = Path(directory)/"updated.log"
    original.write_text(window(1, False)+window(2, False), encoding="utf-8")
    updated.write_text(window(1, True)+window(2, True), encoding="utf-8")
    old, new = module.Trace.load(original), module.Trace.load(updated)
    assert old.windows() == new.windows() == 2
    assert not old.memory_live and not old.sparse and not old.snapshot_cost
    assert len(new.memory_live) == len(new.sparse) == len(new.snapshot_cost) == 2
    assert max(item["elapsed_ns"] for item in new.snapshot_cost) == 7000000
    assert old.report_window(1)["direct_free_mib"] == -1
    sample = new.report_window(1)
    assert sample["direct_free_mib"] == 64
    assert sample["direct_memory_short"] == 1
    assert sample["jit_ms"] > 0 and sample["guest_ipc_ms"] > 0
    assert max(x["committed"] for x in new.sparse) == 4194304
    # Actual archived PS5 stderr often prepends logger/timestamp metadata
    # to each native stdout marker. It must still parse all nine streams.
    prefixed = Path(directory)/"timestamped.log"
    prefixed.write_text("".join(
        f"2026-10-10T19:04:05.002Z [ProsperoEden] {line}\n"
        for line in (window(1, True)+window(2, True)).splitlines()
    ), encoding="utf-8")
    wrapped = module.Trace.load(prefixed)
    assert wrapped.windows() == 2
    assert wrapped.report_window(1)["jit_blocks"] == sample["jit_blocks"]
    # One missing CPU point cannot be shifted onto the next video sample;
    # summary FPS remains available without fabricated attribution.
    missing = Path(directory)/"missing-cpu.log"
    missing.write_text((window(1, True)+window(2, True)).replace(
        "EDEN_PERF_CPU_POINT core=2 cpu_ns=2000000", "DROPPED_SNAPSHOT"
    ), encoding="utf-8")
    incomplete = module.Trace.load(missing)
    assert len(incomplete.frames) == 2 and incomplete.windows() == 0
    # An optional memory probe is NOT necessarily frame-aligned if sparse.
    partial = Path(directory)/"partial-memory.log"
    partial.write_text((window(1, True)+window(2, True)).replace(
        "EDEN_MEMORY_LIVE frame=22 largest_last_confirmed=67108864 short=1", ""
    ), encoding="utf-8")
    unaligned = module.Trace.load(partial)
    assert unaligned.windows() == 2
    assert unaligned.report_window(1)["direct_free_mib"] == -1
    assert unaligned.report_window(1)["direct_memory_short"] == -1
    # A worker restarting between titles resets cumulative counters:
    # do not turn a negative CPU/GPU delta into a zero-time hypothesis.
    reset = Path(directory)/"reset-gpu.log"
    reset.write_text((window(1, True)+window(2, True)).replace(
        "EDEN_DEV_GPU frame=22 cpu_ns=200000000", "EDEN_DEV_GPU frame=22 cpu_ns=100000"
    ), encoding="utf-8")
    try:
        module.Trace.load(reset).report_window(1)
    except ValueError as error:
        assert "reset" in str(error)
    else:
        raise AssertionError("Reset across game session was treated as valid timing")
print("PASS: backward-compatible 5s PS5 GPU/guest/JIT metrics and confirmed pressure headroom")
print("NO PS5 firmware execution, SDK build or measured FPS gain")
