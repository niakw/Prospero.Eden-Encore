#!/usr/bin/env python3
"""Compile actual selected device spans and registry; reject stale native forks."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
native = (ROOT / 'vendor/encore-active/eden-core/overrides/core/device_memory_manager.inc').read_text()
backport = (ROOT / 'vendor/encore-active/eden-backports/src/core/device_memory_manager.inc').read_text()
pinned = (ROOT / 'vendor/sources/eden/src/core/device_memory_manager.inc').read_text()
header = (ROOT / 'vendor/encore-active/eden-backports/src/core/device_memory_manager.h').read_text()
# Whole-unit parity retains all atomic, remap, range and ASID fixes. Restoring
# only id_pool would compile while undoing the no-reuse/lifetime guarantees.
span_start = backport.index('template <typename Traits>\nu8* DeviceMemoryManager<Traits>::GetSpan(')
span_end = backport.index('template <typename Traits>\nvoid DeviceMemoryManager<Traits>::InnerGatherDeviceAddresses(', span_start)
original_span_block = backport[span_start:span_end]
old_return = '    return GetPointer<u8>(src_addr);'
new_return = ('    // Reuse the validated physical backing instead of loading the page again.\n'
              '    return GetPointerFromRaw<u8>((PAddr(backing - 1U) << page_bits) + (src_addr & page_mask));')
assert original_span_block.count(old_return) == 2
expected = backport[:span_start] + original_span_block.replace(old_return, new_return) + backport[span_end:]
assert native == expected, 'Native device implementation drifted beyond the reviewed span reuse'
assert 'id_pool' not in native + header
map_body = native.split('void DeviceMemoryManager<Traits>::Map(', 1)[1].split('void DeviceMemoryManager<Traits>::Unmap(', 1)[0]
assert map_body.index('std::shared_lock registry_lk(process_registry_guard);') < map_body.index('std::unique_lock lk(mapping_guard);')

assert 'mutable std::shared_mutex process_registry_guard;' in header
cmake = (ROOT / 'headless/CMakeLists.txt').read_text()
assert 'target_include_directories(video_core BEFORE PRIVATE "${EDEN_NATIVE_DIRTY_HEADER_ROOT}")' in cmake
assert '"${EDEN_NATIVE_DIRTY_HEADER_ROOT}/core/device_memory_manager.inc"' in cmake


def methods(text, start, end):
    assert text.count(start) == text.count(end) == 1
    return start + text.split(start, 1)[1].split(end, 1)[0]


start = 'template <typename Traits>\nu8* DeviceMemoryManager<Traits>::GetSpan('
end = 'template <typename Traits>\nvoid DeviceMemoryManager<Traits>::InnerGatherDeviceAddresses('
old_spans = methods(pinned, start, end)
spans = methods(native, start, end)
registry = methods(native, 'template <typename Traits>\nAsid DeviceMemoryManager<Traits>::RegisterProcess(',
                   'template <typename Traits>\nvoid DeviceMemoryManager<Traits>::UpdatePagesCachedCountNoLock(')
atomic_load = methods(header, '    static u32 AtomicLoadPhysical(', '    static void AtomicStorePhysical(')
cpp = r'''
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <limits>
#include <mutex>
#include <shared_mutex>
using u8 = std::uint8_t; using u32 = std::uint32_t;
using VAddr = std::uint64_t; using DAddr = std::uint64_t; using PAddr = std::uint64_t;
namespace Core {
namespace Memory { struct Memory {}; }
struct Asid { std::size_t id; };
struct Traits {};
template <typename T> struct DeviceMemoryManager {
    static constexpr std::size_t page_bits = 12, page_mask = 4095;
    static constexpr std::size_t device_as_size = std::size_t{1} << 34;
    // Exercise the real registry capacity expression with four possible IDs.
    static constexpr unsigned guest_max_as_bits = 62;
    struct TrackedEntry { VAddr cpu_backing_address{}; u32 continuity_tracker{}, compressed_physical_ptr{}; };
    std::array<TrackedEntry, 3> tracked_entries{};
    std::array<u32, 5> compressed_device_addr{};
    std::array<u8, 5 * 4096> storage{};
    mutable unsigned pointer_requests = 0, raw_requests = 0;
    mutable bool remap_on_pointer = false;
    template <class V> V* GetPointerFromRaw(PAddr offset) {
        ++raw_requests; assert(offset < storage.size());
        return reinterpret_cast<V*>(storage.data() + offset);
    }
    template <class V> const V* GetPointerFromRaw(PAddr offset) const {
        ++raw_requests; assert(offset < storage.size());
        return reinterpret_cast<const V*>(storage.data() + offset);
    }
    mutable std::shared_mutex process_registry_guard;
    std::deque<Memory::Memory*> registered_processes;
__ATOMIC__
    template <class V> V* GetPointer(DAddr address) {
        ++pointer_requests;
        // Deterministic remap at the old secondary lookup boundary.
        if (remap_on_pointer) {
            auto& entry = const_cast<TrackedEntry&>(tracked_entries[address >> page_bits]);
            entry.compressed_physical_ptr = 5;
        }
        auto physical = AtomicLoadPhysical(tracked_entries[address >> page_bits]);
        assert(physical && physical <= compressed_device_addr.size());
        return reinterpret_cast<V*>(storage.data() + (physical - 1) * 4096 + (address & page_mask));
    }
    template <class V> const V* GetPointer(DAddr address) const {
        ++pointer_requests;
        // Deterministic remap at the old secondary lookup boundary.
        if (remap_on_pointer) {
            auto& entry = const_cast<TrackedEntry&>(tracked_entries[address >> page_bits]);
            entry.compressed_physical_ptr = 5;
        }
        auto physical = AtomicLoadPhysical(tracked_entries[address >> page_bits]);
        assert(physical && physical <= compressed_device_addr.size());
        return reinterpret_cast<const V*>(storage.data() + (physical - 1) * 4096 + (address & page_mask));
    }
    u8* GetSpan(DAddr, std::size_t);
    const u8* GetSpan(DAddr, std::size_t) const;
    Asid RegisterProcess(Memory::Memory*);
    void UnregisterProcess(Asid);
};
__METHODS__
__REGISTRY__
}
int main(int argc, char**) {
    Core::DeviceMemoryManager<Core::Traits> mgr;
    const auto& read = mgr;
    auto& e = mgr.tracked_entries;
    e[0] = {0, 1, 1}; e[1] = {4096, 0, 2};
    if (argc > 1) {
        e[0] = {0, 2, 1}; e[1] = {4096, 1, 2}; e[2] = {8192, 0, 3};
        assert(mgr.GetSpan(0, 12288) == mgr.storage.data());
        // Leave stale predecessor hints while physically unmapping page 1.
        e[1].compressed_physical_ptr = 0; e[1].continuity_tracker = 0;
#ifdef CURRENT_DEVICE_SPAN
        assert(!mgr.GetSpan(0, 8192) && !read.GetSpan(0, 8192));
#else
        assert(mgr.GetSpan(0, 8192) == mgr.storage.data());
#endif
        // Default untracked remap to a different, noncontiguous physical page.
        e[1].compressed_physical_ptr = 5;
#ifdef CURRENT_DEVICE_SPAN
        assert(!mgr.GetSpan(0, 8192) && !read.GetSpan(0, 8192));
        assert(!mgr.GetSpan(4096, 8192) && !read.GetSpan(4096, 8192));
#else
        assert(mgr.GetSpan(0, 8192) == mgr.storage.data());
#endif
        assert(mgr.GetSpan(4096, 4096) == mgr.storage.data() + 4 * 4096);
        e[1].compressed_physical_ptr = 2; e[2].compressed_physical_ptr = 5;
#ifdef CURRENT_DEVICE_SPAN
        assert(!mgr.GetSpan(0, 12288) && !read.GetSpan(0, 12288));
#else
        assert(mgr.GetSpan(0, 12288) == mgr.storage.data());
#endif
        assert(mgr.GetSpan(0, 8192) == mgr.storage.data());
        std::puts("DEVICE_CONTINUITY_PASS partial_unmap=1 untracked_remap=1 const_mutable=2");
        return 0;
    }
#ifndef CURRENT_DEVICE_SPAN
    assert(mgr.GetSpan(1, std::numeric_limits<std::size_t>::max()) == mgr.storage.data() + 1);
    assert(read.GetSpan(1, std::numeric_limits<std::size_t>::max()) == mgr.storage.data() + 1);
    assert(mgr.GetSpan(0, 0) == mgr.storage.data());
#else
    assert(mgr.GetSpan(0, 4096) == mgr.storage.data());
    assert(read.GetSpan(1, 4096) == mgr.storage.data() + 1);
    assert(mgr.GetSpan(4094, 4) == mgr.storage.data() + 4094);
    for (const auto& [address, bytes] : std::array<std::pair<DAddr, std::size_t>, 9>{{
        {0, 8193}, {4095, 8193}, {0, 0}, {1, ~std::size_t{0}},
        {mgr.device_as_size, 1}, {mgr.device_as_size - 1, 2}, {~DAddr{0}, 4096},
        {8192, 1}, {8191, 2}}}) {
        assert(!mgr.GetSpan(address, bytes) && !read.GetSpan(address, bytes));
    }
    mgr.remap_on_pointer = true;
    assert(mgr.GetSpan(0, 8192) == mgr.storage.data());
    assert(read.GetSpan(0, 8192) == mgr.storage.data());
    assert(mgr.pointer_requests == 0 && mgr.raw_requests > 0);
    mgr.remap_on_pointer = false;
    e[0].compressed_physical_ptr = 6;
    assert(!mgr.GetSpan(0, 1) && !read.GetSpan(0, 1));
    e[0].compressed_physical_ptr = 5;
    assert(!mgr.GetSpan(4095, 2) && !read.GetSpan(4095, 2));
    Core::Memory::Memory a, b, c, d, extra;
    assert(mgr.RegisterProcess(nullptr).id == ~std::size_t{0});
    auto first = mgr.RegisterProcess(&a); assert(first.id == 0);
    mgr.UnregisterProcess(first); mgr.UnregisterProcess(first);
    mgr.UnregisterProcess({~std::size_t{0}});
    assert(mgr.RegisterProcess(&b).id == 1);
    assert(mgr.RegisterProcess(&c).id == 2);
    assert(mgr.RegisterProcess(&d).id == 3);
    assert(mgr.RegisterProcess(&extra).id == ~std::size_t{0});
    assert(mgr.registered_processes.size() == 4 && !mgr.registered_processes[0]);
#endif
    std::puts("DEVICE_BOUNDS_REGISTRY_PASS overflow=1 physical_capacity=1 tombstones=1 no_reuse=1");
}
'''
compiler = shutil.which('clang++-18') or shutil.which('clang++') or shutil.which('g++')
assert compiler
continuity = '--continuity' in sys.argv[1:]
with tempfile.TemporaryDirectory(prefix='encore-device-span-') as temp:
    folder = Path(temp)
    variants = [('pinned', old_spans, False), ('native', spans, True)]
    if not continuity:
        variants.append(('secondary-lookup', original_span_block, True))
    for label, segment, current in variants:
        path, binary = folder / (label + '.cpp'), folder / label
        path.write_text(cpp.replace('__ATOMIC__', atomic_load).replace('__METHODS__', segment)
                        .replace('__REGISTRY__', registry if current else ''))
        flags = ['-DCURRENT_DEVICE_SPAN=1'] if current else []
        subprocess.run([compiler, '-std=c++20', '-O1', '-Wall', '-Wextra', '-Werror',
                        '-DPS5_NATIVE=1', *flags,
                        '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                        str(path), '-o', str(binary)], check=True, timeout=60)
        if label == 'secondary-lookup':
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            assert result.returncode != 0 and 'mgr.GetSpan(0, 8192)' in result.stderr, result.stderr
            print('ORIGINAL_DEVICE_SPAN_SECONDARY_RELOOKUP_REPRODUCED')
        else:
            subprocess.run([str(binary), *(['continuity'] if continuity else [])], check=True, timeout=15)
print('NATIVE_DEVICE_SELECTED_IMPLEMENTATION_PASS mode=' + ('continuity' if continuity else 'bounds-registry'))
