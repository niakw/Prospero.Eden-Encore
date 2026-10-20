#!/usr/bin/env python3
"""Execute the complete real query-sync method, including deferred copy ownership."""
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'vendor/encore-active/eden-vulkan/vulkan_query_cache.cpp').read_text()
start = source.index('void QueryCacheRuntime::SyncValues(')
method = source[start:source.index('\n} // namespace Vulkan', start)]
# Preserve the exact preceding implementation as an allocation/locking witness.
oracle = ast.parse((ROOT / 'tools/prepare-vulkan-port.py').read_text())
for node in ast.walk(oracle):
    if isinstance(node, ast.Tuple) and len(node.elts) == 2:
        if all(isinstance(x, ast.Constant) and isinstance(x.value, str) for x in node.elts):
            before, after = (x.value for x in node.elts)
            if before.startswith('    // Vulkan part.') and after.startswith('    // Prepare all query metadata'):
                assert method.count(after) == 1
                previous = method.replace(after, before)
                break
else:
    raise AssertionError('complete historical copy block missing')
cpp = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <random>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>
using u32 = std::uint32_t; using u64 = std::uint64_t; using DAddr = u64;
using VkBuffer = u64; using VkDeviceSize = u64;
struct VkBufferCopy { u64 srcOffset, dstOffset, size; };
namespace Core { constexpr DAddr DEVICE_PAGESIZE = 4096; }
namespace Common { DAddr AlignDown(DAddr n, DAddr a) { return n - n % a; } }
namespace VideoCommon {
enum class ObtainBufferSynchronize { FullSynchronize };
enum class ObtainBufferOperation { DoNothing };
}
static bool locked;
static unsigned copy_allocations, locked_copies, locked_uploads;
void CopyBytes(void* destination, const void* source, std::size_t bytes) {
    if (locked) ++locked_uploads;
    std::memcpy(destination, source, bytes);
}
template <class T> struct CopyAllocator : std::allocator<T> {
    template <class U> struct rebind { using other = CopyAllocator<U>; };
    CopyAllocator() = default;
    template <class U> CopyAllocator(const CopyAllocator<U>&) {}
    T* allocate(std::size_t n) {
        ++copy_allocations; if (locked) ++locked_copies;
        return std::allocator<T>::allocate(n);
    }
    template <class U> bool operator==(const CopyAllocator<U>&) const { return true; }
};
using Copies = std::vector<VkBufferCopy, CopyAllocator<VkBufferCopy>>;
struct Mutex {
    void lock() { assert(!locked); locked = true; }
    void unlock() { assert(locked); locked = false; }
};
struct Registry {
    std::map<VkBuffer, std::vector<unsigned char>> sources;
    struct Destination { DAddr address; u64 offset; };
    std::map<VkBuffer, Destination> destinations;
    std::map<DAddr, unsigned char> written, expected;
    VkBuffer next_source = 100, next_destination = 10000;
};
namespace vk {
struct CommandBuffer {
    Registry* registry;
    template <class Range> void CopyBuffer(VkBuffer src, VkBuffer dst, const Range& copies) {
        assert(!locked);
        const auto& bytes = registry->sources.at(src);
        const auto destination = registry->destinations.at(dst);
        for (const auto& copy : copies) {
            assert(copy.srcOffset <= bytes.size() && copy.size <= bytes.size() - copy.srcOffset);
            assert(copy.dstOffset >= destination.offset);
            const auto address = destination.address + copy.dstOffset - destination.offset;
            for (std::size_t i = 0; i < copy.size; ++i)
                registry->written[address + i] = bytes[copy.srcOffset + i];
        }
    }
};
}
enum class MemoryUsage { Upload };
struct StagingBufferRef { VkBuffer buffer{}; u64 offset{}; std::span<unsigned char> mapped_span; };
struct StagingPool {
    Registry* registry;
    StagingBufferRef Request(std::size_t size, MemoryUsage) {
        assert(locked); // Preserve staging tick assignment after buffer acquisition.
        const auto buffer = registry->next_source++;
        auto& bytes = registry->sources[buffer]; bytes.resize(size + 32);
        return {buffer, 32, std::span<unsigned char>(bytes).subspan(32)};
    }
};
struct BufferCache {
    Mutex mutex;
    Registry* registry;
    bool repeat_next = false, merged = false;
    struct Buffer { VkBuffer handle; VkBuffer Handle() const { return handle; } } current;
    template <class F> void BufferOperations(F&& operation) {
        assert(locked); operation();
        if (repeat_next) {
            registry->destinations.clear(); // previous handles were invalidated by a merge
            repeat_next = false; merged = true; operation();
        }
    }
    auto ObtainCPUBuffer(DAddr address, u32 size, VideoCommon::ObtainBufferSynchronize,
                         VideoCommon::ObtainBufferOperation) {
        assert(locked && size && address % 4096 == 0);
        if (merged) {
            current.handle = 1;
            registry->destinations[1] = Registry::Destination{0, 0};
            return std::pair{&current, address};
        }
        current.handle = registry->next_destination++;
        registry->destinations.emplace(current.handle, Registry::Destination{address, 64});
        return std::pair{&current, u64{64}};
    }
};
struct Scheduler {
    Registry* registry;
    std::vector<std::function<void(vk::CommandBuffer)>> commands;
    void RequestOutsideRenderPassOperationContext() { assert(locked); }
    template <class F> void Record(F&& command) {
        assert(locked); commands.emplace_back(std::forward<F>(command));
    }
    void Execute() {
        for (auto& command : commands) command(vk::CommandBuffer{registry});
        commands.clear();
    }
};
struct Impl {
    Registry registry;
    std::vector<std::pair<DAddr, DAddr>> little_cache;
    std::vector<std::pair<VkBuffer, VkDeviceSize>> buffers_to_upload_to;
    std::vector<std::size_t> redirect_cache, sync_order, copy_offsets, copy_cursors;
#ifdef OLD_COPY_SETUP
    std::vector<Copies> copies_setup;
#else
    Copies copies_setup;
#endif
    BufferCache buffer_cache{{}, &registry, false, false, {}};
    StagingPool staging_pool{&registry};
    Scheduler scheduler{&registry, {}};
};
struct QueryCacheRuntime {
    Impl storage;
    Impl* impl = &storage;
    template <class T> void SyncValues(std::span<T>, VkBuffer);
};
template <class SyncValuesType>
__METHOD__
template <bool Upload> struct Value {
    static constexpr bool GeneratesBaseBuffer = Upload;
    DAddr address; std::size_t size; u64 value; u64 offset;
};
template <bool Upload> void Queue(QueryCacheRuntime& runtime, unsigned count, unsigned seed) {
    auto& registry = runtime.storage.registry;
    auto& base = registry.sources[7]; base.resize(65536);
    for (std::size_t i = 0; i < base.size(); ++i) base[i] = static_cast<unsigned char>(i * 17);
    std::vector<Value<Upload>> values;
    for (unsigned i = 0; i < count; ++i)
        values.push_back({u64(i) * 8192 + (seed ? 4092 : 16), i % 2 ? 4u : 8u,
                          0xabcd123400000000ULL + i, u64(i) * 16});
    if (seed) { std::mt19937 rng(seed); std::shuffle(values.begin(), values.end(), rng); }
    // Multiple query results at one address must retain their original order.
    if (seed && count) {
        values.push_back(values.front()); values.back().value ^= 0x12345678;
        values.back().offset += 8;
    }
    for (const auto& value : values) {
        const auto* bytes = Upload ? reinterpret_cast<const unsigned char*>(&value.value)
                                   : base.data() + value.offset;
        for (std::size_t i = 0; i < value.size; ++i) registry.expected[value.address + i] = bytes[i];
    }
    runtime.SyncValues(std::span(values), 7);
    assert(!locked);
    // Input objects now die; recorded commands must own all copy metadata.
}
int main(int argc, char**) {
    QueryCacheRuntime runtime;
    if (argc > 1) {
        runtime.storage.buffer_cache.repeat_next = true;
        Queue<true>(runtime, 2, 0);
        runtime.storage.scheduler.Execute();
        assert(runtime.storage.registry.written == runtime.storage.registry.expected);
        std::puts("QUERY_COPY_REBUILD_PASS stale_handles_discarded=1");
        return 0;
    }
    Queue<true>(runtime, 1024, 0);
#ifdef OLD_COPY_SETUP
    assert(copy_allocations == 1024 && locked_copies == 1024 && locked_uploads == 1024);
#else
    assert(copy_allocations == 1 && locked_copies == 0 && locked_uploads == 1024);
#endif
    const auto first_allocations = copy_allocations;
    Queue<false>(runtime, 128, 31);
    Queue<true>(runtime, 17, 19);
    Queue<false>(runtime, 0, 0);
    // Scratch vectors have been overwritten by multiple later batches before
    // any worker command executes; captures must still contain the old plan.
    runtime.storage.scheduler.Execute();
    assert(runtime.storage.registry.written == runtime.storage.registry.expected);
    std::printf("QUERY_COPY_PLAN_PASS first_allocations=%u locked_copy_allocations=%u "
                "payload_copies_under_lock=%u upload_and_existing_buffer=1 deferred_batches=3\n",
                first_allocations, locked_copies, locked_uploads);
}
'''
compiler = shutil.which('clang++-18') or shutil.which('clang++') or shutil.which('g++')
assert compiler
with tempfile.TemporaryDirectory(prefix='encore-query-copy-plan-') as temp:
    for label, body in (('old', previous), ('flat', method)):
        path, binary = Path(temp) / (label + '.cpp'), Path(temp) / label
        path.write_text(cpp.replace('__METHOD__', body.replace('std::memcpy(', '::CopyBytes(')))
        flags = ['-DOLD_COPY_SETUP=1'] if label == 'old' else []
        subprocess.run([compiler, '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-fno-sanitize-recover=all', *flags,
                        str(path), '-o', str(binary)], check=True, timeout=90)
        subprocess.run([str(binary)], check=True, timeout=30)
        if label == 'flat':
            subprocess.run([str(binary), 'rebuild'], check=True, timeout=30)
        else:
            retry = subprocess.run([str(binary), 'rebuild'], capture_output=True, text=True, timeout=30)
            assert retry.returncode != 0, 'historical pre-lock clear incorrectly retained stale handles'
            print('PREVIOUS_BATCH_RETRY_REGRESSION_REJECTED')
print('QUERY_COPY_PLAN_HOST_ONLY native_GPU_frametimes_unmeasured')
