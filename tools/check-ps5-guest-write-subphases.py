#!/usr/bin/env python3
"""R370: compile actual sampled guest OnCPUWrite with fake caches and locks."""
from pathlib import Path
import os,subprocess,sys,tempfile

root=Path(__file__).resolve().parents[1]
active=(root/'vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp').read_text()
generator=(root/'tools/prepare-vulkan-port.py').read_text()
perf=(root/'headless/performance.h').read_text()
report=(root/'headless/performance.cpp').read_text()
method_start=active.index('bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {')
method_end=active.index('\nvoid RasterizerVulkan::OnCacheInvalidation(',method_start)
method=active[method_start:method_end]
assert 'ShouldSampleGuestWrite()' in method
assert method.count('CachePhaseTimer') == 5
assert method.count('GuestCacheLock(') == 2
assert 'if (!::Eden::ImagePages::NeverHeld(addr, size))' in method
assert 'cpu_write_ahead{0}' in perf
assert method.count('BufferWriteAhead::MarkFollowingPages') == 1
assert method.index('GuestWriteBufferWait') < method.index('GuestWriteBufferWork')
assert method.index('GuestWriteBufferWork') < method.index('GuestWriteTextureWait')
assert method.index('GuestWriteTextureWait') < method.index('GuestWriteTextureWork')
assert method.index('GuestWriteTextureWork') < method.index('GuestWriteShaderInvalidate')
assert method.index('buffer_cache.OnCPUWrite(addr, size)') < method.index('texture_cache.WriteMemory(addr, size)')
assert method.index('texture_cache.WriteMemory(addr, size)') < method.index('pipeline_cache.InvalidateRegion(addr, size)')
for token in ('GuestWriteBufferWait','GuestWriteBufferWork','GuestWriteTextureWait',
              'GuestWriteTextureWork','GuestWriteShaderInvalidate','ShouldSampleGuestWrite'):
    assert token in perf and token in active and token in generator,token
for name in ('guest_write_buffer_wait','guest_write_buffer_work','guest_write_texture_wait',
             'guest_write_texture_work','guest_write_shader_invalidate'):
    assert '"'+name+'"' in report,name
guest_lock=perf[perf.index('struct GuestCacheDomainTotals {'):
                perf.index('// R310:')]
cache_phase=perf[perf.index('enum class CachePhase : unsigned {'):
                 perf.index('// R361:')]
batch_timer=perf[perf.index('class BatchedGuestWriteTimer {'):
                 perf.index('// Opt-in API wall times:')]
