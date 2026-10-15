#!/usr/bin/env python3
"""Host-only compiler/sanitizer qualification of deferred guest write queue.

Does NOT prove renderer cache/fence/texture correctness; native activation forbidden
until cache replay, GPU-dirty handling and title lifecycle are audited together.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = root / "headless/gpu_deferred_write_queue.h"
assert header.is_file()
source = r'''
#include "gpu_deferred_write_queue.h"
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <thread>
#include <vector>
using Eden::GpuDeferredWrite::Queue;
int main() {
    Queue q;
    assert(!q.Pending());
    assert(!q.Enqueue(4, 1, 1));
    assert(!q.Enqueue(0, 1, 0));
    assert(!q.Enqueue(0, UINT64_MAX, 2));
    assert(!q.Pending());

    assert(q.Enqueue(0, 100, 8));
    assert(q.Enqueue(0, 105, 10));
    assert(q.Enqueue(0, 4093, 8)); // crosses 4K boundary => independent
    assert(q.Enqueue(0, 4100, 10));
    std::vector<std::array<std::uint64_t,3>> written;
    const auto replay = [&](unsigned core, std::uint64_t addr, std::uint64_t size) {
        written.push_back({core,addr,size});
    };
    assert(q.Drain(replay) == 3);
    assert(!q.Pending());
    assert((written[0] == std::array<std::uint64_t,3>{0,100,15}));
    assert((written[1] == std::array<std::uint64_t,3>{0,4093,8}));
    assert((written[2] == std::array<std::uint64_t,3>{0,4100,10}));
    assert(q.Drain(replay) == 0);

    // Boundary-adjacent and gap-separated writes must not coalesce into
    // one GPU dirty area, even when inside the same guest 4-KiB page.
    Queue regions;
    assert(regions.Enqueue(0,2040,8));
    assert(regions.Enqueue(0,2048,8));
    assert(regions.Enqueue(0,3072,8));
    assert(regions.Enqueue(0,3090,8));
    assert(regions.Enqueue(0,3095,8)); // overlaps last: safe to merge
    std::vector<std::array<std::uint64_t,3>> precise;
    assert(regions.Drain([&](unsigned core,std::uint64_t addr,std::uint64_t sz) {
        precise.push_back({core,addr,sz});
    })==4);
    assert((precise[0]==std::array<std::uint64_t,3>{0,2040,8}));
    assert((precise[1]==std::array<std::uint64_t,3>{0,2048,8}));
    assert((precise[2]==std::array<std::uint64_t,3>{0,3072,8}));
    assert((precise[3]==std::array<std::uint64_t,3>{0,3090,13}));

    // GPU-owned writes must collect dirty ranges for the next fence and must
    // not overwrite GPU memory immediately. This is a caller contract.
    unsigned immediate = 0, held_for_fence = 0;
    assert(q.Enqueue(1, 4096, 8));
    assert(q.Enqueue(2, 8192, 8));
    q.Drain([&](unsigned, std::uint64_t addr, std::uint64_t) {
        if (addr == 4096) ++held_for_fence;
        else ++immediate;
    });
    assert(held_for_fence == 1 && immediate == 1);

    // Cross-core enqueue order is part of the memory coherency contract.
    // Previously a per-core sweep moved core 0 ahead of earlier core 2.
    Queue ordered;
    assert(ordered.Enqueue(2,12288,8));
    assert(ordered.Enqueue(0,4096,8));
    assert(ordered.Enqueue(3,16384,8));
    assert(ordered.Enqueue(1,8192,8));
    std::vector<unsigned> observed_order;
    assert(ordered.Drain([&](unsigned core, std::uint64_t, std::uint64_t) {
        observed_order.push_back(core);
    })==4);
    assert((observed_order == std::vector<unsigned>{2,0,3,1}));
    assert(!ordered.Pending());

    // Adjacent writes by the same core cannot merge when another core's
    // write sits between them in the global FIFO.
    Queue interleaved;
    assert(interleaved.Enqueue(0,64,8));
    assert(interleaved.Enqueue(1,4096,8));
    assert(interleaved.Enqueue(0,72,8));
    unsigned entries=0;
    assert(interleaved.Drain([&](unsigned,std::uint64_t,std::uint64_t) {
        ++entries;
    })==3);
    assert(entries==3);


    // Sustained producer pressure must never allocate an unbounded guest
    // dirty backlog. Full means FALL BACK to the original blocking path.
    Queue bounded;
    for (std::uint64_t i=0; i<Queue::MaxPendingEntries; ++i)
        assert(bounded.Enqueue(i%Queue::Cores, (i+1)*4096, 8));
    assert(bounded.Pending());
    assert(!bounded.Enqueue(0, (Queue::MaxPendingEntries+1)*4096, 8));
    assert(bounded.Pending()); // failure must not silently clear old entries
    std::uint64_t recovered=0;
    assert(bounded.Drain([&](unsigned, std::uint64_t, std::uint64_t) {
        ++recovered;
    })==Queue::MaxPendingEntries);
    assert(recovered==Queue::MaxPendingEntries && !bounded.Pending());
    assert(bounded.Enqueue(0, 4096, 8));
    assert(bounded.Drain([&](unsigned, std::uint64_t, std::uint64_t) {})==1);

    // Independent producer cores race with the GPU drain: every unique
    // page written must be replayed, including pushes during a drain.
    Queue concurrent;
    constexpr unsigned N = 320;
    std::array<std::atomic<unsigned>,4> seen{};
    std::array<std::atomic<bool>,4> done{};
    std::vector<std::thread> workers;
    for(unsigned c=0;c<4;++c) workers.emplace_back([&,c] {
        for(unsigned i=0;i<N;++i) {
            const std::uint64_t address = (std::uint64_t(c)*N+i+1)*4096;
            assert(concurrent.Enqueue(c,address,8));
            if ((i&7u)==0) std::this_thread::yield();
        }
        done[c].store(true,std::memory_order_release);
    });
    unsigned long long replay_count = 0;
    auto drain = [&](unsigned c, std::uint64_t addr, std::uint64_t size) {
        assert(size==8 && addr%4096==0);
        assert(addr/4096>std::uint64_t(c)*N &&
               addr/4096<=std::uint64_t(c+1)*N);
        seen[c].fetch_add(1,std::memory_order_relaxed);
        ++replay_count;
    };
    while(!done[0].load(std::memory_order_acquire) ||
          !done[1].load(std::memory_order_acquire) ||
          !done[2].load(std::memory_order_acquire) ||
          !done[3].load(std::memory_order_acquire) ||
          concurrent.Pending()) {
        concurrent.Drain(drain);
        std::this_thread::yield();
    }
    for(auto& t:workers)t.join();
    concurrent.Drain(drain);
    assert(replay_count==4*N);
    for(const auto& s:seen)assert(s.load()==N);
    concurrent.ResetAfterQuiescence();
    assert(!concurrent.Pending());
    assert(concurrent.Drain(drain)==0);
}
'''
with tempfile.TemporaryDirectory(prefix="encore-deferred-host-") as folder:
    cpp = Path(folder) / "test.cpp"
    exe = Path(folder) / "test"
    cpp.write_text(source)
    subprocess.run([
        "clang++", "-std=c++20", "-O1", "-g", "-pthread", "-Wall", "-Wextra",
        "-Werror", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
        "-I", str(header.parent), str(cpp), "-o", str(exe)
    ], check=True, timeout=45)
    subprocess.run([str(exe)], check=True, timeout=45)
print("GPU_DEFERRED_QUEUE_HOST_PASS concurrency=4 no_lost_ranges=1280 backpressure=8192 crosspage_split=1 quiescence=1")
