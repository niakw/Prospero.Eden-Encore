#!/usr/bin/env python3
"""F07 T04: source-extracted native MSAA upload scratch retirement on exceptions.

A checked-out image has tick UINT64_MAX. A failed upload after Acquire must
release it at CurrentTick (never immediately free for a still-pending GPU
command). Desktop keeps its original normal path. This is host-only proof.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "vendor/encore-active/eden-vulkan/vk_texture_cache_cost.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
begin = "        const VkImage temp_vk_image = runtime->AcquireMsaaScratchImage(image_ci);"
end = "\n        auto vk_copies = TransformBufferImageCopies("
start = source.index("void Image::UploadMemory(VkBuffer buffer,")
method = source[start:source.index("\nvoid Image::", start + 5)]
assert method.count(begin) == 1
guard = method[method.index(begin):method.index(end, method.index(begin))]
assert "#ifdef PS5_NATIVE\n        // An allocation" in guard
assert guard.count("SCOPE_EXIT {") == 1
assert guard.count("if (!scratch_released) runtime->ReleaseMsaaScratchImage(temp_vk_image);") == 1
assert "common/scope_exit.h" in source
finish = "        initialized = true;\n        runtime->ReleaseMsaaScratchImage(temp_vk_image);"
assert method.count(finish) == 1
normal = method[method.index(finish):method.index("\n        if (is_rescaled)", method.index(finish))]
assert "scratch_released = true;" in normal
assert "F07 MSAA upload scratch exception safe release" in generator
assert "F07 MSAA upload scratch normal release unchanged" in generator
assert "F07 MSAA scratch failure-guard include" in generator
assert guard in generator and normal in generator

cpp = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <utility>
using u64 = std::uint64_t;
using VkImage = int;
struct VkImageCreateInfo {};
struct ScopeTag {};
template<class F> struct ScopeExit {
    F fn;
    ~ScopeExit() { fn(); }
};
template<class F> ScopeExit<std::decay_t<F>> operator+(ScopeTag, F&& fn) {
    return {std::forward<F>(fn)};
}
#define SCOPE_EXIT auto guard = ScopeTag{} + [&]
struct Scheduler {
    u64 tick = 21;
    bool reject_preflight{};
    int prepare_calls{};
    u64 CurrentTick() const { return tick; }
    void RequestOutsideRenderPassOperationContext() {
        ++prepare_calls;
        if (reject_preflight) throw std::runtime_error("mock rejected preflight");
    }
};
struct Runtime {
    Scheduler& scheduler;
    u64 tick = (std::numeric_limits<u64>::max)();
    u64 completed_tick = 20;
    int acqs{}, releases{}, handle{41};
    VkImage AcquireMsaaScratchImage(const VkImageCreateInfo&) {
        ++acqs;
        tick = (std::numeric_limits<u64>::max)();
        return handle;
    }
    void ReleaseMsaaScratchImage(VkImage img) {
        assert(img == handle);
        ++releases;
        tick = scheduler.CurrentTick();
    }
    bool CanReuse() const {
        return tick <= completed_tick;
    }
};
struct Image {
    Runtime* runtime;
    Scheduler* scheduler;
    bool initialized{};
    void Upload(bool reject_after_record) {
        const VkImageCreateInfo image_ci{};
        const bool is_rescaled = false;
__SOURCE_GUARD__
        if (reject_after_record)
            throw std::runtime_error("mock GPU command failed after enqueue");
__SOURCE_RELEASE__
        (void)is_rescaled;
    }
};
int main() {
    {
        Scheduler scheduler;
        Runtime runtime{scheduler};
        Image image{&runtime, &scheduler};
        image.Upload(false);
        assert(image.initialized && runtime.acqs == 1 && runtime.releases == 1);
        assert(runtime.tick == 21 && !runtime.CanReuse());
        runtime.completed_tick = 21;
        assert(runtime.CanReuse());
    }
    for (const bool before_enqueue : {true, false}) {
        Scheduler scheduler;
        scheduler.reject_preflight = before_enqueue;
        Runtime runtime{scheduler};
        Image image{&runtime, &scheduler};
        bool threw = false;
        try { image.Upload(!before_enqueue); }
        catch (const std::runtime_error&) { threw = true; }
        assert(threw && !image.initialized && runtime.acqs == 1);
#ifdef PS5_NATIVE
        assert(runtime.releases == 1 && runtime.tick == 21);
        assert(!runtime.CanReuse());
        runtime.completed_tick = 21;
        assert(runtime.CanReuse());
#else
        // Desktop path deliberately unchanged by this native-only fix.
        assert(runtime.releases == 0);
#endif
    }
    std::puts("F07_MSAA_UPLOAD_RETIRE_HOST_PASS");
}
""".replace("__SOURCE_GUARD__", guard).replace("__SOURCE_RELEASE__", normal)
compiler = shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 host compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-msaa-scratch-retire-") as d:
    src = Path(d) / "scratch.cpp"
    src.write_text(cpp)
    for mode in ("native", "desktop"):
        for opt in ("-O0", "-O2"):
            exe = Path(d) / (mode + opt)
            command = [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                       "-fsanitize=undefined", "-fno-sanitize-recover=all"]
            if mode == "native":
                command += ["-DPS5_NATIVE"]
            command += [str(src), "-o", str(exe)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            assert result.returncode == 0, (mode, opt, result.stderr[-5000:])
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (mode, opt, result.stderr[-5000:])
            assert "F07_MSAA_UPLOAD_RETIRE_HOST_PASS" in result.stdout
            print("F07_MSAA_UPLOAD_RETIRE_HOST_PASS", mode, opt)


# Same failure must be tested for MSAA readback, which reserves and releases
# the identical scratch pool. A partially enqueued command can own the
# returned tick; neither failure may instantly recycle the Vulkan image.
readback_at = source.index("void Image::DownloadMemory(std::span<VkBuffer> buffers_span,")
readback = source[readback_at:]
read_begin = "            const VkImage temp_vk_image = runtime->AcquireMsaaScratchImage(image_ci);"
read_end = "\n            const VkImageAspectFlags temp_aspect_mask = aspect_mask;"
assert readback.count(read_begin) == 1
read_guard = readback[readback.index(read_begin):readback.index(read_end)]
read_normal_begin = "            runtime->ReleaseMsaaScratchImage(temp_vk_image);"
read_normal_end = "\n        }\n        if (is_rescaled) {"
assert readback.count(read_normal_end) == 1
read_normal = readback[
    readback.index(read_normal_begin):readback.index(
        read_normal_end, readback.index(read_normal_begin)
    )
]
assert "SCOPE_EXIT {" in read_guard
assert "scratch_released = true;" in read_normal
assert "F07 MSAA download scratch failure release" in generator
assert "F07 MSAA download scratch success release unchanged" in generator
assert read_guard in generator and read_normal in generator

read_cpp = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <utility>
using u64 = std::uint64_t;
using VkImage = int;
struct VkImageCreateInfo {};
struct ScopeTag {};
template<class F> struct ScopeExit {
    F fn;
    ~ScopeExit() { fn(); }
};
template<class F> ScopeExit<std::decay_t<F>> operator+(ScopeTag, F&& fn) {
    return {std::forward<F>(fn)};
}
#define SCOPE_EXIT auto guard = ScopeTag{} + [&]
struct Scheduler {
    u64 tick = 21;
    u64 CurrentTick() const { return tick; }
};
struct Runtime {
    Scheduler& scheduler;
    u64 tick = (std::numeric_limits<u64>::max)();
    u64 completed_tick = 20;
    unsigned acquired{}, released{};
    VkImage AcquireMsaaScratchImage(const VkImageCreateInfo&) {
        ++acquired;
        tick = (std::numeric_limits<u64>::max)();
        return 41;
    }
    void ReleaseMsaaScratchImage(VkImage value) {
        assert(value == 41);
        ++released;
        tick = scheduler.CurrentTick();
    }
    bool CanReuse() const { return tick <= completed_tick; }
};
struct Image {
    Runtime* runtime;
    Scheduler* scheduler;
    void Download(bool throw_during_staging, bool throw_after_gpu_enqueue) {
        const VkImageCreateInfo image_ci{};
__READBACK_GUARD__
        if (throw_during_staging) throw std::runtime_error("mock staging");
        if (throw_after_gpu_enqueue) {
            scheduler->tick = 22;
            throw std::runtime_error("mock command enqueue");
        }
__READBACK_RELEASE__
    }
};
int main() {
    {
        Scheduler scheduler;
        Runtime runtime{scheduler};
        Image image{&runtime, &scheduler};
        image.Download(false, false);
        assert(runtime.acquired == 1 && runtime.released == 1);
        assert(runtime.tick == 21 && !runtime.CanReuse());
    }
    for (const bool after_enqueue : {false, true}) {
        Scheduler scheduler;
        Runtime runtime{scheduler};
        Image image{&runtime, &scheduler};
        bool threw = false;
        try { image.Download(!after_enqueue, after_enqueue); }
        catch (const std::runtime_error&) { threw = true; }
        assert(threw && runtime.acquired == 1);
#ifdef PS5_NATIVE
        assert(runtime.released == 1 && runtime.tick == (after_enqueue ? 22u : 21u));
        assert(!runtime.CanReuse());
        runtime.completed_tick = runtime.tick;
        assert(runtime.CanReuse());
#else
        assert(runtime.released == 0);
#endif
    }
    std::puts("F07_MSAA_READBACK_RETIRE_HOST_PASS");
}
""".replace("__READBACK_GUARD__", read_guard).replace(
    "__READBACK_RELEASE__", read_normal)
with tempfile.TemporaryDirectory(prefix="eden-f07-msaa-readback-retire-") as d:
    src = Path(d) / "readback.cpp"
    src.write_text(read_cpp)
    for mode in ("native", "desktop"):
        for opt in ("-O0", "-O2"):
            exe = Path(d) / (mode + opt)
            command = [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                       "-fsanitize=undefined", "-fno-sanitize-recover=all"]
            if mode == "native":
                command += ["-DPS5_NATIVE"]
            command += [str(src), "-o", str(exe)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            assert result.returncode == 0, (mode, opt, result.stderr[-5000:])
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (mode, opt, result.stderr[-5000:])
            assert "F07_MSAA_READBACK_RETIRE_HOST_PASS" in result.stdout
            print("F07_MSAA_READBACK_RETIRE_HOST_PASS", mode, opt)


# The scratch pool itself must reject a null VkImage before the vector grows.
# Compile its exact source method: a null image is not a valid cached candidate.
acquire_begin = "VkImage TextureCacheRuntime::AcquireMsaaScratchImage(const VkImageCreateInfo& image_ci) {"
acquire_end = "\nvoid TextureCacheRuntime::ReleaseMsaaScratchImage("
assert source.count(acquire_begin) == source.count(acquire_end) == 1
acquire_body = source[source.index(acquire_begin):source.index(acquire_end)]
assert "if (!scratch.image) {" in acquire_body
assert "throw std::bad_alloc{};" in acquire_body
assert acquire_body.index("if (!scratch.image)") < acquire_body.index(
    "msaa_scratch_images.push_back(std::move(scratch))"
)
assert "F07 MSAA null scratch image rejected before caching" in generator
assert "#ifdef PS5_NATIVE\n    // Some allocation backends report failure" in acquire_body
# The generator stores strict reviewed deltas, not the entire method.
null_block_begin = "    MsaaScratchImage scratch{"
null_block_end = "    const VkImage handle = *scratch.image;"
null_block = acquire_body[
    acquire_body.index(null_block_begin):
    acquire_body.index(null_block_end) + len(null_block_end)
]
assert null_block in generator

pool_cpp = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <new>
#include <utility>
#include <vector>
using u64 = std::uint64_t;
using u32 = std::uint32_t;
using VkImage = int;
struct Extent {
    u32 width{}, height{}, depth{};
};
struct VkImageCreateInfo {
    int format{}, imageType{};
    Extent extent{64,64,1};
    u32 mipLevels{1}, arrayLayers{1}, usage{7}, flags{};
};
struct MsaaScratchKey {
    int format{}, type{};
    u32 width{}, height{}, depth{}, levels{}, layers{}, usage{}, flags{};
    bool operator==(const MsaaScratchKey&) const = default;
};
struct MockVkImage {
    int handle{};
    explicit operator bool() const noexcept { return handle != 0; }
    VkImage operator*() const noexcept { return handle; }
};
struct MsaaScratchImage {
    MsaaScratchKey key{};
    MockVkImage image{};
    u64 tick{};
    u32 unused_frames{};
};
struct MemoryAllocator {
    bool fail{};
    int next_handle{11};
    MockVkImage CreateImage(const VkImageCreateInfo&) {
        return MockVkImage{fail ? 0 : next_handle++};
    }
};
struct MasterSemaphore {
    u64 completed_tick{20};
    int queries{};
    u64 KnownGpuTick() { ++queries; return completed_tick; }
};
struct Scheduler {
    MasterSemaphore semaphore;
    MasterSemaphore& GetMasterSemaphore() { return semaphore; }
    bool IsFree(u64 tick) { return tick <= semaphore.completed_tick; }
};
struct TextureCacheRuntime {
    MemoryAllocator memory_allocator;
    Scheduler scheduler;
    std::vector<MsaaScratchImage> msaa_scratch_images;
    VkImage AcquireMsaaScratchImage(const VkImageCreateInfo&);
};
__ACTUAL_ACQUIRE__
int main() {
    {
        TextureCacheRuntime r;
        VkImageCreateInfo ci;
        assert(r.AcquireMsaaScratchImage(ci) == 11);
        assert(r.msaa_scratch_images.size() == 1);
        assert(r.AcquireMsaaScratchImage(ci) == 12);
        assert(r.msaa_scratch_images.size() == 2);
        r.msaa_scratch_images[0].tick = 21;
        assert(r.AcquireMsaaScratchImage(ci) == 13); // old tick still in flight
        r.scheduler.semaphore.completed_tick = 21;
        assert(r.AcquireMsaaScratchImage(ci) == 11); // now safely recyclable
        assert(r.msaa_scratch_images.size() == 3);
    }
    {
        TextureCacheRuntime r;
        VkImageCreateInfo ci;
        r.memory_allocator.fail = true;
#ifdef PS5_NATIVE
        bool rejected = false;
        try { (void)r.AcquireMsaaScratchImage(ci); }
        catch (const std::bad_alloc&) { rejected = true; }
        assert(rejected && r.msaa_scratch_images.empty());
#else
        // Desktop retains the pinned null-handling semantics.
        assert(r.AcquireMsaaScratchImage(ci) == 0);
        assert(r.msaa_scratch_images.size() == 1);
#endif
    }
    std::puts("F07_MSAA_SCRATCH_NULL_GUARD_PASS");
}
""".replace("__ACTUAL_ACQUIRE__", acquire_body)
with tempfile.TemporaryDirectory(prefix="eden-f07-msaa-scratch-pool-") as d:
    src = Path(d) / "pool.cpp"
    src.write_text(pool_cpp)
    for mode in ("native", "desktop"):
        for opt in ("-O0", "-O2"):
            exe = Path(d) / (mode + opt)
            command = [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                       "-fsanitize=undefined", "-fno-sanitize-recover=all"]
            if mode == "native":
                command += ["-DPS5_NATIVE"]
            command += [str(src), "-o", str(exe)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            assert result.returncode == 0, (mode, opt, result.stderr[-5000:])
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (mode, opt, result.stderr[-5000:])
            assert "F07_MSAA_SCRATCH_NULL_GUARD_PASS" in result.stdout
            print("F07_MSAA_SCRATCH_NULL_GUARD_PASS", mode, opt)
