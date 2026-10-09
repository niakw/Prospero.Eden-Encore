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
    b.write_bytes(b"binary\x00not a log")
    try:
        m.analyze([a,b])
    except ValueError:
        pass
    else:
        raise AssertionError("NUL log falsely treated as telemetry")
print("HOST FIXTURE PASS: frame windows/late thresholds, slow launcher, controller transitions, OOM, GPU, identical logs")
print("No FC27 rerun, host native build, GitHub Actions or PS5 SDK compilation performed")
