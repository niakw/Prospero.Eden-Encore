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
assert "ScopedGuestWriteOrigin" in replay and "guest_write_origin_core = previous" in replay
assert "enum class GuestWriteIntent { NoStore, StoreFollows };" in replay
assert "ScopedGuestStoreIntent" in replay
assert "guest_write_intent = previous;" in replay
assert "guest_write_intent = GuestWriteIntent::StoreFollows;" in replay
# Fail-closed runtime qualification, independent of any developer toggle.
assert "inline constexpr bool kNativePostStorePublicationReady = false;" in replay
assert code.count("::Eden::GpuDeferredWrite::kNativePostStorePublicationReady") == 2
assert code.index("!::Eden::GpuDeferredWrite::kNativePostStorePublicationReady") < code.index("deferred_cpu_write_queue.Enqueue(core, address, size)")
assert "const bool defer_candidate =\n        ::Eden::GpuDeferredWrite::kNativePostStorePublicationReady &&" in code
assert code.count("::Eden::GpuDeferredWrite::GuestWriteIntent::StoreFollows") == 2
assert "::Eden::GpuDeferredWrite::ScopedGuestStoreIntent store_intent;" in code
assert 'string(FIND "${bridge_cpu}" "${${anchor}}" found)' in code
assert 'string(FIND "${bridge_cpu}" "${NESTED_ANCHOR}" found)' not in code
# Fail-closed documentation contract: the inactive candidate does not yet
# synchronize deferred writes before either CPU-read fast path. Pin BOTH bypass
# sites so a future change must replace this negative proof with a real ordered
# read/drain qualification before runtime activation can be contemplated.
reader=(root/"vendor/sources/eden/src/core/memory.cpp").read_text()
download=reader.split("void HandleRasterizerDownload(",1)[1].split("void HandleRasterizerWrite(",1)[0]
assert download.index("if (current_area.start_address <= address") < download.index("system.GPU().OnCPURead(address, size)")
gpu_src=(root/"vendor/sources/eden/src/video_core/gpu.cpp").read_text()
gpu_read=gpu_src.split("VideoCore::RasterizerDownloadArea OnCPURead(",1)[1].split("void InvalidateRegion(",1)[0]
assert gpu_read.index("if (raster_area.preemtive)") < gpu_read.index("RequestSyncOperation(")
assert "FlushCaching(" not in gpu_read
assert "HandleRasterizerDownload" not in code
# Known unresolved publication hazard: guest writes can enqueue deferred GPU
# invalidations BEFORE the backing RAM write has occurred. A replay-completion
# ticket is NOT sufficient to assert the new payload has become visible.
# Pin the real source ordering until there is an explicit post-store publication
# protocol and a native read-fence qualification.
write_block=reader.split("bool WriteBlockImpl(",1)[1].split("bool ZeroBlock(",1)[0]
tracked_store=write_block.rsplit("HandleRasterizerWrite(GetInteger(current_vaddr), copy_amount);",1)[1]
assert "std::memcpy(ptr, reinterpret_cast<u8 const*>(buffer) + offset, copy_amount);" in tracked_store
zero_block=reader.split("bool ZeroBlock(",1)[1].split("bool CopyBlock(",1)[0]
assert zero_block.index("HandleRasterizerWrite(GetInteger(current_vaddr), copy_amount);") < zero_block.rindex("std::memset(ptr, 0, copy_amount);")
scalar_write=reader.split("inline void Write(Common::ProcessAddress vaddr,",1)[1].split("bool WriteExclusive(",1)[0]
assert scalar_write.index("HandleRasterizerWrite(addr, sizeof(T));") < scalar_write.index("std::memcpy(ptr, &data, sizeof(T));")
# Exhaustive dispatch-site audit in this pinned implementation. These paths
# cannot all be rewritten by patching WriteBlockImpl alone.
assert reader.count("HandleRasterizerWrite(") == 8
exclusive=reader.split("bool WriteExclusive(Common::ProcessAddress vaddr,",1)[1].split("void HandleRasterizerDownload(",1)[0]
assert exclusive.count("HandleRasterizerWrite(") == 2
assert "Common::AtomicCompareAndSwap(reinterpret_cast<T*>(ptr), data, expected)" in exclusive
assert "Common::AtomicCompareAndSwap(reinterpret_cast<u64*>(ptr), data, expected)" in exclusive
cache_ops=reader.split("Result StoreDataCache(",1)[1].split("void MarkRegionDebug(",1)[0]
assert "Result FlushDataCache(" in cache_ops
assert cache_ops.count("HandleRasterizerWrite(GetInteger(current_vaddr), block_size);") == 2
copy_block=reader.split("bool CopyBlock(",1)[1].split("template <typename Callback>",1)[0]
assert "WriteBlockImpl(dest_addr + offset, ptr, copy_amount, false)" in copy_block
assert "HandleRasterizerDownload(GetInteger(current_vaddr), copy_amount);" in copy_block
# These memory-side callbacks are NOT a complete proof of JIT/fastmem
# publication; the native candidate must remain unreachable.
# The host queue now exposes a completion model. It must not be mistaken for
# a native CPU-read barrier: the real reader still has no GPU-drain request.
queue=(root/"headless/gpu_deferred_write_queue.h").read_text()
for symbol in ("EnqueueTracked", "AcceptedSequence", "CompletedSequence",
               "DrainThrough", "WaitUntil", "Close"):
    assert symbol in queue, symbol
