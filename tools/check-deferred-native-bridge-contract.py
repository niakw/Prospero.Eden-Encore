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
    "void State::ProcessData(std::span<const u8> read_buffer)",
    "void DmaPusher::DispatchCalls()",
    "system.GPU().OnCommandListEnd();",
):
    assert signature in code, signature
pins={
    "video_core/memory_manager.h":["    void FlushCaching();","    Core::System& system;"],
    "video_core/memory_manager.cpp":['#include "memory_manager.h"',"void MemoryManager::FlushCaching() {"],
    "video_core/engines/maxwell_dma.cpp":["void MaxwellDMA::Launch() {"],
    "video_core/engines/engine_upload.cpp":["void State::ProcessData(std::span<const u8> read_buffer) {"],
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
# Configure the development CMake path using dummy host targets. This
# exercises source translation without the native SDK or a console build.
with tempfile.TemporaryDirectory(prefix="encore-bridge-on-") as d:
    fake=Path(d)
    (fake/"empty.cpp").write_text("int bridge_host_stub() { return 0; }\n")
    stage=fake/"stage"
    stage.mkdir()
    source=root/"vendor/sources/eden/src/video_core/dma_pusher.cpp"
    (stage/"dma_pusher.cpp").write_bytes(source.read_bytes())
    project=r"""cmake_minimum_required(VERSION 3.24)
project(InactiveBridgeConfigure LANGUAGES CXX)
set(PS5_NATIVE ON)
set(EDEN_PS5_VULKAN ON)
set(EDEN_DEV_PROFILE ON)
set(EDEN_GUEST_WRITE_BRIDGE_DEV ON CACHE BOOL "" FORCE)
set(PORT_ROOT "__ROOT__")
set(EDEN_PORT_DIR "__ROOT__/headless")
set(PROJECT_SOURCE_DIR "__ROOT__/vendor/sources/eden")
set(PORT_BUILD_DIR "__STAGE__")
add_library(video_core STATIC "@{CMAKE_CURRENT_SOURCE_DIR}/empty.cpp")
add_library(core STATIC "@{CMAKE_CURRENT_SOURCE_DIR}/empty.cpp")
set_property(TARGET video_core PROPERTY SOURCES
    "memory_manager.cpp"
    "@{PORT_BUILD_DIR}/vulkan_rasterizer.cpp"
    "@{PORT_BUILD_DIR}/dma_pusher.cpp"
    "engines/maxwell_dma.cpp"
    "engines/kepler_compute.cpp"
    "engines/engine_upload.cpp")
function(write_derived path content)
    file(WRITE "@{path}" "@{content}")
endfunction()
include("__BRIDGE__")
""".replace("@{",chr(36)+"{").replace("__ROOT__",str(root)).replace("__STAGE__",str(stage)).replace("__BRIDGE__",str(bridge))
    (fake/"CMakeLists.txt").write_text(project)
    result=subprocess.run(["cmake","-S",str(fake),"-B",str(fake/"build")],
                          capture_output=True,text=True,timeout=45)
    if result.returncode:
        print(result.stdout[-3500:])
        print(result.stderr[-3500:])
        raise AssertionError("native ON CMake source translation failed")
    sources={p.name:p.read_text() for p in stage.iterdir() if p.is_file()}
    for name in ("memory_manager_deferred.cpp","vulkan_rasterizer_deferred.cpp",
                 "dma_pusher_deferred.cpp","maxwell_dma_deferred.cpp",
                 "kepler_compute_deferred.cpp","engine_upload_deferred.cpp"):
        assert name in sources and len(sources[name])>200,name
    mm=sources["memory_manager_deferred.cpp"]
    assert "deferred_cpu_write_queue.Enqueue(core, address, size)" in mm
    assert "rasterizer->OnCPUWrite(address, size)" in mm
    assert "dirty[core].Collect(address, size)" in mm
    vk=sources["vulkan_rasterizer_deferred.cpp"]
    assert vk.count("EnqueueDeferredCPUWrite(addr, size)") == 1
    assert vk.count("GuestCacheLock(texture_cache.mutex, true)") >= 2
    assert "texture_cache.mutex.try_lock()" not in vk
    assert "!::Eden::GpuDeferredWrite::replaying_guest_write" in vk
    assert "std::lock_guard lock{buffer_cache.mutex, std::adopt_lock};" in vk
    assert "std::lock_guard lock{texture_cache.mutex, std::adopt_lock};" in vk
    assert sources["dma_pusher_deferred.cpp"].count("memory_manager.FlushCaching()") >= 2
    assert "memory_manager.FlushCaching();" in sources["maxwell_dma_deferred.cpp"]
    assert "memory_manager.FlushCaching();" in sources["kepler_compute_deferred.cpp"]
    upload=sources["engine_upload_deferred.cpp"]
    assert "void State::ProcessData(std::span<const u8> read_buffer) {\n    memory_manager.FlushCaching();" in upload
    h=(stage/"include/video_core/memory_manager.h").read_text()
    assert "GpuDeferredWrite::Queue deferred_cpu_write_queue" in h
    dirty_h=(stage/"deferred-core/core/gpu_dirty_memory_manager.h").read_text()
    assert dirty_h.count("void Collect(PAddr address, size_t size) {") == 1
    assert "void Collect(PAddr address, size_t size) {\n        std::scoped_lock lk(guard);" in dirty_h
    assert "std::scoped_lock lk(guard);\n                    back_buffer.emplace_back(tmp);" not in dirty_h
    assert '#include "core/gpu_dirty_memory_manager.h"' in mm
print("NATIVE_GUEST_WRITE_BRIDGE_SOURCE_PASS default_off=1 dev_on_translations=6 no_runtime_enable=1")
