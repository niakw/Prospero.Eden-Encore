#!/usr/bin/env python3
"""Exercise literal Vulkan dirty-GC scan logic across mixed LRU image states.

Extract the production prefetch skip/capacity/recording sequence into a small
C++20 mock of the pinned Vulkan non-owning StagingBufferRef. Assert that clean,
aliased, scaled and multisample images do not truncate eligible dirty batching.
This does not run the PS5 Vulkan driver or a real image cache.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
gc = (root / "headless/vulkan_gc_downloads.inc").read_text(encoding="utf-8")
generator = (root / "tools/prepare-vulkan-port.py").read_text(encoding="utf-8")
assert "(port / 'vulkan_gc_downloads.inc').read_text()" in generator
begin = gc.index("    using DownloadMap = decltype(runtime.DownloadStagingBuffer(size_t{}));")
end = gc.index(" gc_downloads;", begin) + len(" gc_downloads;")
declaration = gc[begin:end]
assert "constexpr size_t gc_prefetch_limit = 40;" in declaration
start = gc.index("                if (!dirty || !image.aliased_images.empty()")
stop = gc.index("                bytes += image.unswizzled_size_bytes;", start)
record = gc[start:stop + len("                bytes += image.unswizzled_size_bytes;")]
assert record.count("return false;") == 1
assert record.count("return true;") == 1
assert record.index("return false;") < record.index("return true;")
assert "gc_downloads.size() == gc_prefetch_limit" in record
assert "image.unswizzled_size_bytes > 32_MiB - bytes" in record
assert "gc_downloads.emplace_back(id, map);" in record
assert record.index("gc_downloads.emplace_back") < record.index("image.DownloadMemory")
assert "if (remaining == 0) return true;" in gc
assert "--remaining;" in gc
assert "if (frame_tick < ticks_to_destroy) return;" in gc
assert "if (!DirtyEvictions() && dirty)" in gc
assert "if (!dirty || !image.aliased_images.empty()" in gc

compiler = next((name for name in ("clang++-18", "clang++", "g++")
                 if shutil.which(name)), None)
if not compiler:
    raise SystemExit("Missing C++20 compiler for Vulkan mixed-GC test")

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
constexpr std::size_t operator""_MiB(unsigned long long size) {
    return static_cast<std::size_t>(size) * 1024 * 1024;
}
namespace Vulkan {
struct StagingBufferRef {
    std::size_t index{};
    std::span<std::uint8_t> mapped_span;
};
static_assert(std::is_trivially_copyable_v<StagingBufferRef>);
struct TextureCacheRuntime {
    std::size_t issued{}, completed{}, finishes{}, freed{};
    std::vector<std::unique_ptr<std::uint8_t[]>> storage;
    std::vector<bool> deferred;
    StagingBufferRef DownloadStagingBuffer(std::size_t size, bool is_deferred) {
        assert(is_deferred);
        storage.push_back(std::make_unique<std::uint8_t[]>(size));
        deferred.push_back(true);
        ++issued;
        return {issued, {storage.back().get(), size}};
    }
    void Finish() { completed = issued; ++finishes; }
    void FreeDeferredStagingBuffer(StagingBufferRef& ref) {
        assert(ref.index > 0 && ref.index <= completed);
        assert(deferred[ref.index - 1]);
        deferred[ref.index - 1] = false;
        ++freed;
    }
};
}
struct Info {
    ImageId id{};
    unsigned num_samples{1};
};
std::vector<ImageId> FullDownloadCopies(Info info) { return {info.id}; }
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
    bool HasScaled() const { return scaled; }
    void DownloadMemory(Vulkan::StagingBufferRef& map,
                        const std::vector<ImageId>& copies) {
        assert(copies.size() == 1 && copies[0] == info.id);
        assert(map.mapped_span.size() == unswizzled_size_bytes);
        if (!map.mapped_span.empty()) {
            map.mapped_span.front() = 0x19;
            map.mapped_span.back() = 0x37;
        }
    }
};
struct Scenario {
    std::vector<Image> images;
    explicit Scenario(std::vector<Image> values) : images(std::move(values)) {}
    void Test(std::size_t expected, std::vector<ImageId> ids,
              std::size_t max_scanned = 40) {
        Vulkan::TextureCacheRuntime runtime;
__PRODUCTION_DECLARATION__
        std::size_t bytes = 0;
        std::size_t scanned = 0;
        std::size_t remaining = max_scanned;
        for (ImageId id = 0; id < images.size(); ++id) {
            if (remaining == 0) break;
            --remaining;
            ++scanned;
            auto& image = images[id];
            const bool dirty = image.dirty;
            const auto scan_one = [&]() -> bool {
__PRODUCTION_RECORD__
                return false;
            };
            if (scan_one()) break;
            assert(bytes <= 32_MiB);
            assert(gc_downloads.size() <= gc_prefetch_limit);
            assert(runtime.freed == 0);
        }
        assert(scanned <= max_scanned);
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
        assert(runtime.freed == expected && runtime.issued == expected);
        assert(runtime.finishes == (expected ? 1u : 0u));
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
        Scenario(std::move(images)).Test(1, {4});
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
with tempfile.TemporaryDirectory(prefix="eden-vulkan-mixed-gc-") as temp:
    path = Path(temp) / "gc.cpp"
    executable = Path(temp) / "gc"
    path.write_text(cpp, encoding="utf-8")
    subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
                    "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", str(path), "-o", str(executable)],
                   check=True, timeout=120)
    subprocess.run([str(executable)], check=True, timeout=180)
print("PASS literal Vulkan mixed-GC scan: clean/alias/scaled/multisample skip, 20/40 batch, 32MiB, fenced release ASan/UBSan")
print("No Sony PS5 SDK, driver or frame-time measurements")
