#!/usr/bin/env python3
"""Compile the EXACT PS5 Vulkan DownloadMemory readback batch under sanitizers.

Unlike the small_vector-only check, this includes the actual source snippet
from headless/vulkan_download_batch.inc inside a mocked texture cache and
checks GPU Finish ordering, image byte integrity, 16-map/32-MiB batching,
zero-sized images, and oversized standalone transfers. Not a native PS5 run.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
snippet = (root / "headless/vulkan_download_batch.inc").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
assert "boost::container::small_vector<std::pair<ImageId, Map>, 16> pending;" in snippet
assert "runtime.Finish();" in snippet
assert "bytes > batch_limit - batch_bytes" in snippet
assert "pending.size() == 16" in snippet
assert "(port / 'vulkan_download_batch.inc').read_text()" in generator
compiler = next((c for c in ("clang++-18", "clang++", "g++")
                 if shutil.which(c)), None)
if not compiler:
    raise SystemExit("C++20 compiler unavailable; refusing unexecuted Vulkan batch PASS")

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
struct Monitor {
    std::size_t issued{};
    std::size_t completed{};
    std::size_t finishes{};
    std::size_t batch_bytes{};
    std::size_t max_batch_bytes{};
    std::vector<std::size_t> image_tickets;
};
namespace Vulkan {
struct TextureCacheRuntime {
    std::shared_ptr<Monitor> monitor;
    struct Map {
        std::unique_ptr<std::vector<std::uint8_t>> bytes;
        std::span<const std::uint8_t> mapped_span;
        explicit Map(std::size_t n)
            : bytes(std::make_unique<std::vector<std::uint8_t>>(n)),
              mapped_span(*bytes) {}
        Map(Map&&) noexcept = default;
        Map& operator=(Map&&) noexcept = default;
        Map(const Map&) = delete;
        Map& operator=(const Map&) = delete;
    };
    Map DownloadStagingBuffer(std::size_t n) {
        monitor->batch_bytes += n;
        monitor->max_batch_bytes = std::max(monitor->max_batch_bytes,
                                            monitor->batch_bytes);
        return Map{n};
    }
    void Finish() {
        monitor->completed = monitor->issued;
        monitor->batch_bytes = 0;
        ++monitor->finishes;
    }
};
}
struct Info { std::size_t id{}; };
std::vector<std::size_t> FullDownloadCopies(Info info) {
    return {info.id};
}
std::vector<std::size_t> FixSmallVectorADL(std::vector<std::size_t> copies) {
    return copies;
}
struct Image {
    std::shared_ptr<Monitor> monitor;
    Info info{};
    std::size_t gpu_addr{};
    std::size_t unswizzled_size_bytes{};
    void DownloadMemory(Vulkan::TextureCacheRuntime::Map& map,
                        const std::vector<std::size_t>& copies) const {
        assert(copies.size() == 1 && copies[0] == info.id);
        assert(map.bytes->size() == unswizzled_size_bytes);
        auto& bytes = *map.bytes;
        for (std::size_t i = 0; i < bytes.size(); ++i) {
            bytes[i] = static_cast<std::uint8_t>((info.id * 13 + i) % 251);
        }
        monitor->image_tickets[info.id] = ++monitor->issued;
    }
};
struct MockGpuMemory {
    std::shared_ptr<Monitor> monitor;
    std::vector<std::vector<std::uint8_t>> written;
    std::vector<std::size_t> write_order;
};
void SwizzleImage(MockGpuMemory& gpu, std::size_t address, Info info,
                  const std::vector<std::size_t>& copies,
                  std::span<const std::uint8_t> span,
                  std::vector<std::uint8_t>& scratch) {
    assert(copies.size() == 1 && copies[0] == address);
    assert(info.id == address);
    assert(gpu.monitor->image_tickets[info.id] <= gpu.monitor->completed);
    assert(gpu.monitor->finishes > 0);
    assert(gpu.written[address].empty());
    gpu.written[address].assign(span.begin(), span.end());
    gpu.write_order.push_back(address);
    scratch.clear();
}
struct MockCache {
    using Runtime = Vulkan::TextureCacheRuntime;
    Runtime runtime;
    MockGpuMemory gpu;
    MockGpuMemory* gpu_memory;
    std::vector<Image> slot_images;
    std::vector<ImageId> images;
    std::vector<std::uint8_t> swizzle_data_buffer;
    explicit MockCache(std::vector<std::size_t> sizes)
        : runtime{std::make_shared<Monitor>()},
          gpu{runtime.monitor, std::vector<std::vector<std::uint8_t>>(sizes.size()), {}},
          gpu_memory(&gpu) {
        runtime.monitor->image_tickets.resize(sizes.size());
        for (std::size_t i = 0; i < sizes.size(); ++i) {
            slot_images.push_back(Image{runtime.monitor, Info{i}, i, sizes[i]});
            images.push_back(i);
        }
    }
    void Run() {
#include "vulkan_download_batch.inc"
    }
    void Check() const {
        assert(gpu.write_order.size() == images.size());
        for (std::size_t i = 0; i < images.size(); ++i) {
            const auto id = images[i];
            assert(gpu.write_order[i] == id);
            const auto& contents = gpu.written[id];
            const std::size_t bytes = slot_images[id].unswizzled_size_bytes;
            assert(contents.size() == bytes);
            for (std::size_t j = 0; j < contents.size(); ++j)
                assert(contents[j] == static_cast<std::uint8_t>((id * 13 + j) % 251));
        }
        assert(runtime.monitor->completed == runtime.monitor->issued);
    }
};
void Test(std::vector<std::size_t> bytes, std::size_t expected_finishes) {
    MockCache cache(std::move(bytes));
    cache.Run();
    cache.Check();
    assert(cache.runtime.monitor->finishes == expected_finishes);
}
int main() {
    Test({}, 0);
    Test({1, 2, 3}, 1);
    Test(std::vector<std::size_t>(17, 1), 2);
    Test({20_MiB, 14_MiB, 1}, 2); // 32-MiB staging boundary
    Test({33_MiB, 1}, 2); // large texture is standalone
    Test({32_MiB, 1}, 2); // exact cap, then next submission
    Test({0, 0, 0}, 1);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-gpu-readback-batch-") as temp:
    src = Path(temp) / "readback-batch.cpp"
    exe = Path(temp) / "readback-batch"
    src.write_text(cpp, encoding="utf-8")
    subprocess.run([compiler, "-std=c++20", "-O1", "-g",
                    "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    "-I", str(root / "headless"), str(src), "-o", str(exe)],
                   check=True, timeout=120)
    subprocess.run([str(exe)], check=True, timeout=180)
print("PASS actual PS5 Vulkan batch C++: ordering, Finish fences, 16 maps, 32 MiB, oversized textures")
print("The GPU implementation and PS5 firmware transfer paths remain unqualified")
