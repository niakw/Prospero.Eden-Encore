#!/usr/bin/env python3
"""R437: buffer registration must not skip HUD texture or shader invalidation."""
from pathlib import Path
import shutil, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
cm=(root/'headless/CMakeLists.txt').read_text()
r=(root/'vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp').read_text()
g=(root/'tools/prepare-vulkan-port.py').read_text()
source=(root/'vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h').read_text()
maintained=(root/'vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h').read_text()
assert 'write_derived("${PORT_BUILD_DIR}/buffer-pages/video_core/buffer_cache/buffer_cache.h"' not in cm
assert 'configure_file("${EDEN_MAINTAINED_BUFFER_PAGES}"' in cm
assert 'target_include_directories(video_core BEFORE PRIVATE "${PORT_BUILD_DIR}/buffer-pages" "${EDEN_PORT_DIR}")' in cm
old_reg = '    const auto size = buffer.SizeBytes();\n    if (insert) {\n        total_used_memory += Common::AlignUp(size, 1024);'
new_reg = '    const auto size = buffer.SizeBytes();\n    if (insert) {\n        ::Eden::BufferPages::Mark(buffer.CpuAddr(), size);\n        total_used_memory += Common::AlignUp(size, 1024);'
assert source.count(old_reg)==1
expected = '#include "buffer_pages.h"\n' + source.replace(old_reg, new_reg)
# DMA copy's byte count also reaches FindBuffer(u32); never truncate a
# >4 GiB span, and do not touch dirty-range bookkeeping on empty copies.
copy_old = "bool BufferCache<P>::DMACopy(GPUVAddr src_address, GPUVAddr dest_address, u64 amount) {\n    const std::optional<DAddr> cpu_src_address = gpu_memory->GpuToCpuAddress(src_address);"
copy_new = "bool BufferCache<P>::DMACopy(GPUVAddr src_address, GPUVAddr dest_address, u64 amount) {\n    // FindBuffer and SynchronizeBuffer accept u32 byte spans. Never truncate\n    // a wider DMA request: the caller can take its ordinary software path.\n    // Reject empty copies before dirty-range bookkeeping as well.\n    if (amount == 0 || amount > static_cast<u64>(~u32{0})) {\n        return false;\n    }\n    const std::optional<DAddr> cpu_src_address = gpu_memory->GpuToCpuAddress(src_address);"
assert expected.count(copy_old) == 1
expected = expected.replace(copy_old, copy_new)
# DMA clear's amount is a word count, unlike byte-based cache registration.
begin = expected.index('bool BufferCache<P>::DMAClear(')
end = expected.index('\ntemplate <class P>', begin)
clear = expected[begin:end]
old_clear = '    const bool dest_dirty = IsRegionRegistered(*cpu_dst_address, amount);'
assert clear.count(old_clear) == 1
clear = clear.replace('    const size_t size = amount * sizeof(u32);\n', '').replace(
    old_clear, '    // FindBuffer accepts a u32 byte span; never truncate or issue an empty fill.\n'
    '    if (amount == 0 || amount > static_cast<u64>(~u32{0}) / sizeof(u32)) {\n'
    '        return false;\n'
    '    }\n'
    '    // The DMA amount counts u32 values; registration is measured in bytes.\n'
    '    const size_t size = amount * sizeof(u32);\n'
    '    const bool dest_dirty = IsRegionRegistered(*cpu_dst_address, size);')
expected = expected[:begin] + clear + expected[end:]
# Native-only ownership scan fix. The shipping backport remains immutable,
# and its bytes are still verified against the pinned manifest.
region_before = "bool BufferCache<P>::IsRegionRegistered(DAddr addr, size_t size) {\n    const DAddr end_addr = addr + size;"
region_after = "bool BufferCache<P>::IsRegionRegistered(DAddr addr, size_t size) {\n    // An empty CPU write does not overlap any registered cache buffer.\n    if (size == 0) {\n        return false;\n    }\n    const DAddr end_addr = addr + size;"
region_skip_before = "        if (buf_start_addr < end_addr && addr < buf_end_addr) {\n            return true;\n        }\n        page = Common::DivCeil(end_addr, CACHING_PAGESIZE);"
region_skip_after = "        if (buf_start_addr < end_addr && addr < buf_end_addr) {\n            return true;\n        }\n        // The first page can contain a buffer ending before addr. A later\n        // page may belong to another registered buffer intersecting the span.\n        // Do not skip all remaining pages after one non-overlapping owner.\n        ++page;"
assert expected.count(region_before) == expected.count(region_skip_before) == 1
expected = expected.replace(region_before, region_after).replace(
    region_skip_before, region_skip_after)
