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
#include <optional>
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

    // Sequence watermarks acknowledge merged writes, not just FIFO entries.
    Queue tracked;
    const auto a = tracked.EnqueueTracked(2, 100, 8);
    const auto b = tracked.EnqueueTracked(2, 104, 8);
    assert(a && b && a->sequence == 1 && b->sequence == 2);
    assert(a->generation == b->generation);
    assert(tracked.AcceptedSequence() == 2);
    assert(tracked.CompletedSequence() == 0 && tracked.Pending());
    std::optional<Queue::Ticket> late_ticket;
    std::atomic<bool> wait_done{false};
    std::atomic<bool> wait_ok{false};
    std::thread waiting_reader([&] {
        wait_ok.store(tracked.WaitUntil(*b), std::memory_order_release);
        wait_done.store(true, std::memory_order_release);
    });
    std::atomic<unsigned> batch_count{0};
    assert(tracked.DrainThrough(b->sequence, [&](unsigned core, std::uint64_t addr, std::uint64_t sz) {
        assert(core == 2 && addr == 100 && sz == 12);
        assert(tracked.Pending()); // In-flight replay is not a completed ticket.
        batch_count.fetch_add(1);
        // A new producer during replay must not extend this drain indefinitely.
        late_ticket = tracked.EnqueueTracked(0, 4096, 8);
        assert(late_ticket && late_ticket->sequence == 3);
    }) == 1);
    waiting_reader.join();
    assert(wait_done.load() && wait_ok.load());
    assert(batch_count.load() == 1);
    assert(tracked.CompletedSequence() == 2);
    assert(tracked.AcceptedSequence() == 3 && tracked.Pending());
    assert(tracked.Drain([&](unsigned, std::uint64_t, std::uint64_t) {}) == 1);
    assert(tracked.CompletedSequence() == 3 && !tracked.Pending());
    assert(tracked.WaitUntil(*late_ticket));
    assert(!tracked.WaitUntil(Queue::Ticket{4, late_ticket->generation}));

    // A blocked read must escape on title shutdown rather than wait forever.
    Queue stopping;
    const auto ticket = stopping.EnqueueTracked(1, 8192, 8);
    assert(ticket && ticket->sequence == 1);
    std::atomic<bool> cancelled{false};
    std::thread blocked([&] { cancelled.store(!stopping.WaitUntil(*ticket)); });
    stopping.Close();
    blocked.join();
    assert(cancelled.load());
    assert(!stopping.EnqueueTracked(1, 12288, 8).has_value());
    stopping.ResetAfterQuiescence();
    assert(!stopping.Pending() && stopping.Enqueue(1, 12288, 8));
    assert(stopping.Drain([](unsigned, std::uint64_t, std::uint64_t) {}) == 1);

    // Two GPU-owner attempts are serialized. The second must not replay a
    // newer write before the first callback completes, nor skip its own work.
    Queue single_owner;
    assert(single_owner.Enqueue(0, 16384, 8));
    std::atomic<bool> replay_entered{false};
    std::atomic<bool> release_replay{false};
    std::atomic<bool> first_callback_done{false};
    std::atomic<bool> second_started{false};
    std::atomic<bool> second_callback_done{false};
    std::thread first_owner([&] {
        assert(single_owner.Drain([&](unsigned, std::uint64_t, std::uint64_t) {
            replay_entered.store(true, std::memory_order_release);
            while (!release_replay.load(std::memory_order_acquire)) std::this_thread::yield();
            first_callback_done.store(true, std::memory_order_release);
        }) == 1);
    });
    while (!replay_entered.load(std::memory_order_acquire)) std::this_thread::yield();
    assert(single_owner.Enqueue(1, 20480, 8));
    std::thread second_owner([&] {
        second_started.store(true, std::memory_order_release);
        assert(single_owner.Drain([&](unsigned core, std::uint64_t, std::uint64_t) {
            assert(core == 1 && first_callback_done.load(std::memory_order_acquire));
            second_callback_done.store(true, std::memory_order_release);
        }) == 1);
    });
    while (!second_started.load(std::memory_order_acquire)) std::this_thread::yield();
    assert(single_owner.CompletedSequence() == 0);
    release_replay.store(true, std::memory_order_release);
    first_owner.join();
    second_owner.join();
    assert(first_callback_done.load() && second_callback_done.load());
    assert(single_owner.CompletedSequence() == 2 && !single_owner.Pending());

    // Regression: the replay callback continuously appends more writes.
    // DrainThrough must take ONE fixed queue snapshot, not keep draining
    // new work until producers finally stop. The old implementation did.
    Queue burst;
    const auto initial = burst.EnqueueTracked(0, 32768, 8);
    assert(initial && initial->sequence == 1);
    assert(burst.DrainThrough(initial->sequence, [&](unsigned core, std::uint64_t, std::uint64_t) {
        assert(core == 0);
        for (unsigned i = 0; i < 400; ++i) {
            const auto added = burst.EnqueueTracked(1, (std::uint64_t(i) + 20) * 4096, 8);
            assert(added && added->sequence == i + 2);
        }
    }) == 1);
    assert(burst.CompletedSequence() == 1);
    assert(burst.AcceptedSequence() == 401 && burst.Pending());
    unsigned later_count = 0;
    assert(burst.Drain([&](unsigned core, std::uint64_t, std::uint64_t) {
        assert(core == 1);
        ++later_count;
    }) == 400);
    assert(later_count == 400 && !burst.Pending());
    assert(burst.CompletedSequence() == burst.AcceptedSequence());

    // A requested read ticket is a minimum completion target, not an
    // exact cutoff. The captured snapshot can acknowledge newer writes
    // accepted before the GPU consumer takes its snapshot.
    Queue snapshot;
    const auto early = snapshot.EnqueueTracked(0, 4096, 8);
    const auto later = snapshot.EnqueueTracked(1, 8192, 8);
    assert(early && later && early->sequence == 1 && later->sequence == 2);
    assert(snapshot.DrainThrough(early->sequence, [](unsigned, std::uint64_t, std::uint64_t) {}) == 2);
    assert(snapshot.CompletedSequence() == later->sequence);
    assert(!snapshot.Pending());
    assert(snapshot.DrainThrough(early->sequence, [](unsigned, std::uint64_t, std::uint64_t) {
        assert(false);
    }) == 0);

    // Two-phase publication: an out-of-order published write must not
    // leapfrog a prior reservation from another guest core.
    Queue two_phase;
    const auto first = two_phase.Reserve(1, 4096, 8);
    const auto second = two_phase.Reserve(3, 8192, 8);
    assert(first && second && first->sequence == 1 && second->sequence == 2);
    assert(first->generation == second->generation);
    assert(two_phase.Publish(*second));
    assert(!two_phase.Publish(*second));
    assert(two_phase.Pending() && two_phase.CompletedSequence() == 0);
    unsigned premature = 0;
    assert(two_phase.Drain([&](unsigned,std::uint64_t,std::uint64_t){++premature;}) == 0);
    assert(premature == 0);
    assert(two_phase.Publish(*first));
    std::vector<unsigned> published_order;
    assert(two_phase.Drain([&](unsigned core,std::uint64_t,std::uint64_t) {
        published_order.push_back(core);
    }) == 2);
    assert((published_order == std::vector<unsigned>{1,3}));
    assert(two_phase.WaitUntil(*first) && two_phase.WaitUntil(*second));
    assert(!two_phase.Publish(*first) && !two_phase.Pending());

    // A finished ordinary (non-atomic) CPU store is visible to replay
    // because Publish releases the queue mutex and the consumer acquires it.
    // No callback may execute before publication of this exact ticket.
    Queue publication;
    int guest_payload = 0;
    const auto delayed = publication.Reserve(0, 12288, sizeof(guest_payload));
    assert(delayed);
    assert(publication.Drain([](unsigned,std::uint64_t,std::uint64_t){assert(false);}) == 0);
    std::atomic<bool> started{false};
    std::thread producer([&] {
        started.store(true, std::memory_order_release);
        guest_payload = 0x12345;
        assert(publication.Publish(*delayed));
    });
    while (!started.load(std::memory_order_acquire)) std::this_thread::yield();
    unsigned observed = 0;
    while (publication.CompletedSequence() < delayed->sequence) {
        publication.Drain([&](unsigned core,std::uint64_t addr,std::uint64_t sz) {
            assert(core == 0 && addr == 12288 && sz == sizeof(guest_payload));
            assert(guest_payload == 0x12345);
            ++observed;
        });
        std::this_thread::yield();
    }
    producer.join();
    assert(observed == 1 && publication.WaitUntil(*delayed));

    // Published entries before an uncommitted reservation can drain.
    // Published entries after that reservation must wait.
    Queue partial;
    assert(partial.Enqueue(0, 4096, 8));
    const auto hole = partial.Reserve(1, 8192, 8);
    assert(hole);
    assert(partial.Enqueue(2, 16384, 8));
    std::vector<unsigned> prefix;
    assert(partial.Drain([&](unsigned c,std::uint64_t,std::uint64_t) {
        prefix.push_back(c);
    }) == 1);
    assert((prefix == std::vector<unsigned>{0}));
    assert(partial.CompletedSequence() == 1 && partial.Pending());
    assert(partial.Drain([](unsigned,std::uint64_t,std::uint64_t){assert(false);}) == 0);
    assert(partial.Publish(*hole));
    assert(partial.Drain([&](unsigned c,std::uint64_t,std::uint64_t) {
        prefix.push_back(c);
    }) == 2);
    assert((prefix == std::vector<unsigned>{0,1,2}));
    assert(!partial.Pending());

    // Stale sessions, invalid tickets, and teardown cancellation.
    Queue lifetime;
    const auto old = lifetime.Reserve(2, 24576, 8);
    assert(old);
    assert(!lifetime.Publish(Queue::Ticket{0, old->generation}));
    assert(!lifetime.Publish(Queue::Ticket{old->sequence + 1, old->generation}));
    lifetime.Close();
    assert(!lifetime.Publish(*old));
    assert(!lifetime.WaitUntil(*old));
    lifetime.ResetAfterQuiescence();
    const auto fresh = lifetime.Reserve(2, 24576, 8);
    assert(fresh && fresh->sequence == old->sequence &&
           fresh->generation != old->generation);
    assert(!lifetime.Publish(*old));
    assert(!lifetime.WaitUntil(*old));
    assert(lifetime.Publish(*fresh));
    assert(lifetime.Drain([](unsigned,std::uint64_t,std::uint64_t){}) == 1);
    assert(lifetime.WaitUntil(*fresh));

    // Multiple CPU producers publish DIFFERENT RAM payloads out of order.
    // Replay must stay FIFO and must never observe a pre-publication value.
    // Entries are spaced apart so ordinary coalescing cannot hide a hole.
    Queue concurrent_publication;
    constexpr unsigned PublishedWrites = 128;
    std::array<Queue::Ticket, PublishedWrites> reserved_tickets{};
    std::array<unsigned, PublishedWrites> guest_values{};
    std::array<std::atomic<bool>, 4> finished_publishers{};
    for (unsigned i = 0; i < PublishedWrites; ++i) {
        auto ticket = concurrent_publication.Reserve(i % 4,
                                                     (std::uint64_t(i) + 1) * 4096, 8);
        assert(ticket && ticket->sequence == i + 1);
        reserved_tickets[i] = *ticket;
    }
    std::vector<std::thread> publishers;
    for (unsigned core = 0; core < 4; ++core) {
        publishers.emplace_back([&, core] {
            for (int index = int(PublishedWrites) - 4 + int(core);
                 index >= 0; index -= 4) {
                guest_values[unsigned(index)] = unsigned(index) + 1;
                assert(concurrent_publication.Publish(reserved_tickets[unsigned(index)]));
                if ((index & 15) == 0) std::this_thread::yield();
            }
            finished_publishers[core].store(true, std::memory_order_release);
        });
    }
    unsigned next_replay_index = 0;
    const auto verify_publication = [&](unsigned core, std::uint64_t addr,
                                        std::uint64_t size) {
        const auto index = unsigned(addr / 4096 - 1);
        assert(size == 8 && index == next_replay_index);
        assert(core == index % 4);
        // Plain CPU backing-RAM values, synchronized only by Publish and the
        // replay snapshot's mutex acquisition.
        assert(guest_values[index] == index + 1);
        ++next_replay_index;
    };
    while (true) {
        concurrent_publication.Drain(verify_publication);
        bool producers_done = true;
        for (const auto& done : finished_publishers)
            producers_done &= done.load(std::memory_order_acquire);
        if (producers_done && !concurrent_publication.Pending()) break;
        std::this_thread::yield();
    }
    for (auto& publisher : publishers) publisher.join();
    assert(next_replay_index == PublishedWrites);
    assert(concurrent_publication.CompletedSequence() == PublishedWrites);
    assert(!concurrent_publication.Pending());

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
print("GPU_DEFERRED_QUEUE_HOST_PASS concurrency=4 no_lost_ranges=1280 crosspage_split=1 quiescence=1")