assert "return DrainThrough(target, std::forward<Replay>(replay));" in queue
assert "DrainThrough(Ticket target, Replay&& replay)" in queue
assert "target.generation != generation_" in queue
# Prevent cross-address-space ticket aliasing even when sequence and session
# counters align. The queue epoch generator is global to the process.
assert "static inline std::atomic<std::uint64_t> next_generation_{0};" in queue
assert "generation_{FreshGeneration()}" in queue
assert "generation_ = FreshGeneration();" in queue
assert "bool WaitUntil(Sequence sequence)" not in queue
assert "std::optional<Ticket> EnqueueTracked" in queue
# Bounded backlog counts accepted but UNACKNOWLEDGED sequence IDs, not
# vector entries: a GPU snapshot in progress and coalesced eager writes
# must both consume the budget. Rejected reservations require a safe
# synchronous producer fallback, never a silently lost invalidation.
assert "static constexpr Sequence MaxOutstandingWrites = 8192;" in queue
assert "std::optional<Ticket> ReserveOrdered(" in queue
ordered=queue.split("std::optional<Ticket> ReserveOrdered(",1)[1].split("// Host-only legacy publication",1)[0]
for guard in ("if (auto ticket = Reserve(core, address, size)) return ticket;",
              "if (accepted_ - completed_ < MaxOutstandingWrites) continue;",
              "barrier = {accepted_, generation_};",
              "++pending_wake_callbacks_;", "--pending_wake_callbacks_;",
              "if (!WaitUntil(barrier)) return std::nullopt;",
              "failed_ = true;"):
    assert guard in ordered, guard