# Native-only zero-tick GPU fence fast path: the scheduler cannot wait
# for tick zero, and the shipping backport remains byte-for-byte pinned.
zero_tick_before = "        const u64 buffer_tick = buffer.getWriteTick();\n        if (!runtime.IsFree(buffer_tick)) {\n            runtime.Wait(buffer_tick);\n        }"
zero_tick_after = "        const u64 buffer_tick = buffer.getWriteTick();\n        // New and never-GPU-written buffers have a zero fence tick.\n        // Scheduler::Wait(0) cannot wait; skip its IsFree semaphore probe.\n        if (buffer_tick != 0 && !runtime.IsFree(buffer_tick)) {\n            runtime.Wait(buffer_tick);\n        }"
assert expected.count(zero_tick_before) == 1
expected = expected.replace(zero_tick_before, zero_tick_after)
# Native-only unmapped uniform CBUF guard. A missing GPU-to-CPU
# translation must clear the previous slot binding without optional UB.
unmapped_uniform_before = "    const std::optional<DAddr> device_addr = gpu_memory->GpuToCpuAddress(gpu_addr);\n    const Binding binding{\n        .device_addr = *device_addr,\n        .size = size,\n        .buffer_id = BufferId{},\n    };"
unmapped_uniform_after = "    const std::optional<DAddr> device_addr = gpu_memory->GpuToCpuAddress(gpu_addr);\n    if (!device_addr) {\n        // An unmapped cbuf is not a valid CPU-backed GPU buffer. Retire any\n        // previous slot binding instead of dereferencing an empty optional.\n        channel_state->uniform_buffers[stage][index] = NULL_BINDING;\n        return;\n    }\n    const Binding binding{\n        .device_addr = *device_addr,\n        .size = size,\n        .buffer_id = BufferId{},\n    };"
assert expected.count(unmapped_uniform_before) == 1
expected = expected.replace(unmapped_uniform_before, unmapped_uniform_after)
# Native-only vertex buffer extent hardening: never truncate a 64-bit
# guest GPU range to u32 before checking the exclusive-end bounds.
vertex_extent_old = "    const u32 address_size = static_cast<u32>(gpu_addr_end - gpu_addr_begin);\n    u32 size = address_size; // TODO: Analyze stride and number of vertices"
vertex_extent_new = "    // GPU addresses are 64-bit. Truncating the range before validation\n    // could turn a valid >=4 GiB vertex span into zero or a tiny buffer.\n    const u64 address_size =\n        gpu_addr_end > gpu_addr_begin ? gpu_addr_end - gpu_addr_begin : 0;\n    u32 size = static_cast<u32>((std::min)(address_size, static_cast<u64>(~u32{0})));"
vertex_clip_old = "    if (!gpu_memory->IsWithinGPUAddressRange(gpu_addr_end) || size >= 64_MiB) {\n        size = static_cast<u32>(gpu_memory->MaxContinuousRange(gpu_addr_begin, size));\n    }\n    const BufferId buffer_id = FindBuffer(*device_addr, size, false);"
vertex_clip_new = "    if (!gpu_memory->IsWithinGPUAddressRange(gpu_addr_end) || size >= 64_MiB) {\n        size = static_cast<u32>(gpu_memory->MaxContinuousRange(gpu_addr_begin, size));\n        if (size == 0) {\n            // No mapped contiguous data: never create a zero-byte vertex\n            // buffer or retain the previous draw's vertex binding.\n            channel_state->vertex_buffers[index] = NULL_BINDING;\n            UpdateVertexBufferSlot(index, NULL_BINDING);\n            return;\n        }\n    }\n    const BufferId buffer_id = FindBuffer(*device_addr, size, false);"
assert expected.count(vertex_extent_old) == expected.count(vertex_clip_old) == 1
expected = expected.replace(vertex_extent_old, vertex_extent_new).replace(vertex_clip_old, vertex_clip_new)
# Native-only index buffer extent hardening: detect 64-bit GPU limits and
# 32-bit index arithmetic overflow before converting to FindBuffer(u32).
index_before = "    const u32 address_size = static_cast<u32>(gpu_addr_end - gpu_addr_begin);\n    const u32 draw_size = (index_buffer_ref.count + index_buffer_ref.first) * u32(index_buffer_ref.FormatSizeInBytes());\n    const u32 size = (std::min)(address_size, draw_size);"
index_after = "    // Both the GPU range and (first + count) * format size can exceed\n    // 32 bits. Compare their full widths before bounding FindBuffer(u32).\n    const u64 address_size =\n        gpu_addr_end > gpu_addr_begin ? gpu_addr_end - gpu_addr_begin : 0;\n    const u64 index_count =\n        static_cast<u64>(index_buffer_ref.count) + index_buffer_ref.first;\n    const u64 draw_size = index_count * index_buffer_ref.FormatSizeInBytes();\n    const u32 size = static_cast<u32>((std::min)(\n        (std::min)(address_size, draw_size), static_cast<u64>(~u32{0})));"
assert expected.count(index_before) == 1
expected = expected.replace(index_before, index_after)
# Native-only indirect draw extent validation; preserve source replay.
indirect_before = "    const auto update = [this](GPUVAddr gpu_addr, size_t size, Binding& binding) {\n        const std::optional<DAddr> device_addr = gpu_memory->GpuToCpuAddress(gpu_addr);"
indirect_after = "    const auto update = [this](GPUVAddr gpu_addr, size_t size, Binding& binding) {\n        // The binding and FindBuffer accept u32 bytes. An empty or wider\n        // indirect command range must not wrap into a valid-looking buffer.\n        if (size == 0 || size > static_cast<size_t>(~u32{0})) {\n            binding = NULL_BINDING;\n            return;\n        }\n        const std::optional<DAddr> device_addr = gpu_memory->GpuToCpuAddress(gpu_addr);"
assert expected.count(indirect_before) == 1
expected = expected.replace(indirect_before, indirect_after)
assert maintained == expected, "R437 maintained header differs from reviewed transforms"
assert maintained.count('::Eden::BufferPages::Mark(buffer.CpuAddr(), size);') == 1
assert 'buffer-pages/video_core/buffer_cache/buffer_cache.h' in cm
assert r.count('::Eden::BufferPages::NeverRegistered(addr, size)')==8
# Five newer sites extend the original R437 witnesses: the batched path,
# two single-range invalidations, and CPU unmap. These optimizations must
# preserve shader/texture invalidation and unknown-memory fallback.
assert 'bool buffer_may_overlap = false;' in r
assert 'if (buffer_may_overlap)' in r
witness=(root/'headless/buffer_pages.h').read_text()
assert 'registered[word].load(std::memory_order_acquire) & mask' in witness
assert 'registered[word].fetch_or(mask,std::memory_order_release)' in witness
assert g.count('::Eden::BufferPages::NeverRegistered(addr, size)')==8
pos=r.index('bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size)')
body=r[pos:r.index('void RasterizerVulkan::OnCacheInvalidation',pos)]
assert body.index('::Eden::BufferPages::NeverRegistered') < body.index(
    '::Eden::Performance::GuestCacheLock(buffer_cache.mutex, false)')
