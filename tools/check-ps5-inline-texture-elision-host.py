#!/usr/bin/env python3
"""Native-source-extracted inline GPU upload texture lock regression.

The CPU buffer tracker, guest memory write, query and shader invalidation
must follow the conservative texture and buffer ownership witnesses.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
main = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
bridge = (root / "vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp").read_text()
pinned = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
oracle = (root / "tools/prepare-vulkan-port.py").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
texture = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
buffer = (root / "vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h").read_text()
anchor = "void RasterizerVulkan::AccelerateInlineToMemory("
last = "\nstd::optional<FramebufferTextureInfo> RasterizerVulkan::AccelerateDisplay("
def extract(text: str) -> str:
    assert text.count(anchor) == 1
    begin = text.index(anchor)
    end = text.index(last, begin)
    return text[begin:end]
body = extract(main)
old = extract(pinned)
assert body == extract(bridge), "inactive Vulkan bridge drifted from active C++"
assert body != old
assert body.count("::Eden::ImagePages::NeverHeld(*cpu_addr, copy_size)") == 1
assert "if (!::Eden::ImagePages::NeverHeld(*cpu_addr, copy_size)) {" in body
assert body.index("gpu_memory->WriteBlockUnsafe(") < body.index("buffer_cache.InlineMemory(")
assert body.index("buffer_cache.WriteMemory(") < body.index("::Eden::ImagePages::NeverHeld(")
assert body.index("::Eden::ImagePages::NeverHeld(") < body.index("texture_cache.WriteMemory(")
assert body.index("texture_cache.WriteMemory(") < body.index("pipeline_cache.InvalidateRegion(")
assert body.index("pipeline_cache.InvalidateRegion(") < body.index("query_cache.InvalidateRegion(")
assert "memory_tracker.MarkRegionAsCpuModified(device_addr, size);" in buffer
assert "ForEachImageInRegion(cpu_addr, size" in texture
assert oracle.count("Conservative native inline-upload texture lock elision") == 1
assert "python3 -B tools/check-ps5-inline-texture-elision-host.py" in workflow

program = r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <span>
#include <vector>
#include "image_pages.h"
#include "buffer_pages.h"
using u8 = std::uint8_t;
using DAddr = std::uint64_t;
using GPUVAddr = std::uint64_t;
struct CountingMutex {
    std::recursive_mutex mutex;
    unsigned calls{};
    void lock() { mutex.lock(); ++calls; }
    void unlock() { mutex.unlock(); }
};
struct MockGpuMemory {
    std::optional<DAddr> cpu{std::nullopt};
    unsigned safe_writes{};
    unsigned unsafe_writes{};
    std::optional<DAddr> GpuToCpuAddress(GPUVAddr) { return cpu; }
    void WriteBlock(GPUVAddr, const u8*, std::size_t) { ++safe_writes; }
    void WriteBlockUnsafe(GPUVAddr, const u8*, std::size_t) { ++unsafe_writes; }
};
struct MockBufferCache {
    std::recursive_mutex mutex;
    bool handled{};
    unsigned inlines{};
    unsigned writes{};
    bool InlineMemory(DAddr, std::size_t, std::span<const u8>) {
        ++inlines;
        return handled;
    }
    void WriteMemory(DAddr, std::size_t) { ++writes; }
};
struct MockTextureCache {
    CountingMutex mutex;
    unsigned writes{};
    void WriteMemory(DAddr, std::size_t) { ++writes; }
};
struct MockInvalidations {
    unsigned calls{};
    void InvalidateRegion(DAddr, std::size_t) { ++calls; }
};
class RasterizerVulkan {
public:
    MockGpuMemory backing;
    MockGpuMemory* gpu_memory{&backing};
    MockBufferCache buffer_cache;
    MockTextureCache texture_cache;
    MockInvalidations pipeline_cache, query_cache;
    void AccelerateInlineToMemory(GPUVAddr, std::size_t, std::span<const u8>);
};
__REAL_METHOD__
int main() {
    RasterizerVulkan x;
    constexpr DAddr page = 4096;
    std::array<u8, 16> small{};
    x.backing.cpu = 10*page;
    // No prior texture OR buffer ownership: only guest RAM/shader/query update.
    x.AccelerateInlineToMemory(42, small.size(), small);
    assert(x.backing.unsafe_writes == 1 && x.buffer_cache.inlines == 0);
    assert(x.buffer_cache.writes == 0 && x.texture_cache.writes == 0);
    assert(x.texture_cache.mutex.calls == 0);
    assert(x.pipeline_cache.calls == 1 && x.query_cache.calls == 1);

    // An inline buffer upload returning handled still invalidates texture
    // and shader/query if a texture was ever registered.
    Eden::ImagePages::Mark(20*page, page);
    Eden::BufferPages::Mark(20*page, page);
    x.backing.cpu = 20*page;
    x.buffer_cache.handled = true;
    x.AccelerateInlineToMemory(42, small.size(), small);
    assert(x.buffer_cache.writes == 0 && x.buffer_cache.inlines == 1);
    assert(x.texture_cache.writes == 1 && x.texture_cache.mutex.calls == 1);
    assert(x.pipeline_cache.calls == 2 && x.query_cache.calls == 2);

    // Registered overlap is conservatively retained.
    x.backing.cpu = 20*page-1;
    x.buffer_cache.handled = false;
    x.AccelerateInlineToMemory(42, small.size(), small);
    assert(x.texture_cache.writes == 2 && x.texture_cache.mutex.calls == 2);
    assert(x.buffer_cache.writes == 1);

    // Large requests fail closed even when no pages were registered.
    std::vector<u8> large(256*1024+1);
    x.backing.cpu = 100*page;
    x.AccelerateInlineToMemory(42, large.size(), large);
    assert(x.texture_cache.writes == 3 && x.texture_cache.mutex.calls == 3);
    assert(x.buffer_cache.writes == 2);

    // Unknown/out-of-range CPU spans conservatively lock.
    x.backing.cpu = Eden::ImagePages::kSpace-4;
    x.AccelerateInlineToMemory(42, small.size(), small);
    assert(x.texture_cache.writes == 4 && x.texture_cache.mutex.calls == 4);
    assert(x.buffer_cache.writes == 3);

    // Translation failure still uses original safe guest block, then returns.
    x.backing.cpu = std::nullopt;
    x.AccelerateInlineToMemory(42, small.size(), small);
    assert(x.backing.safe_writes == 1 && x.backing.unsafe_writes == 5);
    assert(x.buffer_cache.inlines == 4 && x.buffer_cache.writes == 3);
    assert(x.texture_cache.writes == 4);
    assert(x.pipeline_cache.calls == 5 && x.query_cache.calls == 5);
}
""".replace("__REAL_METHOD__", body)
compiler = shutil.which("clang++-18") or shutil.which("clang++")
assert compiler, "Clang required for ASan/UBSan C++ method test"
with tempfile.TemporaryDirectory(prefix="encore-inline-texture-elision-") as tmp:
    source, binary = Path(tmp)/"inline.cpp", Path(tmp)/"test"
    source.write_text(program)
    subprocess.run([compiler, "-std=c++20", "-O1", "-pthread", "-Wall",
                    "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-I"+str(root/"headless"),
                    str(source), "-o", str(binary)], check=True, timeout=55)
    subprocess.run([str(binary)], check=True, timeout=20)
print("VULKAN_INLINE_TEXTURE_ELISION_HOST_PASS real_method=1 never_owned_skip=1 "
      "registered_overlap=1 oversized=1 unknown=1 translation_fail=1 "
      "buffer_shader_query_kept=1 asan_ubsan=1")