assert ordered.index("barrier = {accepted_, generation_};") < ordered.index("RequestGpuOrThrow(request_gpu);")
assert ordered.index("RequestGpuOrThrow(request_gpu);") < ordered.index("WaitUntil(barrier)")
assert "deferred_cpu_write_queue.ReserveOrdered(" not in code
assert "CommitPostStore(" not in code
assert "accepted_ - completed_ >= MaxOutstandingWrites" in queue
# Publishing thousands of reservations out of order must not turn the FIFO
# into a quadratic per-frame CPU hotspot. Last-sequence keys are monotone
# across tail merges and prefix drains, allowing log-time lookup.
publish_body=queue.split("std::optional<bool> PublishImpl(Ticket ticket, bool arm_wake = false, bool cancel = false) {",1)[1].split("static std::uint64_t FreshGeneration()",1)[0]
assert "std::lower_bound(" in publish_body
assert "write.last_sequence < sequence" in publish_body
assert "entry->last_sequence != ticket.sequence" in publish_body
# A post-store producer must wake the GPU when a previously blocked FIFO head
# first becomes replayable. RequestGpu runs OUTSIDE the queue mutex, so a
# synchronous callback can acquire the queue and renderer locks safely.
notify_body=queue.split("bool ResolveAndWake(Ticket ticket, bool cancel, RequestGpu&& request_gpu) {",1)[1].split("// Returning true means a blocked/unready FIFO head",1)[0]
assert "PublishImpl(ticket, true, cancel)" in notify_body
assert "return ResolveAndWake(ticket, false, std::forward<RequestGpu>(request_gpu));" in queue
assert "return ResolveAndWake(ticket, true, std::forward<RequestGpu>(request_gpu));" in queue
assert "RequestGpuOrThrow(std::forward<RequestGpu>(request_gpu));" in notify_body
request_guard=queue.split("static void RequestGpuOrThrow(RequestGpu&& request_gpu) {",1)[1].split("bool ResolveAndWake(",1)[0]
assert "std::is_same_v<std::invoke_result_t<RequestGpu>, bool>" in request_guard
assert "if (!std::forward<RequestGpu>(request_gpu)())" in request_guard
assert "throw std::runtime_error" in request_guard
assert "std::forward<RequestGpu>(request_gpu)();" in request_guard
assert "failed_ = true;" in notify_body and "throw;" in notify_body
assert "const bool became_ready = !was_ready && !queue_.empty()" in publish_body
assert "if (arm_wake && became_ready) ++pending_wake_callbacks_;" in publish_body
assert "std::optional<bool> PublishImpl(Ticket ticket, bool arm_wake = false, bool cancel = false)" in queue
assert "entry->cancelled = cancel;" in publish_body
assert "tail.published && !tail.cancelled && tail.core == core" in queue
assert "bool Cancel(Ticket ticket)" in queue
assert "bool CancelAndWake(Ticket ticket, RequestGpu&& request_gpu)" in queue
assert "wake_cv_.wait(lock, [&] { return pending_wake_callbacks_ == 0; });" in queue
assert "pending_wake_callbacks_ != 0" in queue
assert "active_wake_callback_ == this" in queue
assert "active_wake_callback_ = this;" in notify_body
assert "deferred_cpu_write_queue.PublishAndWake(" not in code
assert "deferred_cpu_write_queue.CancelAndWake(" not in code
# Shutdown must be a replay-lifetime barrier, not just a waiter wake-up.
# Without this, the GPU callback can still touch freed rasterizer resources.
close_body=queue.split("void Close() {",1)[1].split("bool ResetAfterQuiescence()",1)[0]
assert close_body.index("closed_ = true;") < close_body.index("std::lock_guard owner(consumer_mutex_);")
assert "completed_cv_.notify_all()" in close_body
assert "if (active_consumer_ == this || active_wake_callback_ == this)" in close_body
drain_body=queue.split("std::uint64_t DrainThrough(Ticket target, Replay&& replay)",1)[1].split("std::uint64_t Drain(Replay&& replay)",1)[0]
assert "std::unique_lock owner(consumer_mutex_);" in drain_body
assert "if (item.cancelled) continue;" in drain_body
assert "return replayed;" in drain_body
assert "if (closed_ || failed_ || target.generation != generation_" in drain_body
# A thrown rasterizer callback has potentially non-atomic side effects.
# Never let the queue acknowledge, retry or accept fresh work after failure.
assert "catch (...)" in drain_body
assert drain_body.index("failed_ = true;") < drain_body.index("throw;")
assert "bool Failed() const" in queue
assert "closed_ || failed_ || ticket.generation != generation_" in queue
assert "completed_ >= ticket.sequence || closed_ || failed_" in queue
# A title that is closing or poisoned must never return a successful read,
# even when its GPU callback previously acknowledged the ticket's watermark.
wait_body=queue.split("bool WaitUntil(Ticket ticket) {",1)[1].split("std::uint64_t DrainThrough(",1)[0]
assert "return !closed_ && !failed_ && generation_ == ticket.generation" in wait_body
assert "if (closed_ || failed_ || accepted_" in queue
assert "failed_ = false;" in queue
# Reset is destructive: it must not race any GPU callback or reopen a live
# title merely because producers have momentarily become idle.
reset_body=queue.split("bool ResetAfterQuiescence() {",1)[1].split("private:",1)[0]
assert reset_body.index("std::lock_guard owner(consumer_mutex_);") < reset_body.index("std::lock_guard lock(mutex_);")
assert "if (active_consumer_ == this) return false;" in reset_body
assert "if (!closed_ || !close_completed_ || pending_wake_callbacks_ != 0)" in reset_body
assert reset_body.index("if (!closed_ || !close_completed_ || pending_wake_callbacks_ != 0)") < reset_body.index("queue_.clear();")
assert "close_completed_ = false;" in queue
assert "close_completed_ = true;" in close_body
assert close_body.index("std::lock_guard owner(consumer_mutex_);") < close_body.index("close_completed_ = true;")
assert "completed_cv_.notify_all()" in queue
assert "WaitUntil(" not in code
# The host candidate now has a publish-after-store contract; the real bridge
# still uses eager Enqueue and must NOT be presented as correctly integrated.
for symbol in ("struct Ticket", "Reserve(", "Publish(Ticket", "WaitUntil(Ticket",
               "generation_", "queue_[ready].published"):
    assert symbol in queue, symbol