assert body.index('::Eden::Performance::GuestCacheLock(buffer_cache.mutex, false)') < body.index(
    'texture_cache.WriteMemory(addr, size);') < body.index(
    'pipeline_cache.InvalidateRegion(addr, size);')
assert body.count('texture_cache.WriteMemory(addr, size);')==1
assert body.count('pipeline_cache.InvalidateRegion(addr, size);')==1
cxx=shutil.which('c++') or shutil.which('clang++') or shutil.which('g++')
assert cxx
cpp=r"""
#include "buffer_pages.h"
#include <cassert>
#include <thread>
#include <vector>
int main(){
 using namespace Eden::BufferPages;
 constexpr std::uint64_t p=4096;
 assert(NeverRegistered(0,1));
 assert(!NeverRegistered(0,0) && !NeverRegistered(kSpace,1));
 assert(!NeverRegistered(0,64*p+1) && !NeverRegistered(kSpace-1,2));
 Mark(0,1);
 assert(!NeverRegistered(0,1) && NeverRegistered(p,1));
 // A previously marked word stays marked on repeated registrations.
 Mark(100*p,1);
 const auto word = (100ull*p >> kPageBits) / 64;
 const auto previous = registered[word].load(std::memory_order_acquire);
 for(unsigned n=0;n<2000;++n) Mark(100*p,1);
 assert(registered[word].load(std::memory_order_acquire)==previous);
 // Concurrent overlapping and disjoint writers within one bitmap word
 // must never lose either registration on the conditional fast path.
 std::vector<std::thread> overlapping;
 for(unsigned t=0;t<8;++t)overlapping.emplace_back([t]{
   for(unsigned n=0;n<1000;++n) {
     Mark((128+t)*p, 1);
     Mark(128*p, 8*p);
   }
 });
 for(auto& task:overlapping)task.join();
 for(unsigned t=0;t<8;++t)assert(!NeverRegistered((128+t)*p,1));
 Mark(63*p+7,2*p);
 assert(!NeverRegistered(63*p,1) && !NeverRegistered(64*p,1));
 assert(!NeverRegistered(65*p,1) && NeverRegistered(66*p,p));
 std::vector<std::thread> jobs;
 for(unsigned t=0;t<8;t++)jobs.emplace_back([t]{
    const auto b=(1000000ull+t*1000ull)*4096ull;
    for(unsigned n=0;n<512;n++)Mark(b+n*4096,1);
 });
 for(auto& j:jobs)j.join();
 for(unsigned t=0;t<8;t++){
   const auto b=(1000000ull+t*1000ull)*4096ull;
   assert(!NeverRegistered(b,1));
   assert(!NeverRegistered(b+511*p,1));
   assert(NeverRegistered(b+512*p,1));
 }
 Mark(kSpace+1,1);
 assert(!NeverRegistered(66*p,1));
}
"""
with tempfile.TemporaryDirectory(prefix='eden-r437-') as d:
 src=Path(d)/'b.cpp';exe=Path(d)/'b'
 src.write_text(cpp)
 subprocess.run([cxx,'-std=c++20','-O1','-pthread','-Wall','-Wextra','-Werror',
  '-fsanitize=undefined','-I'+str(root/'headless'),str(src),'-o',str(exe)],check=True,timeout=90)
 subprocess.run([str(exe)],check=True,timeout=90)
print('PASS R437 buffer-page witness and protected HUD invalidation')
