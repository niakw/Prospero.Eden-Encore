#!/usr/bin/env python3
"""R364: source-extracted buffer/texture CPU guest cache lock accounting."""
from pathlib import Path
import os, subprocess, sys, tempfile

root=Path(__file__).resolve().parents[1]
perf=(root/'headless/performance.h').read_text()
report=(root/'headless/performance.cpp').read_text()
active=(root/'vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp').read_text()
oracle=(root/'tools/prepare-vulkan-port.py').read_text()
start=perf.index('struct GuestCacheDomainTotals {')
end=perf.index('// R310:',start)
methods=perf[start:end]
assert 'GuestCacheLock(Mutex& mutex, bool texture_domain = false)' in methods
assert 'if (!detailed_gpu_profile.load(std::memory_order_relaxed))' in methods
assert methods.index('mutex.lock();\n        return;') < methods.index('mutex.try_lock()')
assert 'domain.contended.fetch_add(1' in methods
assert 'domain.blocked.fetch_add(1' in methods
assert 'domain.wait_ns.fetch_add' in methods
assert 'domain.waited_ge1ms.fetch_add' in methods
assert 'domain.waited_ge10ms.fetch_add' in methods
assert 'domain.max_wait_ns.compare_exchange_weak' in methods
assert 'EDEN_GUEST_CACHE_LOCK_TAIL frame=%u domain=%s' in report
assert 'wait_ge1ms=%llu wait_ge10ms=%llu max_wait_ns=%llu' in report
for source in (active,oracle):
    assert source.count('::Eden::Performance::GuestCacheLock(texture_cache.mutex, true);')==2
    assert source.count('::Eden::Performance::GuestCacheLock(buffer_cache.mutex, false);')==1
assert 'EDEN_GUEST_CACHE_DOMAIN frame=%u domain=%s' in report
assert 'window_contended=%llu window_blocked=%llu window_wait_ns=%llu' in report
assert report.index('if (detailed_gpu_profile.load') < report.index('EDEN_GUEST_CACHE_DOMAIN')

cpp=r"""
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <thread>
#include <cstdio>
#if !defined(__x86_64__)
#define __builtin_ia32_pause() ((void)0) // PS5 native path is x86_64
#endif
namespace Common {
struct Clock {
    std::atomic<unsigned long long> reads{};
    std::chrono::nanoseconds GetTimeNS() noexcept {
        // Publish a read only AFTER capturing the blocked-start timestamp.
        // The harness can then wait until a worker is definitely timing its lock wait.
        const auto started = std::chrono::steady_clock::now();
        const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
            started.time_since_epoch());
        reads.fetch_add(1, std::memory_order_release);
        return ns;
    }
};
inline Clock g_wall_clock;
}
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{false};
inline std::atomic<unsigned> cache_lock_spins{0};
inline std::atomic<unsigned long long> cache_lock_contended{0},cache_lock_blocked{0};
inline std::atomic<unsigned long long> cache_lock_wait_ns{0};
__METHODS__
}
int main() {
    using namespace Eden::Performance;
    std::mutex buffer_mutex,texture_mutex;
    // No instrumentation work in production/quiet path.
    for(int i=0;i<3000;i++) {
        GuestCacheLock(buffer_mutex,false);
        buffer_mutex.unlock();
        GuestCacheLock(texture_mutex,true);
        texture_mutex.unlock();
    }
    assert(cache_lock_contended.load()==0 && cache_lock_blocked.load()==0);
    assert(guest_cache_domain_totals[0].contended.load()==0);
    assert(guest_cache_domain_totals[1].contended.load()==0);
    assert(Common::g_wall_clock.reads.load()==0);
    detailed_gpu_profile.store(true);
    auto exercise=[](std::mutex& m,bool texture) {
        // A thread-start signal does NOT mean GuestCacheLock has reached its
        // timed blocking path. Slow CI runners could resume it only after
        // unlocking and spuriously report a wait shorter than 10 ms.
        const auto initial_reads=Common::g_wall_clock.reads.load(std::memory_order_acquire);
        m.lock();
        std::thread worker([&] {
            GuestCacheLock(m,texture);
            std::lock_guard unlock{m,std::adopt_lock};
        });
        const bool profiling = detailed_gpu_profile.load(std::memory_order_relaxed);
        bool timing_started = false;
        if (profiling) {
            // Only detailed mode reads the clock. Expecting a timed read in
            // quiet mode made the test fail despite correct blocking behavior.
            // Source checkout, sanitizer startup and heavy native-build
            // competition can starve a newly created test thread for
            // several seconds. Preserve the mandatory observed-clock
            // handshake; extend only its upper bound, never drop the
            // assertion or infer that a thread started timing.
            const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(15);
            while (Common::g_wall_clock.reads.load(std::memory_order_acquire)==initial_reads &&
                   std::chrono::steady_clock::now()<deadline) std::this_thread::yield();
            timing_started =
                Common::g_wall_clock.reads.load(std::memory_order_acquire)>initial_reads;
            if (timing_started) std::this_thread::sleep_for(std::chrono::milliseconds(15));
        } else {
            std::this_thread::sleep_for(std::chrono::milliseconds(15));
        }
        m.unlock();
        worker.join();
        if (profiling) assert(timing_started);
    };
    exercise(buffer_mutex,false);
    assert(guest_cache_domain_totals[0].contended.load()==1);
    assert(guest_cache_domain_totals[0].blocked.load()==1);
    assert(guest_cache_domain_totals[0].wait_ns.load()>0);
    assert(guest_cache_domain_totals[1].contended.load()==0);
    exercise(texture_mutex,true);
    assert(guest_cache_domain_totals[1].contended.load()==1);
    assert(guest_cache_domain_totals[1].blocked.load()==1);
    assert(guest_cache_domain_totals[1].wait_ns.load()>0);
    assert(cache_lock_contended.load()==2 && cache_lock_blocked.load()==2);
    for (const auto& domain : guest_cache_domain_totals) {
        assert(domain.waited_ge1ms.load() == 1);
        assert(domain.waited_ge10ms.load() == 1);
        assert(domain.max_wait_ns.load() >= 10'000'000);
    }
    assert(cache_lock_wait_ns.load()==
           guest_cache_domain_totals[0].wait_ns.load() +
           guest_cache_domain_totals[1].wait_ns.load());
    const auto reads=Common::g_wall_clock.reads.load();
    detailed_gpu_profile.store(false);
    exercise(buffer_mutex,false);
    assert(Common::g_wall_clock.reads.load()==reads);
    assert(cache_lock_contended.load()==2);
    assert(cache_lock_blocked.load()==2);
    // Quiet path does not increment expensive profiling histograms.
    assert(guest_cache_domain_totals[0].waited_ge1ms.load()==1);
    assert(guest_cache_domain_totals[1].waited_ge10ms.load()==1);
}
""".replace('__METHODS__',methods)
env=os.environ.copy()
if sys.platform=='darwin' and not env.get('SDKROOT'):
    sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
    if sdk.is_dir():env['SDKROOT']=str(sdk)
with tempfile.TemporaryDirectory(prefix='eden-r364-domains-') as d:
    src=Path(d)/'domains.cpp';binary=Path(d)/'domains';src.write_text(cpp)
    subprocess.run(['c++','-std=c++20','-O1','-pthread','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined',str(src),'-o',str(binary)],
                   check=True,env=env,timeout=40)
    subprocess.run([str(binary)],check=True,env=env,timeout=40)
print('PASS R364 actual GuestCacheLock C++: buffer/texture isolation, aggregate identity, no quiet clock/counters')
