#!/usr/bin/env python3
"""Exercise literal Vulkan dirty-GC scan logic across mixed LRU image states.

Extract the production prefetch skip/capacity/recording sequence into a small
C++20 mock of the pinned Vulkan non-owning StagingBufferRef. Assert that clean,
aliased and multisample images do not truncate eligible dirty batching while
scaled images DO batch behind one GPU completion barrier.
This does not run the PS5 Vulkan driver or a real image cache.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
maintained = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text(encoding="utf-8")
begin = maintained.index("void TextureCache<P>::RunGarbageCollector() {")
end = maintained.index("\ntemplate <class P>", begin)
gc = maintained[begin:end]
oracle = (root / "vendor/encore-active/eden-vulkan-oracles/vulkan_gc_downloads.inc").read_text(encoding="utf-8")
assert "const bool prefetch_dirty = DirtyEvictions();" in oracle and "const bool prefetch_dirty = DirtyEvictions();" in gc
generator = (root / "tools/prepare-vulkan-port.py").read_text(encoding="utf-8")
assert "(vulkan_oracle / 'vulkan_gc_downloads.inc').read_text()" in generator
begin = gc.index("    using DownloadMap = decltype(runtime.DownloadStagingBuffer(size_t{}));")
end = gc.index(" gc_downloads;", begin) + len(" gc_downloads;")
declaration = gc[begin:end]
assert "constexpr size_t gc_prefetch_limit = 40;" in declaration
start = gc.index("                if (!dirty || !image.aliased_images.empty()")
stop = gc.index("                bytes += image.unswizzled_size_bytes;", start)
record = gc[start:stop + len("                bytes += image.unswizzled_size_bytes;")]
project_begin = gc.index("            const u64 projected_stop = (aggressive_mode ||")
project_end = gc.index("\n            };", project_begin) + len("\n            };")
projected = gc[project_begin:project_end]
assert "usage, ReclaimedBytes(image)" in projected
assert "critical_memory : expected_memory" in projected
assert "return usage < projected_stop;" in projected
assert projected.count("::Eden::Performance::KeepDirtyTextures()") == 1
assert "return NoteProjectedEviction(image);" in record
# The two ordinary capacity/invalid-stage exits plus both native recoverable
# exception exits stop the prefetch pass, never marking dirty bytes evicted.
assert record.count("return true;") == 4
assert "RetireFailedBatch();" in record
assert "if (!gc_downloads.empty()) runtime.Finish();" in record
assert "ReleaseDownloads();" in record
assert "catch (const std::bad_alloc&)" in record
assert "catch (const std::invalid_argument&)" in record
assert "F07 rollback partial Vulkan dirty GC prefetch before staging release" in generator
# Enforce byte-for-byte replay of the actual guarded native record body:
# a generator update cannot silently omit the drain or invert ownership.
rollback_from = record.index("                // The pinned StagingBufferRef is a POD handle")
rollback_to = record.index("                bytes += image.unswizzled_size_bytes;", rollback_from)
assert record[rollback_from:rollback_to] in generator
assert record.index("if (!gc_downloads.empty()) runtime.Finish();") < record.index("ReleaseDownloads();")
assert record.index("gc_downloads.emplace_back(id, map);") < record.index("map_owned_by_batch = true;")
assert record.index("map_owned_by_batch = true;") < record.index("image.DownloadMemory(map, copies);")
assert record.index("return NoteProjectedEviction(image);") < record.index("return true;")
assert record.index("if (!map.buffer || map.mapped_span.size_bytes() < image.unswizzled_size_bytes)") < record.rindex("return true;")
assert gc.count("return NoteProjectedEviction(image);") == 2
assert "gc_downloads.size() == gc_prefetch_limit" in record
assert "image.unswizzled_size_bytes > 32_MiB - bytes" in record
assert "image.unswizzled_size_bytes > 32_MiB)" in record
assert "return NoteProjectedEviction(image);" in record
assert "gc_downloads.emplace_back(id, map);" in record
assert record.index("gc_downloads.emplace_back") < record.index("image.DownloadMemory")
assert "F07 reject failed or undersized dirty GC prefetch staging" in generator
assert "if (!map.buffer || map.mapped_span.size_bytes() < image.unswizzled_size_bytes)" in record
assert record.index("if (!map.buffer || map.mapped_span.size_bytes() < image.unswizzled_size_bytes)") < record.index("gc_downloads.emplace_back")
assert "if (map.buffer) runtime.FreeDeferredStagingBuffer(map);" in record
assert "if (remaining == 0 || scanned >= max_scanned) return true;" in gc
assert "if (count_visits) --remaining;" in gc
assert "if (!count_visits) --remaining;" in gc
assert "if (frame_tick < ticks_to_destroy) return;" in gc
assert "const bool prefetch_dirty = DirtyEvictions();" in gc
assert "if (!prefetch_dirty) return;" in gc
assert gc.index("if (frame_tick < ticks_to_destroy) return;") < gc.index("const bool prefetch_dirty = DirtyEvictions();")
assert gc.index("if (!prefetch_dirty) return;") < gc.index("lru_cache.ForEachItemBelow(")
assert "(!DirtyEvictions() && dirty)) return false;" not in gc
assert "if (!aggressive_mode && True(image.flags & ImageFlagBits::CostlyLoad))" in gc
# Prefetch snapshots its own pressure forecast; native Cleanup refreshes the
# kernel-backed dirty-pressure decision at most eight LRU visits later and
# immediately after an eviction. Desktop retains its original live probe.
assert "if (!dirty || !image.aliased_images.empty()" in gc
assert "image.HasScaled() || image.info.num_samples != 1" not in gc
assert "Scaled textures use the SAME Image::DownloadMemory path" in gc
assert "image.HasScaled() || image.info.num_samples != 1" not in (
    root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h"
).read_text()


compiler = next((name for name in ("clang++-18", "clang++", "g++")
                 if shutil.which(name)), None)
if not compiler:
    raise SystemExit("Missing C++20 compiler for Vulkan mixed-GC test")
# The PS5 build uses pinned Boost 1.90. The host must compile against
# the SAME vendored source, not assume a separately installed Homebrew Boost.
boost_root = root / "vendor/sources/eden-cpm/boost/boost-1.90.0"
boost_includes = [str(p) for p in boost_root.glob("libs/*/include") if p.is_dir()]
if not boost_includes:
    raise SystemExit(f"Vendored Boost headers missing: {boost_root}")
boost_flags = [flag for inc in boost_includes for flag in ("-I", inc)]

cpp = r"""
#include <boost/container/small_vector.hpp>
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <new>
#include <span>
#include <stdexcept>
#include <type_traits>
#include <utility>
#include <vector>
struct ScopeExitMaker {};
template<class F> struct ScopeExit {
    F callback;
    ~ScopeExit() { callback(); }
};
template<class F> ScopeExit<std::decay_t<F>> operator+(ScopeExitMaker, F&& callback) {
    return {std::forward<F>(callback)};
}
#define SCOPE_EXIT auto scope_guard = ScopeExitMaker{} + [&]
#include "vulkan_gc_budget.h"

