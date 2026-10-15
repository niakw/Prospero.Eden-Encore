#!/usr/bin/env python3
"""Host gate for the inactive developer-only cache replay source bridge.

Validates pinned anchors and CMake OFF parsing, not a native compilation or
correct GPU execution; opt-in ON remains explicitly unqualified.
"""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
bridge=root/"headless/guest_write_deferred_bridge.cmake"
code=bridge.read_text()
base=(root/"headless/CMakeLists.txt").read_text()
replay=(root/"headless/gpu_deferred_replay.h").read_text()
perf=(root/"headless/performance.h").read_text()
assert 'option(EDEN_GUEST_WRITE_BRIDGE_DEV "Compile inactive native deferred-write bridge" OFF)' in code
assert "NOT EDEN_DEV_PROFILE" in code and "NOT EDEN_PS5_VULKAN" in code
assert "guest_write_deferred_bridge.cmake" in base
assert "cpu_write_defer{false}" in perf
assert "cpu_write_defer.store(true" not in code
assert "ScopedReplay" in replay and "replaying_guest_write" in replay
for signature in (
    "EnqueueDeferredCPUWrite",
    "deferred_cpu_write_queue",
    "ReplayQueued(",
    "dirty[core].Collect(address, size);",
    "rasterizer->OnCPUWrite(address, size);",
    "gpu_memory->EnqueueDeferredCPUWrite(addr, size)",
    "memory_manager.FlushCaching();",
    "void MaxwellDMA::Launch()",
    "void KeplerCompute::ProcessLaunch()",
    "void DmaPusher::DispatchCalls()",
    "system.GPU().OnCommandListEnd();",
):
    assert signature in code, signature
pins={
    "video_core/memory_manager.h":["    void FlushCaching();","    Core::System& system;"],
    "video_core/memory_manager.cpp":['#include "memory_manager.h"',"void MemoryManager::FlushCaching() {"],
    "video_core/engines/maxwell_dma.cpp":["void MaxwellDMA::Launch() {"],
    "video_core/engines/kepler_compute.cpp":["void KeplerCompute::ProcessLaunch() {"],
    "video_core/dma_pusher.cpp":["void DmaPusher::DispatchCalls() {","    system.GPU().OnCommandListEnd();"],
}
for file, anchors in pins.items():
    text=(root/"vendor/sources/eden/src"/file).read_text()
    for needle in anchors:assert needle in text,(file,needle)
vk=(root/"vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
for needle in ("bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {",
               "GuestCacheLock(buffer_cache.mutex, false)",
               "GuestCacheLock(texture_cache.mutex, true)"):
    assert needle in vk,needle
with tempfile.TemporaryDirectory(prefix="encore-bridge-config-") as d:
    subprocess.run(["cmake","-P",str(bridge)],cwd=d,check=True,
                   timeout=20,capture_output=True,text=True)
print("NATIVE_GUEST_WRITE_BRIDGE_STATIC_PASS default_off=1 guest_session=1 gpu_dirty=1 dma=1 no_runtime_enable=1")