assert "deferred_cpu_write_queue.Enqueue(core, address, size)" in code
# A GPU replay exception poisons the session; even if upstream catches it,
# no later native command may silently proceed through FlushCaching().
assert "if (deferred_cpu_write_queue.Failed()) std::terminate();" in code
assert code.index("if (deferred_cpu_write_queue.Failed()) std::terminate();") < code.index("if (deferred_cpu_write_queue.Pending())")

assert "deferred_cpu_write_queue.Reserve(" not in code
assert "deferred_cpu_write_queue.Publish(" not in code
assert "cpu_write_defer{false}" in perf
for signature in (
    "EnqueueDeferredCPUWrite",
    "ScopedGuestWriteOrigin guest_origin",
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
    (stage/"memory-ps5.cpp").write_bytes((root/"vendor/sources/eden/src/core/memory.cpp").read_bytes())
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
set_property(TARGET core PROPERTY SOURCES "@{PORT_BUILD_DIR}/memory-ps5.cpp")
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
    guest=(stage/"memory-ps5-deferred.cpp").read_text()
    assert guest.count("ScopedGuestWriteOrigin guest_origin") == 1
    assert guest.count("ScopedGuestStoreIntent store_intent;") == 5
    block=guest.split("bool WriteBlockImpl(",1)[1].split("bool ZeroBlock(",1)[0]
    assert block.index("ScopedGuestStoreIntent store_intent;") < block.index("HandleRasterizerWrite(")
    zero=guest.split("bool ZeroBlock(",1)[1].split("bool CopyBlock(",1)[0]
    assert zero.index("ScopedGuestStoreIntent store_intent;") < zero.index("HandleRasterizerWrite(")
    scalar=guest.split("inline void Write(Common::ProcessAddress vaddr,",1)[1].split("bool WriteExclusive(",1)[0]
    assert scalar.count("ScopedGuestStoreIntent store_intent;") == 1
    exclusive=guest.split("bool WriteExclusive(Common::ProcessAddress vaddr,",1)[1].split("void HandleRasterizerDownload(",1)[0]
    assert exclusive.count("ScopedGuestStoreIntent store_intent;") == 2
    maintenance=guest.split("Result StoreDataCache(",1)[1].split("void MarkRegionDebug(",1)[0]
    assert maintenance.count("HandleRasterizerWrite(") == 2
    assert "ScopedGuestStoreIntent store_intent;" not in maintenance
    assert "guest_write_intent" in vk and "guest_write_intent" in mm
    assert "system.GPU().OnCPUWrite(address, size)" in guest
    assert "GetCurrentHostThreadID()" not in mm.split("bool MemoryManager::EnqueueDeferredCPUWrite",1)[1].split("void MemoryManager::FlushCaching",1)[0]
    assert "guest_write_origin_core" in mm
    assert "guest_write_origin_core < ::Eden::GpuDeferredWrite::Queue::Cores" in vk
    dirty_h=(stage/"deferred-core/core/gpu_dirty_memory_manager.h").read_text()
    assert dirty_h.count("void Collect(PAddr address, size_t size) {") == 1
    assert "void Collect(PAddr address, size_t size) {\n        std::scoped_lock lk(guard);" in dirty_h
    assert "std::scoped_lock lk(guard);\n                    back_buffer.emplace_back(tmp);" not in dirty_h
    assert '#include "core/gpu_dirty_memory_manager.h"' in mm
    # Compile the generated (not hand-reimplemented) GPU-dirty collector
    # against a minimal pinned-page-size shim under ASan and UBSan.
    stub=stage/"fixture/core"
    stub.mkdir(parents=True,exist_ok=True)
    (stub/"device_memory_manager.h").write_text(
        "#pragma once\n#include <cstddef>\n#include <cstdint>\n"
        "using PAddr = std::uint64_t;\nusing u32 = std::uint32_t;\n"
        "using u64 = std::uint64_t;\n"
        "namespace Core { inline constexpr std::size_t DEVICE_PAGEBITS = 12; }\n"
    )
    stress = r'''
#include "core/gpu_dirty_memory_manager.h"
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <functional>
#include <thread>
#include <vector>
int main() {
    static constexpr unsigned Cores=4, Writes=400;
    Core::GPUDirtyMemoryManager dirty;
    std::array<std::atomic<bool>,Cores> finished{};
    std::vector<unsigned char> seen(Cores*Writes,0);
    auto receive = [&](PAddr a, std::size_t length) {
        assert(a>=2048 && a%2048==0 && length==64);
        const auto index=a/2048-1;
        assert(index<seen.size());
        ++seen[index];
    };
    std::function<void(PAddr,std::size_t)> callback=receive;
    std::vector<std::thread> writers;
    for(unsigned core=0;core<Cores;++core) writers.emplace_back([&,core] {
        for(unsigned i=0;i<Writes;++i) {
            const auto address=std::uint64_t(core*Writes+i+1)*2048;
            dirty.Collect(address,64);
            if((i%11)==0) std::this_thread::yield();
        }
        finished[core].store(true,std::memory_order_release);
    });
    while(true) {
        dirty.Gather(callback);
        bool all=true;
        for(auto& done:finished) all &= done.load(std::memory_order_acquire);
        if(all) break;
        std::this_thread::yield();
    }
    for(auto& w:writers) w.join();
    dirty.Gather(callback);
    for(unsigned i=0;i<seen.size();++i) assert(seen[i]!=0);

    // Same-region disjoint writes must union their 64-byte dirty masks.
    Core::GPUDirtyMemoryManager blocks;
    std::vector<std::thread> union_writers;
    for(unsigned c=0;c<4;++c) union_writers.emplace_back([&,c] {
        for(unsigned j=0;j<8;++j) blocks.Collect(0x200000+c*512+j*64,64);
    });
    for(auto& w:union_writers) w.join();
    std::vector<std::pair<PAddr,std::size_t>> combined;
    std::function<void(PAddr,std::size_t)> union_callback =
        [&](PAddr a,std::size_t n){combined.emplace_back(a,n);};
    blocks.Gather(union_callback);
    assert(combined.size()==1);
    assert(combined[0].first==0x200000 && combined[0].second==2048);
}
'''
    cpp=stage/"dirty_collector_stress.cpp"
    binary=stage/"dirty_collector_stress"
    cpp.write_text(stress)
    subprocess.run(["clang++","-std=c++20","-O1","-g","-pthread",
                    "-Wall","-Wextra","-Werror","-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all",
                    "-I",str(stage/"deferred-core"),"-I",str(stage/"fixture"),
                    str(cpp),"-o",str(binary)],
                   check=True,timeout=45)
    subprocess.run([str(binary)],check=True,timeout=45)
    print("DEFERRED_GPU_DIRTY_STRESS_PASS producers=4 regions=1600 live_gather=1 mask_union=32")

print("NATIVE_GUEST_WRITE_BRIDGE_SOURCE_PASS default_off=1 dev_on_translations=6 no_runtime_enable=1")