assert 'if (++batch.calls == 64) batch.Flush();' in batch_timer
cpp=r"""
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include "buffer_write_ahead.h"
#include "image_pages.h"
#include <mutex>
#include <cstdio>
#if !defined(__x86_64__)
#define __builtin_ia32_pause() ((void)0)
#endif
using DAddr=std::uint64_t;
using u64=std::uint64_t;
#define DEBUG_ASSERT(x) assert(x)
namespace Common {
struct Clock {
    mutable std::atomic<unsigned long long> calls{};
    std::chrono::nanoseconds GetTimeNS() const {
        calls.fetch_add(1,std::memory_order_relaxed);
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
           std::chrono::steady_clock::now().time_since_epoch());
    }
};
inline Clock g_wall_clock{};
}
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{false};
inline std::atomic<unsigned> cache_lock_spins{0};
inline std::atomic<unsigned> cpu_write_ahead{0};
inline std::atomic<unsigned long long> cache_lock_contended{0}, cache_lock_blocked{0};
inline std::atomic<unsigned long long> cache_lock_wait_ns{0};
struct Totals {
    std::atomic<unsigned long long> calls{}, nanoseconds{};
};
inline Totals guest_cpu_write;
__BATCH_TIMER__
__GUEST_LOCK__
__CACHE_PHASE__
}
namespace Eden::BufferPages {
inline std::atomic<bool> test_skip_empty_page{false};
// The real bitmap has its own sanitizer test. Exercise the exact extracted
// RasterizerVulkan method here, with the fast/slow decision controlled.
inline bool NeverRegistered(DAddr,u64) {
    return test_skip_empty_page.load(std::memory_order_relaxed);
}
}
struct FakeBuffer {
    std::mutex mutex;
    bool hazard{};
    DAddr gpu_modified_page{};
    unsigned writes{};
    bool IsRegionRegistered(DAddr page, u64 bytes) { return page != 0 && bytes == 4096; }
    bool OnCPUWrite(DAddr address,u64) { ++writes; return hazard || (gpu_modified_page && gpu_modified_page == address); }
};
struct FakeTexture {
    std::mutex mutex;
    unsigned writes{};
    void WriteMemory(DAddr,u64) { ++writes; }
};
struct FakePipeline {
    unsigned invalidations{};
    void InvalidateRegion(DAddr,u64) { ++invalidations; }
};
struct RasterizerVulkan {
    FakeBuffer buffer_cache{};
    FakeTexture texture_cache{};
    FakePipeline pipeline_cache{};
    bool OnCPUWrite(DAddr,u64);
};
__ON_CPU_WRITE__
int main() {
    using namespace Eden::Performance;
    RasterizerVulkan r;
    // This legacy latency/sampling fixture models an image that has
    // already been registered. Its texture invalidation assertions must
    // therefore take the conservative locked route after the new page gate.
    ::Eden::ImagePages::Mark(1,4);
    assert(!::Eden::ImagePages::NeverHeld(1,4));
    for (int i=0;i<128;++i) assert(!r.OnCPUWrite(1,4));
    assert(Common::g_wall_clock.calls.load()==0);
    assert(guest_cpu_write.calls.load()==0);
    for (const auto& phase:cache_phase_totals) assert(phase.samples.load()==0);
    assert(r.buffer_cache.writes==128 && r.texture_cache.writes==128 &&
           r.pipeline_cache.invalidations==128);
    detailed_gpu_profile.store(true);
    for (int i=0;i<128;++i) assert(!r.OnCPUWrite(1,4));
    const CachePhase groups[] = {
        CachePhase::GuestWriteBufferWait, CachePhase::GuestWriteBufferWork,
        CachePhase::GuestWriteTextureWait, CachePhase::GuestWriteTextureWork,
        CachePhase::GuestWriteShaderInvalidate
    };
    for (CachePhase p:groups) assert(
        cache_phase_totals[static_cast<unsigned>(p)].samples.load()==2);
    assert(r.buffer_cache.writes==256 && r.texture_cache.writes==256 &&
           r.pipeline_cache.invalidations==256);
    assert(cache_lock_contended.load()==0 && cache_lock_blocked.load()==0);
    assert(guest_cpu_write.calls.load()==128);
    assert(guest_cpu_write.nanoseconds.load()>0);
    const auto reads=Common::g_wall_clock.calls.load();
    assert(reads>0);
    // Under a guest GPU-modified buffer hazard, the ORIGINAL immediate
    // early-return must skip texture and shader invalidation.
    r.buffer_cache.hazard=true;
    for (int i=0;i<64;++i) assert(r.OnCPUWrite(1,4));
    assert(r.buffer_cache.writes==320);
    assert(r.texture_cache.writes==256 &&
           r.pipeline_cache.invalidations==256);
    for (unsigned i=0;i<5;++i) {
        const auto count=cache_phase_totals[static_cast<unsigned>(groups[i])].samples.load();
        assert(count==(i<2?3u:2u));
    }
    detailed_gpu_profile.store(false);
    const auto quiet_clock_reads=Common::g_wall_clock.calls.load();
    for (int i=0;i<64;++i) assert(r.OnCPUWrite(1,4));
    assert(Common::g_wall_clock.calls.load()==quiet_clock_reads);
    assert(r.texture_cache.writes==256 &&
           r.pipeline_cache.invalidations==256);
    for (unsigned i=0;i<5;++i) {
        const auto count=cache_phase_totals[static_cast<unsigned>(groups[i])].samples.load();
        assert(count==(i<2?3u:2u));
    }
    // R437: empty BUFFER pages skip that mutex and OnCPUWrite.
    // This fixture's registered IMAGE page still needs the texture mutex;
    // the independent never-held-image case has its own extracted-host test.
    r.buffer_cache.hazard=false;
    const auto before_buffer=r.buffer_cache.writes;
    const auto before_texture=r.texture_cache.writes;
    const auto before_shader=r.pipeline_cache.invalidations;
    ::Eden::BufferPages::test_skip_empty_page.store(true);
    for (int i=0;i<32;++i) assert(!r.OnCPUWrite(1,4));
    assert(r.buffer_cache.writes==before_buffer);
    assert(r.texture_cache.writes==before_texture+32);
    assert(r.pipeline_cache.invalidations==before_shader+32);
    ::Eden::BufferPages::test_skip_empty_page.store(false);
    // Upstream #187 write-ahead subset: only registered buffer pages are
    // marked under the existing lock. Shader/texture invalidation remains.
    cpu_write_ahead.store(3);
    const unsigned a=r.buffer_cache.writes;
    const unsigned b=r.texture_cache.writes;
    const unsigned c=r.pipeline_cache.invalidations;
    assert(!r.OnCPUWrite(1,4));
    assert(r.buffer_cache.writes==a+4); // current page + 3 future pages
    assert(r.texture_cache.writes==b+1 && r.pipeline_cache.invalidations==c+1);
    // A GPU-owned next page must terminate pre-marking immediately, without
    // making its contents look guest-owned or skipping texture updates.
    r.buffer_cache.gpu_modified_page=8192;
    const unsigned d=r.buffer_cache.writes;
    assert(!r.OnCPUWrite(1,4));
    assert(r.buffer_cache.writes==d+3); // current, page 4096, stop at 8192
    r.buffer_cache.gpu_modified_page=0;
    cpu_write_ahead.store(0);
    puts("R370_GUEST_WRITE_PHASES_HOST_PASS");
}
""".replace('__GUEST_LOCK__',guest_lock).replace('__CACHE_PHASE__',cache_phase).replace('__BATCH_TIMER__',batch_timer).replace('__ON_CPU_WRITE__',method)
# Test source-extracted exact method without graphically modifying any image/view.
env=os.environ.copy()
if sys.platform=='darwin' and not env.get('SDKROOT'):
    sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
    if sdk.is_dir():env['SDKROOT']=str(sdk)
with tempfile.TemporaryDirectory(prefix='eden-r370-write-') as d:
    f=Path(d)/'phases.cpp';o=Path(d)/'phases';f.write_text(cpp)
    subprocess.run(['c++','-std=c++20','-O1','-pthread','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-I',str(root/'headless'),str(f),'-o',str(o)],
                   env=env,check=True,timeout=40)
    subprocess.run([str(o)],check=True,env=env,timeout=15)
print('PASS R370: original CPU-write ordering/early return, 1-in-64 sampling, quiet counters untouched')
