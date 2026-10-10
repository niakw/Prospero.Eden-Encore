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
assert '({hint, remaining_pages, tracked_entries.size() - page_index})' in p
assert 'std::atomic<std::uint64_t> reads{0}, writes{0}' in h
assert 'return n <= 8 || (n & (n - 1)) == 0;' in h
assert 'target_include_directories(video_core PRIVATE "${EDEN_PORT_DIR}")' in c
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
