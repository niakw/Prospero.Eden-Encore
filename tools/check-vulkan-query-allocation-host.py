#!/usr/bin/env python3
"""Count real query-sync destination allocations and preserve locked acquisitions.

Executes the pinned and maintained buffer-acquisition blocks under ASan/UBSan.
No Vulkan driver, guest progress or PS5 frame-time measurement is performed.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def block(path):
    text = path.read_text().split("void QueryCacheRuntime::SyncValues(", 1)[1]
    begin, end = "    // Vulkan part.", "\n    VkBuffer src_buffer"
    assert text.count(begin) == 1
    tail = text.split(begin, 1)[1]
    assert tail.count(end) == 1
    body = tail.split(end, 1)[0]
    if "    // Prepare all query metadata" in text:
        body = "    const size_t groups = impl->little_cache.size();\n" + body
    return body


pinned = block(ROOT / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_query_cache.cpp")
active = block(ROOT / "vendor/encore-active/eden-vulkan/vulkan_query_cache.cpp")
assert "reserve(" not in pinned
assert active.index(".reserve(") < active.index("std::scoped_lock")
for workflow in ("encore-core-preflight.yml", "encore-core-fast-gate.yml"):
    assert "python3 -B tools/check-vulkan-query-allocation-host.py" in (
        ROOT / ".github/workflows" / workflow).read_text()

cpp = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <mutex>
#include <utility>
#include <vector>
using u32 = std::uint32_t;
using VkBuffer = std::uint64_t;
using VkDeviceSize = std::uint64_t;
using DAddr = std::uint64_t;
static bool locked = false;
static unsigned allocations = 0, locked_allocations = 0;
template <class T> struct Allocator : std::allocator<T> {
    template <class U> struct rebind { using other = Allocator<U>; };
    T* allocate(std::size_t n) {
        ++allocations;
        locked_allocations += locked;
        return std::allocator<T>::allocate(n);
    }
};
struct Mutex {
    void lock() { assert(!locked); locked = true; }
    void unlock() { assert(locked); locked = false; }
};
namespace VideoCommon {
enum class ObtainBufferSynchronize { FullSynchronize };
enum class ObtainBufferOperation { DoNothing };
}
struct Buffer {
    VkBuffer handle{};
    VkBuffer Handle() const { return handle; }
};
struct Cache {
    Mutex mutex;
    Buffer buffer;
    unsigned operations = 0;
    std::vector<std::pair<DAddr, u32>> requests;
    template <class F> void BufferOperations(F&& f) {
        assert(locked);
        ++operations;
        f();
    }
    auto ObtainCPUBuffer(DAddr address, u32 size,
                         VideoCommon::ObtainBufferSynchronize sync,
                         VideoCommon::ObtainBufferOperation op) {
        assert(locked);
        assert(sync == VideoCommon::ObtainBufferSynchronize::FullSynchronize);
        assert(op == VideoCommon::ObtainBufferOperation::DoNothing);
        requests.emplace_back(address, size);
        buffer.handle = address + 17;
        return std::pair{&buffer, address % 4096};
    }
};
using Destinations = std::vector<std::pair<VkBuffer, VkDeviceSize>,
                                 Allocator<std::pair<VkBuffer, VkDeviceSize>>>;
struct Impl {
    std::vector<std::pair<DAddr, DAddr>> little_cache;
    Destinations buffers_to_upload_to;
    Cache buffer_cache;
};
void baseline(Impl* impl) {
PINNED
}
void maintained(Impl* impl) {
ACTIVE
}
int main() {
    unsigned worst_before = 0;
    for (const std::size_t count : {0U, 1U, 2U, 17U, 1024U}) {
        Impl old, current;
        for (std::size_t i = 0; i < count; ++i) {
            const DAddr address = 8192 * i + 4096;
            old.little_cache.emplace_back(address, address + 4096);
        }
        current.little_cache = old.little_cache;
        for (unsigned repeat = 0; repeat < 3; ++repeat) {
            allocations = locked_allocations = 0;
            baseline(&old);
            const auto before = locked_allocations;
            assert(!locked && allocations == before);
            allocations = locked_allocations = 0;
            maintained(&current);
            assert(!locked && locked_allocations == 0);
            assert(allocations == (count ? 1U : 0U));
            assert(old.buffer_cache.requests == current.buffer_cache.requests);
            assert(old.buffer_cache.operations == repeat + 1);
            assert(current.buffer_cache.operations == repeat + 1);
            assert(old.buffers_to_upload_to == current.buffers_to_upload_to);
            assert(current.buffers_to_upload_to.size() == count);
            for (std::size_t i = 0; i < count; ++i) {
                assert(current.buffers_to_upload_to[i].first ==
                       current.little_cache[i].first + 17);
                assert(current.buffers_to_upload_to[i].second == 0);
            }
            if (count == 1024) {
                assert(before > 1);
                worst_before = before;
            }
            // The production Record lambda owns these vectors until execution.
            // Swap guarantees an empty fresh vector for the next mock batch.
            Destinations old_recorded, recorded;
            old_recorded.swap(old.buffers_to_upload_to);
            recorded.swap(current.buffers_to_upload_to);
            assert(old_recorded == recorded);
        }
    }
    std::printf("QUERY_DESTINATIONS_PASS ranges=1024 before_locked=%u "
                "after_locked=0 after_total=1 repeated_batches=3\n", worst_before);
}
""".replace("PINNED", pinned).replace("ACTIVE", active)

compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-query-allocation-") as temp:
    path, executable = Path(temp) / "query.cpp", Path(temp) / "query"
    path.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    str(path), "-o", str(executable)], check=True, timeout=90)
    subprocess.run([str(executable)], check=True, timeout=30)
print("QUERY_DESTINATIONS_HOST_ONLY PS5_frametime=unmeasured")
