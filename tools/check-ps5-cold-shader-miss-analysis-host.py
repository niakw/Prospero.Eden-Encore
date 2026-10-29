#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Host-only proof for keyed F07 shader miss accounting (no PS5 execution)."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "eden_shader_miss_analysis", root / "tools/analyze-ps5-cold-shader-misses.py"
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

logs = [
    "2026-10-29T08:00:00Z [PS5] EDEN_VULKAN_SHADER_MISS kind=graphics key=0123456789abcdef retry=0 success=0 cpu_ns=5000000",
    "EDEN_VULKAN_SHADER_MISS kind=graphics key=0123456789ABCDEF retry=1 success=1 cpu_ns=2000000",
    "EDEN_VULKAN_SHADER_MISS kind=graphics key=0000000000000001 retry=0 success=1 cpu_ns=12000000",
    "EDEN_VULKAN_SHADER_MISS kind=compute key=0000000000000002 retry=0 success=1 cpu_ns=1000000",
    "EDEN_VULKAN_SHADER_MISS kind=compute key=0000000000000003 retry=0 success=0 cpu_ns=500000",
    "EDEN_VULKAN_SHADER_MISS kind=compute key=invalid retry=0 success=0 cpu_ns=500000",
    "EDEN_GPU_CACHE_PHASE frame=100 phase=shader_cfg window_samples=1 window_ns=100",
]
records, malformed = module.parse(logs)
assert len(records) == 5 and malformed == 1
assert records[0].key == records[1].key
assert module.nearest_rank_95([100, 200, 300, 400, 500]) == 500
output = module.report(records, malformed)
assert "shader_miss_records=5 malformed=1" in output
assert "graphics: attempts=3 unique_keys=2 cold=2 retry=1 failures=1" in output
assert "cpu_sum_ms=19.000 cold_cpu_ms=17.000 retry_cpu_ms=2.000" in output
assert "compute: attempts=2 unique_keys=2 cold=2 retry=0 failures=1" in output
assert "cpu_sum_ms=1.500" in output
assert "slow_key=0000000000000001 retry=0 success=1 cpu_ms=12.000" in output
assert "No frame IDs" in output
assert "NO_VALID_SHADER_MISSES malformed=1" == module.report([], 1)
assert module.parse(["EDEN_VULKAN_SHADER_MISS kind=graphics key=0123456789abcdef retry=2 success=1 cpu_ns=1"]) == ([], 1)
assert module.parse(["EDEN_VULKAN_SHADER_MISS kind=graphics key=0123456789abcdef retry=0 success=1 cpu_ns=-1"]) == ([], 1)
# Pin the parser's contract to the actual native emitter. The marker has
# no frame ID, and the four callsites are cold/retry graphics/compute only.
source = (root / "vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text(
    encoding="utf-8"
)
assert "EDEN_VULKAN_SHADER_MISS kind=%s key=%016llx retry=%u " in source
assert r"success=%u cpu_ns=%llu\n" in source
assert source.count("ColdShaderMissTrace cold_") == 4
print("PASS F07: keyed cold shader miss/retry accounting, malformed exclusion and no frame attribution")
print("No PS5 runtime measurement or FPS gain claimed")
