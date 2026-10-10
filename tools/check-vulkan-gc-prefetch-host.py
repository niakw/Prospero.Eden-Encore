#!/usr/bin/env python3
"""Host-bound C++ test of the literal PS5 Vulkan GC prefetch capacity and byte cap.

The real pinned Vulkan staging ref is a copyable NON-OWNING POD descriptor;
pool entries, not map destructors, own deferred GPU resources. Mock only the
driver, execute actual production container declaration and admission
predicate. No PS5 native renderer/device or measured FPS.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
gc = (root / "headless/vulkan_gc_downloads.inc").read_text(encoding="utf-8")
generator = (root / "tools/prepare-vulkan-port.py").read_text(encoding="utf-8")
assert "(port / 'vulkan_gc_downloads.inc').read_text()" in generator
start = gc.index("    using DownloadMap = decltype(runtime.DownloadStagingBuffer(size_t{}));")
end = gc.index(" gc_downloads;", start) + len(" gc_downloads;")
declaration = gc[start:end]
assert "constexpr size_t gc_prefetch_limit = 40;" in declaration
assert "small_vector<std::pair<ImageId, DownloadMap>, gc_prefetch_limit>" in declaration
assert gc.count("gc_downloads.size() == gc_prefetch_limit") == 1
assert gc.count("32_MiB - bytes") == 1
assert "if (frame_tick < ticks_to_destroy) return;" in gc
# Skip ALL LRU lookahead if pressure policy forbids staged dirty downloads.
# Cleanup still executes and can reclaim old clean images.
prefetch_body = gc[gc.index("    const auto PrefetchDownloads = [&] {"):gc.index("    const auto UsePrefetched = [&]")]
assert "const bool prefetch_dirty = DirtyEvictions();" in prefetch_body
assert "if (!prefetch_dirty) return;" in prefetch_body
assert prefetch_body.index("if (frame_tick < ticks_to_destroy) return;") < prefetch_body.index("const bool prefetch_dirty = DirtyEvictions();")
assert prefetch_body.index("if (!prefetch_dirty) return;") < prefetch_body.index("lru_cache.ForEachItemBelow(")
assert prefetch_body.count("::Eden::Performance::KeepDirtyTextures()") == 1
assert "return usage < projected_stop;" in prefetch_body
assert "(!DirtyEvictions() && dirty)) return false;" not in prefetch_body
pred_begin = gc.index("gc_downloads.size() == gc_prefetch_limit")
pred_end = gc.index(") return true;", pred_begin)
predicate = gc[pred_begin:pred_end]
assert "image.unswizzled_size_bytes > 32_MiB - bytes" in predicate
assert "gc_downloads.size() == gc_prefetch_limit" in predicate
assert "runtime.Finish()" in gc and "runtime.FreeDeferredStagingBuffer(map)" in gc
compiler = next((name for name in ("clang++-18", "clang++", "g++")
                 if shutil.which(name)), None)
if not compiler:
    raise SystemExit("No C++20 compiler; Vulkan GC prefetch proof unavailable")

cpp = r"""
#include <boost/container/small_vector.hpp>
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <type_traits>
#include <utility>
#include <vector>
using ImageId = std::size_t;
constexpr std::size_t operator""_MiB(unsigned long long n) {
    return static_cast<std::size_t>(n) * 1024 * 1024;
}
namespace Vulkan {
struct StagingBufferRef {
    std::size_t index{};
    std::span<std::uint8_t> mapped_span{};
};
static_assert(std::is_trivially_copyable_v<StagingBufferRef>);
struct TextureCacheRuntime {
    std::size_t issued{}, completed{}, finishes{}, freed{};
    std::vector<std::unique_ptr<std::uint8_t[]>> backing;
    std::vector<bool> deferred;
    StagingBufferRef DownloadStagingBuffer(std::size_t size, bool deferred_request = false) {
        assert(deferred_request);
        backing.push_back(std::make_unique<std::uint8_t[]>(size));
        deferred.push_back(true);
        ++issued;
        return {issued, {backing.back().get(), size}};
    }
    void Finish() { completed = issued; ++finishes; }
    void FreeDeferredStagingBuffer(StagingBufferRef& map) {
        assert(map.index > 0 && map.index <= completed);
        assert(deferred[map.index - 1]);
        deferred[map.index - 1] = false;
        ++freed;
    }
};
}
struct Image {
    std::size_t unswizzled_size_bytes{};
    void DownloadMemory(Vulkan::StagingBufferRef& map) {
        assert(map.mapped_span.size() == unswizzled_size_bytes);
        if (!map.mapped_span.empty()) {
            map.mapped_span.front() = 19;
            map.mapped_span.back() = 37;
        }
    }
};
std::size_t Test(std::vector<std::size_t> sizes, std::size_t expected) {
    using Runtime = Vulkan::TextureCacheRuntime;
    Runtime runtime;
    std::vector<Image> images;
    for (auto size : sizes) images.push_back({size});
__ACTUAL_DECLARATION__
    std::size_t bytes = 0;
    for (ImageId id = 0; id < images.size(); ++id) {
        auto& image = images[id];
        if (__ACTUAL_PREDICATE__) break;
        auto map = runtime.DownloadStagingBuffer(image.unswizzled_size_bytes, true);
        gc_downloads.emplace_back(id, map);
        image.DownloadMemory(map);
        bytes += image.unswizzled_size_bytes;
        assert(bytes <= 32_MiB);
        assert(gc_downloads.size() <= gc_prefetch_limit);
        assert(runtime.freed == 0);
    }
    assert(gc_downloads.size() == expected);
    if (!gc_downloads.empty()) runtime.Finish();
    for (auto& [id, map] : gc_downloads) {
        assert(id + 1 == map.index);
        assert(runtime.completed == runtime.issued);
        runtime.FreeDeferredStagingBuffer(map);
        assert(map.mapped_span.empty() ||
               (map.mapped_span.front() == 19 && map.mapped_span.back() == 37));
    }
    gc_downloads.clear();
    assert(runtime.freed == expected && runtime.issued == expected);
    assert(runtime.finishes == (expected ? 1u : 0u));
    return runtime.finishes;
}
int main() {
    assert(Test({}, 0) == 0);
    assert(Test(std::vector<std::size_t>(20, 1024), 20) == 1);
    assert(Test(std::vector<std::size_t>(40, 1024), 40) == 1);
    assert(Test(std::vector<std::size_t>(41, 1024), 40) == 1);
    assert(Test(std::vector<std::size_t>(20, 2_MiB), 16) == 1);
    assert(Test(std::vector<std::size_t>(40, 1_MiB), 32) == 1);
    assert(Test(std::vector<std::size_t>(40, 0), 40) == 1);
}
"""
cpp = cpp.replace("__ACTUAL_DECLARATION__", declaration).replace(
    "__ACTUAL_PREDICATE__", predicate)
with tempfile.TemporaryDirectory(prefix="eden-vk-gc-prefetch-") as folder:
    source = Path(folder) / "gc.cpp"
    binary = Path(folder) / "gc"
    source.write_text(cpp, encoding="utf-8")
    subprocess.run([compiler, "-std=c++20", "-O1", "-g",
                    "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", str(source), "-o", str(binary)],
                   check=True, timeout=120)
    subprocess.run([str(binary)], check=True, timeout=180)
print("PASS actual Vulkan GC admission/container: 20/40 staging slots, 32-MiB cap, one Finish, deferred pool release ASan/UBSan")
print("No native PS5 Vulkan driver/firmware execution or measured frame-time improvement")
