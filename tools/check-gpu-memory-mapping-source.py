#!/usr/bin/env python3
"""Source-only pinned PS5 GPU remap/alias regression; NOT console qualification."""
from pathlib import Path
r=Path(__file__).resolve().parents[1]
p=(r/'headless/backports/eden-ps5-gpu-memory-mapping.patch').read_text()
h=(r/'headless/gpu_fault_rate_limit.h').read_text()
c=(r/'headless/CMakeLists.txt').read_text()
apply=(r/'tools/apply-eden-backports.sh').read_text()
perf=(r/'headless/performance.cpp').read_text()
for need in ('invalid.continuity_tracker = 0;', 'valid.continuity_tracker = 0;',
             'entry.continuity_tracker = 0;', 'observed == first_backing + n',
             'tracked_entries[first_page + i].compressed_physical_ptr != backing + i'):
    assert need in p, need
assert p.count('#ifndef PS5_NATIVE') == 4
assert p.count('::Eden::GpuFault::ShouldReportRead()') == 2
assert p.count('::Eden::GpuFault::ShouldReportWrite()') == 2
assert 'const size_t remaining_pages = 1 + ((remaining_size - 1 + page_offset) >> Memory::YUZU_PAGEBITS);' in p
assert 'if (addr >= device_as_size || size > device_as_size - addr)' in p
assert p.count('if (address >= device_as_size) return nullptr;') == 2
assert p.count('&& address < device_as_size && size <= device_as_size - address') == 2
assert '({hint, remaining_pages, tracked_entries.size() - page_index})' in p
assert 'std::atomic<std::uint64_t> reads{0}, writes{0}' in h
assert 'return n <= 8 || (n & (n - 1)) == 0;' in h
assert 'target_include_directories(video_core PRIVATE "${EDEN_PORT_DIR}")' in c
# Upstream core/video_core do not inherit PS5_NATIVE from the executable/common.
# Scope the define to precisely the rewritten memory.cpp and GPU manager TU.
assert 'set(eden_cpu_memory_tu "${PORT_BUILD_DIR}/memory.cpp")' in c
assert 'set(eden_cpu_memory_tu "${PROJECT_SOURCE_DIR}/src/core/memory.cpp")' in c
assert 'set_property(SOURCE "${eden_cpu_memory_tu}" TARGET_DIRECTORY core' in c
assert 'set_property(SOURCE "${PROJECT_SOURCE_DIR}/src/video_core/host1x/gpu_device_memory_manager.cpp"' in c
assert c.count('APPEND PROPERTY COMPILE_DEFINITIONS "PS5_NATIVE=1"') >= 2
assert 'validate_ps5_gpu_memory_mapping' in apply
reverse=(r/'headless/backports/eden-ps5-gpu-remap-reverse.patch').read_text()
for needle in ('previous_physical == replacement_physical',
               'compressed_device_addr.GetAndFault(previous_physical - 1U)',
               'impl->multi_dev_address.Unregister(', 'EDEN_GPU_REMAP_REVERSE_MISMATCH'):
    assert needle in reverse, needle
assert 'validate_ps5_gpu_remap_reverse' in apply
unmap=(r/'headless/backports/eden-ps5-gpu-unmap-reverse-guard.patch').read_text()
assert 'base_dev != retiring_page' in unmap
assert 'EDEN_GPU_UNMAP_REVERSE_MISMATCH' in unmap
assert 'validate_ps5_gpu_unmap_reverse' in apply
multi=(r/'headless/backports/eden-ps5-gpu-multi-missing-guard.patch').read_text()
for token in ('bool Contains(u32 value, u32 start_entry) const noexcept',
              'EDEN_GPU_REMAP_MULTI_MISSING', 'EDEN_GPU_UNMAP_MULTI_MISSING'):
    assert token in multi, token
assert 'validate_ps5_gpu_multi_missing' in apply
map_bounds=(r/'headless/backports/eden-ps5-gpu-map-bounds.patch').read_text()
for token in ('virtual_address >= guest_as_size', 'size > guest_as_size - virtual_address',
              'EDEN_GPU_MAP_BAD_RANGE', 'EDEN_GPU_UNMAP_BAD_RANGE'):
    assert token in map_bounds, token