using ImageId = std::size_t;
using u64 = std::uint64_t;
namespace Eden::Performance {
bool KeepDirtyTextures() { return true; }
}
constexpr std::size_t operator""_MiB(unsigned long long size) {
    return static_cast<std::size_t>(size) * 1024 * 1024;
}
namespace Vulkan {
struct StagingBufferRef {
    std::size_t index{};
    std::size_t buffer{};
    std::span<std::uint8_t> mapped_span;
};
static_assert(std::is_trivially_copyable_v<StagingBufferRef>);
struct TextureCacheRuntime {
    std::size_t issued{}, completed{}, finishes{}, freed{}, queued_max{};
    std::vector<std::unique_ptr<std::uint8_t[]>> storage;
    std::vector<bool> deferred;
    bool short_first{}, throw_first{}, null_first{};
    StagingBufferRef DownloadStagingBuffer(std::size_t size, bool is_deferred = false) {
        assert(is_deferred);
        if (throw_first) {throw_first=false;throw std::bad_alloc{};}
        if (null_first) {
            null_first=false;
            // A null Vulkan buffer can still report a full CPU mapping.
            storage.push_back(std::make_unique<std::uint8_t[]>(size));
            return {0,0,{storage.back().get(),size}};
        }
        storage.push_back(std::make_unique<std::uint8_t[]>(size));
        deferred.push_back(true);
        ++issued;
        if(short_first) {short_first=false;return {issued,issued,{storage.back().get(),size-1}};}
        return {issued,issued,{storage.back().get(),size}};
    }
    void Finish() { completed = issued; ++finishes; }
    void FreeDeferredStagingBuffer(StagingBufferRef& ref) {
        assert(completed >= queued_max); // cannot release in-flight GPU readers
        assert(ref.index > 0 && ref.index <= issued);
        assert(deferred[ref.index - 1]);
        deferred[ref.index - 1] = false;
        ++freed;
    }
};
}
struct Info {
    ImageId id{};
    unsigned num_samples{1};
    bool no_regions{};
};
std::vector<ImageId> FullDownloadCopies(Info info) {
    if (info.no_regions) return {};
    return {info.id};
}
std::vector<ImageId> FixSmallVectorADL(std::vector<ImageId> copies) {
    return copies;
}
struct Image {
    Info info;
    std::size_t unswizzled_size_bytes;
    bool dirty;
    bool scaled = false;
    std::vector<ImageId> aliased_images;
    std::vector<ImageId> overlapping_images;
    u64 reclaimed_bytes{};
    bool decoding{false}, costly{false};
    unsigned fail_mode{}; // 1: bad_alloc, 2: invalid_argument, 3: unexpected runtime failure
    Vulkan::TextureCacheRuntime* recording_runtime{};
    bool HasScaled() const { return scaled; }
    void DownloadMemory(Vulkan::StagingBufferRef& map,
                        const std::vector<ImageId>& copies) {
        assert(copies.size() == 1 && copies[0] == info.id);
        assert(map.mapped_span.size() == unswizzled_size_bytes);
        if (recording_runtime) recording_runtime->queued_max = map.index;
        if (fail_mode == 1) throw std::bad_alloc{};
        if (fail_mode == 2) throw std::invalid_argument("mock invalid copy");
        if (fail_mode == 3) throw std::runtime_error("mock unexpected driver failure");
        if (!map.mapped_span.empty()) {
            map.mapped_span.front() = 0x19;
            map.mapped_span.back() = 0x37;
        }
    }
};
using ImageBase = Image;
struct Scenario {
    std::vector<Image> images;
    explicit Scenario(std::vector<Image> values) : images(std::move(values)) {}
    void Test(std::size_t expected, std::vector<ImageId> ids,
              std::size_t eviction_budget = 40,
              u64 initial_usage = 1000_MiB,
              std::size_t expected_scanned = 0,
              bool short_first=false, bool throw_first=false, bool null_first=false,
              unsigned fail_second=0) {
        Vulkan::TextureCacheRuntime runtime;
        runtime.short_first=short_first;
        runtime.throw_first=throw_first;
        runtime.null_first=null_first;
        if (fail_second) {
            assert(images.size() >= 2);
            images[1].fail_mode = fail_second;
        }
__PRODUCTION_DECLARATION__
        const auto ReleaseDownloads = [&] {
            for (auto& [id, map] : gc_downloads) {
                (void)id;
                runtime.FreeDeferredStagingBuffer(map);
            }
            gc_downloads.clear();
        };
        std::size_t bytes = 0;
        u64 usage = initial_usage;
        constexpr u64 critical_memory = 100_MiB;
        constexpr u64 expected_memory = 80_MiB;
        const bool aggressive_mode = true;
        const auto ReclaimedBytes = [](const ImageBase& image) -> u64 {
            return image.reclaimed_bytes;
        };
__PRODUCTION_PROJECTION__
        std::size_t scanned = 0;
        std::size_t remaining = eviction_budget;
        bool rethrew_unexpected = false;
        for (ImageId id = 0; id < images.size(); ++id) {
            if (remaining == 0 || scanned >= 8192) break;
            ++scanned;
            auto& image = images[id];
            image.recording_runtime = &runtime;
            // R442: decoding and costly-load images are visited but are not
            // eviction candidates; their presence cannot exhaust the budget.
            if (image.decoding || image.costly) continue;
            --remaining;
            const bool dirty = image.dirty;
            const auto scan_one = [&]() -> bool {
__PRODUCTION_RECORD__
                return NoteProjectedEviction(image);
            };
            try {
                if (scan_one()) break;
            } catch (const std::runtime_error&) {
                // Non-recoverable errors must still drain and retire EVERY
                // previously accepted map, then propagate to the caller.
                if (fail_second != 3) throw;
                rethrew_unexpected = true;
                break;
            }
            assert(bytes <= 32_MiB);
            assert(gc_downloads.size() <= gc_prefetch_limit);
            if (!fail_second)
                assert(runtime.freed == (short_first ? 1u : 0u));
        }
        assert(scanned <= 8192);
        assert(rethrew_unexpected == (fail_second == 3));
        if (expected_scanned != 0) assert(scanned == expected_scanned);
        assert(gc_downloads.size() == expected);
        std::vector<ImageId> actual;
        for (auto& entry : gc_downloads) actual.push_back(entry.first);
        assert(actual == ids);
        if (!gc_downloads.empty()) runtime.Finish();
        for (auto& [id, ref] : gc_downloads) {
            assert(id == images[id].info.id);
            assert(ref.mapped_span.empty() ||
                   (ref.mapped_span.front() == 0x19 &&
                    ref.mapped_span.back() == 0x37));
            runtime.FreeDeferredStagingBuffer(ref);
        }
        gc_downloads.clear();
        const auto rejected=short_first ? 1u : 0u;
        const auto rolled_back=fail_second ? 2u : 0u;
        assert(runtime.freed == expected + rejected + rolled_back);
        assert(runtime.issued == expected + rejected + rolled_back);
        assert(runtime.finishes == (expected ? 1u : 0u) + (fail_second ? 1u : 0u));
        if (fail_second)
            assert(runtime.completed == 2 && runtime.queued_max == 2);
    }
};
Image ImageFor(ImageId id, bool dirty, std::size_t size = 1024) {
    return {Info{id, 1}, size, dirty, false, {}, {}};
}
int main() {
    {
        auto clean = ImageFor(0, false);
        auto dirty = ImageFor(1, true);
        Scenario({clean, dirty}).Test(1, {1});
    }
    {
        std::vector<Image> images;
        std::vector<ImageId> ids;
        for (ImageId i = 0; i < 40; ++i) {
            images.push_back(ImageFor(i, i % 2 == 1));
            if (i % 2) ids.push_back(i);
        }
        Scenario(std::move(images)).Test(20, std::move(ids));
    }
    {
        std::vector<Image> images;
        std::vector<ImageId> ids;
        for (ImageId i = 0; i < 50; ++i) {
            images.push_back(ImageFor(i, i >= 16));
            if (i >= 16 && i < 40) ids.push_back(i);
        }
        Scenario(std::move(images)).Test(24, std::move(ids));
    }
    {
        std::vector<Image> images;
        for (ImageId i = 0; i < 20; ++i) {
            auto item = ImageFor(i, false);
            images.push_back(std::move(item));
        }
        Scenario(std::move(images)).Test(0, {});
    }
    {
        std::vector<Image> images;
        for (ImageId i = 0; i < 5; ++i) images.push_back(ImageFor(i, true));
        images[0].aliased_images.push_back(3);
        images[1].overlapping_images.push_back(4);
        images[2].scaled = true;
        images[3].info.num_samples = 4;
        // Scaled download is eligible; aliases/overlaps/MSAA are not.
        Scenario(std::move(images)).Test(2, {2, 4});
    }
    {
        // 40 scaled textures of 1MiB remain in one bounded prefetch pass.
        // The 32-MiB staging budget is not enlarged to upstream's 64-MiB.
        std::vector<Image> images;
        std::vector<ImageId> ids;
        for (ImageId i = 0; i < 40; ++i) {
            auto scaled = ImageFor(i, true, 1_MiB);
            scaled.scaled = true;
            images.push_back(std::move(scaled));
            if (i < 32) ids.push_back(i);
        }
        Scenario(std::move(images)).Test(32, std::move(ids), 40, 1000_MiB, 33);
    }
    {
        // An oversized dirty image must use Cleanup's individual download.
        // It must not prevent the next independent small images from sharing
        // one Finish. The first huge image still consumes one scanned slot.
        std::vector<Image> images;
        std::vector<ImageId> ids;
        images.push_back(ImageFor(0, true, 33_MiB));
        for (ImageId i = 1; i <= 40; ++i) {
            images.push_back(ImageFor(i, true));
            if (i < 40) ids.push_back(i);
        }
        Scenario(std::move(images)).Test(39, std::move(ids));
    }
    {
        // The clean LRU image is deleted by Cleanup, reclaiming enough
        // projected memory to remove pressure. No later dirty readback
        // should be submitted speculatively.
        std::vector<Image> images;
        images.push_back(ImageFor(0, false));
        images[0].reclaimed_bytes = 31_MiB;
        for (ImageId i = 1; i < 10; ++i)
            images.push_back(ImageFor(i, true));
        Scenario(std::move(images)).Test(0, {}, 40, 130_MiB, 1);
    }
    {
        // Two stages of pressure reduction: a clean eviction, then three
        // eligible dirty readbacks. Stop at the third, before queuing a
        // fourth readback that Cleanup need not execute.
        std::vector<Image> images;
        images.push_back(ImageFor(0, false));
        images[0].reclaimed_bytes = 20_MiB;
        for (ImageId i = 1; i <= 10; ++i) {
            images.push_back(ImageFor(i, true));
            images.back().reclaimed_bytes = 5_MiB;
        }
        Scenario(std::move(images)).Test(3, {1, 2, 3}, 40, 130_MiB, 4);
    }
    {
        // R442: more than 40 decoding/costly LRU entries preceding dirty
        // candidates no longer prevent their shared GPU Finish().
        std::vector<Image> images;
        for (ImageId i = 0; i < 185; ++i) {
            auto image = ImageFor(i, i >= 180);
            if (i < 120) image.decoding = true;
            else if (i < 180) image.costly = true;
            images.push_back(std::move(image));
        }
        Scenario(std::move(images)).Test(5, {180, 181, 182, 183, 184}, 10,
                                          1000_MiB, 185);
    }
    {
        std::vector<Image> images;
        std::vector<ImageId> ids;
        for (ImageId i = 0; i < 41; ++i) {
            images.push_back(ImageFor(i, true));
            if (i < 40) ids.push_back(i);
        }
        Scenario(std::move(images)).Test(40, std::move(ids));
    }
#ifdef PS5_NATIVE
    // A dirty image without any GPU download regions cannot be staged or
    // projected as evicted. Continue to the NEXT valid dirty LRU image.
    {
        auto unsupported = ImageFor(0, true);
        unsupported.info.no_regions = true;
        Scenario({unsupported, ImageFor(1, true)}).Test(1, {1}, 40, 1000_MiB, 2);
    }
    // Short mappings and thrown staging requests must stop speculative
    // downloads before recording GPU copies; real Cleanup can retry.
    Scenario({ImageFor(0,true),ImageFor(1,true)}).Test(
        0,{},40,1000_MiB,1,true,false);
    Scenario({ImageFor(0,true),ImageFor(1,true)}).Test(
        0,{},40,1000_MiB,1,false,true);
    // Null VkBuffer + full mapped bytes must never schedule a GPU transfer.
    Scenario({ImageFor(0,true),ImageFor(1,true)}).Test(
        0,{},40,1000_MiB,1,false,false,true);
    // One accepted GPU readback followed by a bad_alloc/invalid copy:
    // both deferred maps MUST be fenced and freed, and no dirty image may
    // be advertised to Cleanup as prefetched.
    Scenario({ImageFor(0,true),ImageFor(1,true)}).Test(
        0,{},40,1000_MiB,2,false,false,false,1);
    Scenario({ImageFor(0,true),ImageFor(1,true)}).Test(
        0,{},40,1000_MiB,2,false,false,false,2);
    // Unclassified failure after a GPU record is never swallowed.
    // The same pending map retirement happens BEFORE the rethrow.
    Scenario({ImageFor(0,true),ImageFor(1,true)}).Test(
        0,{},40,1000_MiB,2,false,false,false,3);
#endif
    {
        std::vector<Image> images;
        std::vector<ImageId> ids;
        for (ImageId i = 0; i < 40; ++i) {
            images.push_back(ImageFor(i, true, 2_MiB));
            if (i < 16) ids.push_back(i);
        }
        Scenario(std::move(images)).Test(16, std::move(ids));
    }
}
"""
cpp = cpp.replace("__PRODUCTION_DECLARATION__", declaration)
cpp = cpp.replace("__PRODUCTION_RECORD__", record)
cpp = cpp.replace("__PRODUCTION_PROJECTION__", projected)
with tempfile.TemporaryDirectory(prefix="eden-vulkan-mixed-gc-") as temp:
    path = Path(temp) / "gc.cpp"
    executable = Path(temp) / "gc"
    path.write_text(cpp, encoding="utf-8")
    for native in (False,True):
        binary=Path(temp)/("gc-ps5" if native else "gc-desktop")
        subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=address,undefined",
                        "-fno-sanitize-recover=all",
                        *(['-DPS5_NATIVE=1'] if native else []),
                        "-I", str(root / "headless"),
                        *boost_flags, str(path), "-o", str(binary)],
                       check=True, timeout=120)
        subprocess.run([str(binary)], check=True, timeout=180)
print("PASS literal Vulkan mixed-GC scan: clean pressure projection, skips, 20/40 batch, 32MiB, fenced release ASan/UBSan")
print("No Sony PS5 SDK, driver or frame-time measurements")
