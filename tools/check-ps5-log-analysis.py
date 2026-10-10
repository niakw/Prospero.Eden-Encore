#!/usr/bin/env python3
"""Synthetic-only PS5 telemetry fixture, no native PS5 execution/build/CI."""
from __future__ import annotations
import importlib.util
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("eden_ps5_log_triage", ROOT/"tools/analyze-ps5-logs.py")
assert spec and spec.loader
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

TEXT="""EDEN_PS5_JIT_POLICY free_mib=11826 admission_budget_mib=4376 safe=0 sparse=0
EDEN_VULKAN_FRAME frames=100 seconds=5.000 fps=20.000 worst_ms=400.0 total=100 late38=20 late50=6 late100=3 late200=1 late500=0
EDEN_VULKAN_FRAME frames=150 seconds=5.000 fps=30.000 worst_ms=33.5 total=250 late38=0 late50=0 late100=0 late200=0 late500=0
[ProsperoEden] slow frame: update 175 ms, draw 0 ms, present 1 ms
EDEN_PAD_CONTEXT mode=gameplay reason=activity
EDEN_PAD_CONTEXT mode=ui reason=navigation
[ProsperoEden] glyphs: In-game button art: Nintendo original (rule=unsupported)
CreateGraphicsPipeline: Instruction PRMT (imm) is not implemented
Direct allocation failed: rc=80020023 bytes=461373440 limit=12884901888
EDEN_HEAP_PIECE bytes=134217728 va=0x100000000 pa=abc123 alloc_ns=3000000 map_ns=6000000 zero_ns=15000000
EDEN_HEAP_LIFETIME phase=core_destroyed pieces=1476395008 large=0 large_blocks=0 tcache=1048576
EDEN_HEAP_GROW req_bytes=201326592 root=1 pieces=2 spaces=2 committed_mib=384
EDEN_HEAP_ROOT phase=core_destroyed root=0 pieces=1 held_bytes=2233 held_blocks=4 arena_pins=3 physical_owner=1 reclaim=disabled
EDEN_HEAP_ROOT phase=core_destroyed root=1 pieces=2 held_bytes=0 held_blocks=0 arena_pins=0 physical_owner=1 reclaim=disabled
EDEN_HEAP_ROOT phase=core_destroyed root=3 pieces=1 held_bytes=0 held_blocks=0 arena_pins=0 physical_owner=0 reclaim=disabled
EDEN_PS5_DMEM_PROBE_FAILED consecutive=1 fallback=last_confirmed
EDEN_PS5_DMEM_PROBE_FAILED consecutive=2 fallback=conservative
EDEN_PS5_DMEM_PROBE_SLOW latency_ns=3500000 known=1
EDEN_MEMORY_LIVE frame=300 largest_last_confirmed=4328521728 short=0
EDEN_WORKER_TOPOLOGY ready=0 distinct_cores=1 cpus=0,0,0,0,0
"""
with tempfile.TemporaryDirectory(prefix="eden-ps5-log-triage-") as folder:
    root=Path(folder)
    a,b=root/"stderr6.log",root/"stderr7.log"
    a.write_text(TEXT,encoding="utf-8")
    b.write_text(TEXT,encoding="utf-8")
    report=m.analyze([a,b])
    assert report["input_file_count"] == 2
    assert report["unique_file_count"] == 1
    assert len(report["duplicate_files_not_counted_twice"]) == 1
    data=report["unique_logs"][0]["telemetry"]
    assert data["frame_windows"] == 2
    assert data["aggregate_frames"] == 250
    assert data["aggregate_seconds"] == 10
    assert data["weighted_fps"] == 25.0
    assert data["minimum_5s_fps_window"]["fps_reported"] == 20
    assert data["largest_single_worst_frame_window"]["worst_ms"] == 400
    assert data["late_frame_counts"]["late50"] == 6
    assert data["slow_launcher_update_frames"][0]["update_ms"] == 175
    assert data["pad_context_transitions"]["ui"] == 1
    assert data["original_nintendo_glyph_events"] == 1
    assert data["out_of_memory_hints"] == 1
    assert len(data["gpu_compatibility_diagnostics"]) == 1
    assert data["jit_policy_samples"][0]["fields"]["sparse"] == 0
    pressure = data["resource_pressure"]
    assert pressure["heap_piece_commits_over_16ms"] == 1
    assert pressure["heap_piece_commit_samples"][0]["total_ms"] == 24.0
    assert pressure["heap_lifetime_samples"][0]["committed_heap_bytes"] == 1476395008
    assert pressure["heap_lifetime_samples"][0]["phase"] == "core_destroyed"
    growth = pressure["heap_growth_events"]
    assert len(growth) == 1
    assert growth[0]["request_bytes"] == 201326592
    assert growth[0]["new_physical_extent_mib"] == 256
    assert growth[0]["committed_total_mib"] == 384
    roots = pressure["heap_root_snapshots"]
    assert len(roots) == 3
    assert roots[0]["diagnostic_reason"] == "pinned_child_arenas"
    assert roots[1]["physical_extent_mib"] == 256
    assert roots[1]["diagnostic_reason"] == "zero_reported_but_quiescence_unproven"
    assert roots[1]["reclaim"] == "disabled"
    assert roots[2]["diagnostic_reason"] == "missing_direct_owner"
    transient = TEXT.replace(
        "held_bytes=0 held_blocks=0 arena_pins=0 physical_owner=1",
        "held_bytes=-256 held_blocks=0 arena_pins=0 physical_owner=1",
    )
    shifted = m.parse_log(transient.encode("utf-8"))
    assert shifted["resource_pressure"]["heap_root_snapshots"][1][
        "diagnostic_reason"] == "inconsistent_or_transient_ledger"
    assert shifted["resource_pressure"]["heap_root_snapshots"][1]["reclaim"] == "disabled"
    mismatched = TEXT.replace(
        "held_bytes=0 held_blocks=0 arena_pins=0 physical_owner=1",
        "held_bytes=0 held_blocks=3 arena_pins=0 physical_owner=1",
    )
    assert m.parse_log(mismatched.encode("utf-8"))["resource_pressure"][
        "heap_root_snapshots"][1]["diagnostic_reason"] == "inconsistent_or_transient_ledger"
    assert [x["fallback"] for x in pressure["direct_memory_probe_failures"]] == [
        "last_confirmed", "conservative"]
    assert pressure["direct_memory_slow_probe_samples"][0]["latency_ms"] == 3.5
    assert pressure["gpu_last_confirmed_memory_samples"][0]["short"] is False
    assert pressure["worker_topology_samples"][0]["distinct_cores"] == 1
    assert pressure["worker_topology_samples"][0]["ready"] is False
    # Malformed root ownership indexes may never become a false green
    # candidate: even a seemingly empty root cannot bypass the 3-GiB limit.
    bad_growth = TEXT.replace("committed_mib=384", "committed_mib=256")
    assert not m.parse_log(bad_growth.encode("utf-8"))[
        "resource_pressure"]["heap_growth_events"]
    bad = TEXT.replace("root=1 pieces=2", "root=24 pieces=2")
    try:
        m.parse_log(bad.encode("utf-8"))
    except ValueError as error:
        assert "heap root" in str(error)
    else:
        raise AssertionError("invalid heap root passed parser")
    b.write_bytes(b"binary\x00not a log")
    try:
        m.analyze([a,b])
    except ValueError:
        pass
    else:
        raise AssertionError("NUL log falsely treated as telemetry")
print("HOST FIXTURE PASS: FPS/late frames, heap-growth cause, root ownership/quiescence, commit latency, memory probe, lifetime, worker topology, duplicate logs")
print("No FC27 rerun, host native build, GitHub Actions or PS5 SDK compilation performed")
