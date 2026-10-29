#!/usr/bin/env python3
"""Host-only V01 pipeline wait log parser and exact source marker contract."""
from importlib import util
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
path = root / "tools/analyze-ps5-pipeline-waits.py"
spec = util.spec_from_file_location("f07_keyed_waits", path)
assert spec and spec.loader
mod = util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

records = [
    "EDEN_VULKAN_SHADER_MISS kind=graphics key=0000000000001234 retry=0 success=1 cpu_ns=2000000 env_ns=10 pool_ns=20 cfg_ns=40 ir_ns=50 spirv_ns=100 module_ns=200",
    "EDEN_VULKAN_PIPELINE_WAIT kind=graphics key=0000000000001234 wait_ns=12000000 usable=1",
    "EDEN_VULKAN_SHADER_MISS kind=compute key=000000000000abcd retry=0 success=0 cpu_ns=1000000",
    "EDEN_VULKAN_PIPELINE_WAIT kind=compute key=000000000000abcd wait_ns=9000000 usable=0",
    "EDEN_VULKAN_PIPELINE_WAIT kind=graphics key=not-a-key wait_ns=4 usable=1",
]
waits, cpu, malformed = mod.parse(records)
assert len(waits) == 2 and malformed == 1
assert len(cpu[("graphics", "0000000000001234")]) == 1
assert len(cpu[("compute", "000000000000abcd")]) == 1
out = mod.report(records)
assert "worker_waits=2 malformed_waits=1" in out
assert "graphics: blocked_callbacks=1 matched_cpu_key=1 wait_sum_ms=12.000 failed_pipeline=0" in out
assert "compute: blocked_callbacks=1 matched_cpu_key=1 wait_sum_ms=9.000 failed_pipeline=1" in out
assert "key=000000000000abcd waited_ms=9.000 usable=0 cold_cpu_ms=1.000" in out
assert "totals are NOT" in out and "causality remains unmeasured" in out
assert "worker_waits=0 malformed_waits=0" in mod.report(["other log"])
graphics = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
compute = (root / "vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp").read_text()
perf = (root / "headless/performance.h").read_text()
for token in ('"graphics", key.Hash(), CanExecuteDraw()', '"compute", diagnostic_cache_key_hash, IsBound()'):
    assert token in graphics + compute
assert "EDEN_VULKAN_PIPELINE_WAIT kind=%s key=%016llx wait_ns=%llu usable=%u" in perf
print("F07_KEYED_PIPELINE_WAIT_ANALYSIS_PASS matched_cpu_worker=1 failed_pipeline=1 legacy_cpu=1 malformed=1 no_frame_claim=1")
