#!/usr/bin/env python3
"""Source-extracted host check for PS5 nonblocking Vulkan GPU timestamp batches."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
marker = 'void GpuTimeCollect(const Device& device) {'
assert source.count(marker) == 1
body = source.split(marker, 1)[1].split("// VkQueryPool is a device child.", 1)[0]
method = marker + body
assert "constexpr u32 kQueryBatch = 32;" in method
assert "VK_QUERY_RESULT_WITH_AVAILABILITY_BIT" in method
assert "samples.fill(0);" in method
assert "if (completed != count) break;" in method
assert "F07 batch native GPU timestamp queries" in generator
assert "VK_QUERY_RESULT_WITH_AVAILABILITY_BIT" in generator
assert method.count("#ifdef PS5_NATIVE") == 1 and method.count("#else") == 1
assert method.count("#endif") == 1

prefix = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using VkResult = int;
constexpr VkResult VK_SUCCESS = 0, VK_NOT_READY = 1;
constexpr u32 VK_QUERY_RESULT_64_BIT = 1, VK_QUERY_RESULT_WITH_AVAILABILITY_BIT = 2;
namespace Eden::DevVulkan { inline bool gpu_time = true; }
struct Pool { int operator*() const { return 1; } };
struct GpuTimeProbe {
    static constexpr u32 SLOTS = 512;
    Pool pool{};
    bool write{true}, failed{};
    double period_ns{1.0};
    u64 next{}, first_pending{}, busy_ns{}, max_ns{}, submissions{};
    std::chrono::steady_clock::time_point report{std::chrono::steady_clock::now()};
} gpu_time;
struct FakeLogical {
    mutable int calls{};
    bool fail{};
    std::array<bool, 512> ready{};
    VkResult GetQueryResults(int, u32 first, u32 count, std::size_t size,
                             void* data, std::size_t stride, u32 flags) const {
        ++calls;
        if (fail) return -4;
        assert(count % 2 == 0 && size >= count * stride);
        bool all = true;
        for (u32 i = 0; i < count; ++i) {
            const bool available = ready[((first + i) / 2) % 512];
            all &= available;
            auto* out = reinterpret_cast<u64*>(static_cast<char*>(data) + i * stride);
            if (flags & VK_QUERY_RESULT_WITH_AVAILABILITY_BIT) {
                out[0] = available ? (i % 2 ? 15 : 10) : 0;
                out[1] = available ? 1 : 0;
            } else if (available) {
                out[0] = i % 2 ? 15 : 10;
            }
        }
        return all ? VK_SUCCESS : VK_NOT_READY;
    }
};
struct Device {
    mutable FakeLogical logical{};
    FakeLogical& GetLogical() const { return logical; }
};
"""
suffix = r"""
void Reset(u64 first, u64 next) {
    gpu_time = GpuTimeProbe{};
    gpu_time.first_pending = first;
    gpu_time.next = next;
}
int main() {
    Device d{};
    Reset(0, 34);
    for (u32 i = 0; i < 33; ++i) d.logical.ready[i] = true;
    GpuTimeCollect(d);
    assert(gpu_time.first_pending == 33 && gpu_time.submissions == 33);
    assert(gpu_time.busy_ns == 165 && gpu_time.max_ns == 5);
#ifdef PS5_NATIVE
    assert(d.logical.calls == 2);
#else
    assert(d.logical.calls == 33);
#endif
    d.logical = FakeLogical{};
    Reset(0, 6);
    d.logical.ready[0] = d.logical.ready[1] = true;
    d.logical.ready[3] = d.logical.ready[4] = true;
    GpuTimeCollect(d);
    assert(gpu_time.first_pending == 2 && gpu_time.submissions == 2);
    d.logical.ready[2] = true;
    GpuTimeCollect(d);
    assert(gpu_time.first_pending == 5 && gpu_time.submissions == 5);
    d.logical = FakeLogical{};
    Reset(510, 515);
    for (u32 i : {510u, 511u, 0u, 1u}) d.logical.ready[i] = true;
    GpuTimeCollect(d);
    assert(gpu_time.first_pending == 514 && gpu_time.submissions == 4);
#ifdef PS5_NATIVE
    assert(d.logical.calls == 2);
#else
    assert(d.logical.calls == 4);
#endif
    d.logical = FakeLogical{};
    d.logical.fail = true;
    Reset(0, 3);
    GpuTimeCollect(d);
    assert(gpu_time.first_pending == 0 && gpu_time.submissions == 0);
}
"""
compiler = shutil.which("clang++") or shutil.which("g++")
assert compiler, "A C++20 compiler is required"
with tempfile.TemporaryDirectory(prefix="f07-gpu-time-") as folder:
    cpp = Path(folder) / "probe.cpp"
    cpp.write_text(prefix + method + suffix)
    for mode in ("-O0", "-O2"):
        for native in (False, True):
            binary = Path(folder) / ("probe-" + mode[2:] + ("-ps5" if native else "-desktop"))
            cmd = [compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror", mode,
                   "-fsanitize=undefined", "-fno-sanitize-recover=all"]
            if native:
                cmd.append("-DPS5_NATIVE")
            subprocess.run([*cmd, str(cpp), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
print("F07 GPU timestamp batch: source-extracted desktop/native O0/O2 UBSan OK")
