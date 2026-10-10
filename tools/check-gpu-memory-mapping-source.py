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
def sample(i): return i<=8 or i&(i-1)==0
assert [i for i in range(1,129) if sample(i)] == [1,2,3,4,5,6,7,8,16,32,64,128]
print('PASS source: physical continuity, PS5 shared-cache bypass, bounded fault logs')
print('Hardware graphics, game stability, frame pacing: NOT VERIFIED')