assert 'validate_ps5_gpu_map_bounds' in apply
physical=(r/'headless/backports/eden-ps5-gpu-physical-capacity.patch').read_text()
for token in ('GetIntendedMemorySize() >> Memory::YUZU_PAGEBITS', 'EDEN_GPU_MAP_OUTSIDE_DRAM',
              'EDEN_GPU_REVERSE_PHYS_OOB', 'compressed_device_addr.size()'):
    assert token in physical, token
assert 'validate_ps5_gpu_physical_capacity' in apply
cache_remap=(r/'headless/backports/eden-ps5-gpu-remap-cache-invalidate.patch').read_text()
for token in ('std::unique_lock lk(mapping_guard);', 'replaced_gpu_mapping = true;',
              'lk.unlock();', 'device_inter->InvalidateRegion(address, size);'):
    assert token in cache_remap, token
assert 'remap_cache_evictions.fetch_add' in cache_remap
assert 'validate_ps5_gpu_remap_invalidation' in apply
empty_multi=(r/'headless/backports/eden-ps5-gpu-empty-multi-head.patch').read_text()
assert 'first != 0 ? impl->multi_dev_address.ReleaseEntry(first) : 0' in empty_multi
assert 'new_start != 0 ? impl->multi_dev_address.ReleaseEntry(new_start) : 0' in empty_multi
assert 'validate_ps5_gpu_empty_multi_head' in apply
inline_bounds=(r/'headless/backports/eden-ps5-gpu-reverse-inline-bounds.patch').read_text()
for token in ('if ((address >> page_bits) >= compressed_device_addr.size()) return;',
              'if (base == 0) return;', 'if (host < physical_base ||',
              'if (address >= device_as_size) return 0;'):
    assert token in inline_bounds, token
assert 'validate_ps5_gpu_reverse_inline' in apply
assert 'inline bool ShouldReportBadPhysical() noexcept' in h
assert 'bad_map_range=%llu bad_unmap_range=%llu' in perf
assert 'remap_replaced=%llu remap_mismatch=%llu' in perf
assert 'EDEN_GPU_UNMAPPED_COUNTERS read=%llu write=%llu guest_map_zero=%llu guest_null_mapped=%llu' in perf
diagnostics=(r/'headless/backports/eden-ps5-guest-mapping-diagnostics.patch').read_text()
for needle in ('EDEN_GUEST_MAP_POINTER_ZERO', 'EDEN_GUEST_MAPPED_NULL_POINTER',
               'ShouldReportGuestMapZero()', 'ShouldReportGuestNullMapped()'):
    assert needle in diagnostics, needle
assert 'validate_ps5_guest_mapping_diagnostics' in apply
walk=(r/'headless/backports/eden-ps5-guest-walk.patch').read_text()
assert 'The PS5\'s read-only shared-zero sparse slots are safe to inspect.' in walk
assert 'on_unmapped(offset, copy_amount, current_vaddr);' in walk
assert 'validate_ps5_guest_walk_memory' in apply
zero_alias=(r/'headless/backports/eden-ps5-guest-zero-alias.patch').read_text()
assert 'IsDirectBackingAlias(u64 address, std::size_t bytes) const' in zero_alias
assert 'GetIntendedMemorySize()' in zero_alias
assert 'guest_alias_mapped.fetch_add' in zero_alias
assert 'guest_alias_access.fetch_add' in zero_alias
assert 'validate_ps5_guest_zero_alias' in apply
span=(r/'headless/backports/eden-ps5-guest-span.patch').read_text()
assert '(addr + size - 1) >> YUZU_PAGEBITS' in span
assert 'if (p != delta || t != type || b != block) return nullptr;' in span
assert 'static_cast<const Impl&>(*this).GetSpan(addr, size)' in span
assert 'validate_ps5_guest_span' in apply
assert 'guest_alias_mapped=%llu guest_alias_access=%llu' in perf
main=(r/'headless/main.cpp').read_text()
assert '#include "gpu_fault_rate_limit.h"' in main
assert '::Eden::GpuFault::ResetTitleCounters();' in main
assert 'inline void ResetTitleCounters() noexcept' in h
assert h.count('.store(0, std::memory_order_relaxed);') >= 12
def sample(i): return i<=8 or i&(i-1)==0
assert [i for i in range(1,129) if sample(i)] == [1,2,3,4,5,6,7,8,16,32,64,128]
print('PASS source: physical continuity, PS5 shared-cache bypass, bounded fault logs')
print('Hardware graphics, game stability, frame pacing: NOT VERIFIED')
