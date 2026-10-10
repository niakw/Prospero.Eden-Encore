#!/usr/bin/env python3
"""Compile the literal Vulkan GC staging transfer with move-only ownership.

The exact staging/download/enqueue statements are extracted from the
production GC snippet. This catches accidental copies of RAII buffer maps,
publication before GPU recording and premature destruction without PS5 SDK.
This is NOT a Vulkan driver/PS5 GPU execution test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
gc = (root / "headless/vulkan_gc_downloads.inc").read_text(encoding="utf-8")
generator = (root / "tools/prepare-vulkan-port.py").read_text(encoding="utf-8")
assert "(port / 'vulkan_gc_downloads.inc').read_text()" in generator
begin = gc.index("                auto map = runtime.DownloadStagingBuffer(")
end = gc.index("                bytes += image.unswizzled_size_bytes;", begin)
source = gc[begin:end]
assert gc.count("gc_downloads.emplace_back(id,") == 1
record = source.index("image.DownloadMemory(map, copies);")
enqueue = source.index("gc_downloads.emplace_back(id, std::move(map));")
assert record < enqueue, "staging map must not be moved before GPU recording"
assert "gc_downloads.emplace_back(id, map);" not in gc
assert source.count("DownloadStagingBuffer(") == 1
assert "runtime.Finish()" in gc
assert "runtime.FreeDeferredStagingBuffer(map)" in gc

compiler = next((name for name in ("clang++-18", "clang++", "g++")
                 if shutil.which(name)), None)
if not compiler:
    raise SystemExit("C++20 compiler unavailable; GC staging proof not executed")

cpp = r"""
#include <boost/container/small_vector.hpp>
#include <cassert>
#include <cstddef>
#include <memory>
#include <type_traits>
#include <utility>
#include <vector>
using ImageId = std::size_t;
struct Monitor {
    std::size_t live{}, issued{}, completed{}, finishes{}, freed{};
};
namespace Vulkan {
struct TextureCacheRuntime {
    std::shared_ptr<Monitor> monitor;
    struct Map {
        std::shared_ptr<Monitor> monitor;
        std::unique_ptr<std::size_t> ticket;
        explicit Map(std::shared_ptr<Monitor> m)
            : monitor(std::move(m)), ticket(std::make_unique<std::size_t>()) {
            ++monitor->live;
        }
        Map(Map&&) noexcept = default;
        Map& operator=(Map&&) noexcept = default;
        Map(const Map&) = delete;
        Map& operator=(const Map&) = delete;
        ~Map() {
            if (ticket) {
                // Real deferred buffer release must happen after GPU Finish.
                assert(monitor && *ticket != 0 && *ticket <= monitor->completed);
                ++monitor->freed;
                --monitor->live;
            }
        }
    };
    Map DownloadStagingBuffer(std::size_t, bool = false) {
        return Map(monitor);
    }
    void Finish() {
        monitor->completed = monitor->issued;
        ++monitor->finishes;
    }
};
}
static_assert(!std::is_copy_constructible_v<Vulkan::TextureCacheRuntime::Map>);
struct Info { std::size_t id; };
std::vector<ImageId> FullDownloadCopies(Info info) { return {info.id}; }
std::vector<ImageId> FixSmallVectorADL(std::vector<ImageId> copy) {
    return copy;
}
struct Image {
    std::shared_ptr<Monitor> monitor;
    Info info;
    std::size_t unswizzled_size_bytes;
    void DownloadMemory(Vulkan::TextureCacheRuntime::Map& map,
                        const std::vector<ImageId>& copies) {
        assert(map.ticket && map.monitor == monitor);
        assert(copies.size() == 1 && copies.front() == info.id);
        *map.ticket = ++monitor->issued;
    }
};
struct MockCache {
    Vulkan::TextureCacheRuntime runtime;
    std::vector<Image> images;
    explicit MockCache(std::size_t count)
        : runtime{std::make_shared<Monitor>()} {
        for (std::size_t id = 0; id < count; ++id)
            images.push_back({runtime.monitor, Info{id}, 1024 + id});
    }
    void Run() {
        using DownloadMap = decltype(runtime.DownloadStagingBuffer(std::size_t{}));
        boost::container::small_vector<std::pair<ImageId, DownloadMap>, 16> gc_downloads;
        std::size_t bytes = 0;
        for (ImageId id = 0; id < images.size(); ++id) {
            auto& image = images[id];
__PRODUCTION_GC_RECORD_AND_MOVE__
            bytes += image.unswizzled_size_bytes;
            assert(runtime.monitor->live == gc_downloads.size());
            assert(runtime.monitor->freed == 0);
        }
        assert(bytes >= images.size() * 1024);
        assert(runtime.monitor->issued == images.size());
        assert(gc_downloads.size() == images.size());
        // No ownership is destroyed before GPU submission completes.
        runtime.Finish();
        for (auto& [id, map] : gc_downloads) {
            assert(map.ticket);
            assert(id == *map.ticket - 1);
        }
        gc_downloads.clear();
        assert(runtime.monitor->live == 0);
        assert(runtime.monitor->freed == images.size());
        assert(runtime.monitor->completed == images.size());
        assert(runtime.monitor->finishes == 1);
    }
};
int main() {
    MockCache(1).Run();
    MockCache(16).Run();
}
"""
cpp = cpp.replace("__PRODUCTION_GC_RECORD_AND_MOVE__", source)
with tempfile.TemporaryDirectory(prefix="eden-vulkan-gc-staging-") as folder:
    source_file = Path(folder) / "gc.cpp"
    binary = Path(folder) / "gc"
    source_file.write_text(cpp, encoding="utf-8")
    subprocess.run([compiler, "-std=c++20", "-O1", "-g",
                    "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    str(source_file), "-o", str(binary)], check=True, timeout=120)
    subprocess.run([str(binary)], check=True, timeout=180)
print("PASS literal Vulkan GC staging C++: move-only maps, 1/16 images, Finish-before-release ASan/UBSan")
print("Not a PS5 SDK build or live GPU memory safety qualification")
