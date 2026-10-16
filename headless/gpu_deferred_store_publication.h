// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Source-only post-store publication primitive. This is NOT wired into the
// shipping core or the disabled native bridge.
#include "gpu_deferred_write_queue.h"
#include <cstdint>
#include <mutex>
#include <optional>
#include <type_traits>
#include <utility>

namespace Eden::GpuDeferredWrite {
enum class StoreOutcome { Modified, Unchanged };

// Reserve BEFORE an actual host RAM store, commit AFTER the store, or cancel
// a conditional store that made no modification. The owner callback can be
// synchronous or asynchronous; a bool false scheduler return poisons Queue.
//
// Crucial caller contracts that this helper cannot itself prove:
//  - Caller has completed any GPU->CPU read/download synchronization first.
//  - Store is noexcept and happens exactly once; no cache mutex is held.
//  - Guest producer lifetime extends through resolution (join before Close).
//  - A nullopt after a store means fatal title failure, never synchronous
//    fallback or a second store.
//  - Normal store, cache flush (no new data), CAS/LL-SC and direct JIT paths
//    must be classified independently in the source-derived native bridge.
// This header does not enable kNativePostStorePublicationReady.
template<class Store, class RequestGpu>
std::optional<StoreOutcome> CommitPostStore(
    Queue& queue, unsigned core, std::uint64_t address, std::uint64_t size,
    Store&& store, RequestGpu&& request_gpu) {
    static_assert(std::is_nothrow_invocable_r_v<StoreOutcome, Store&>,
                  "Backing RAM operation must be noexcept and return StoreOutcome");
    const auto ticket = queue.ReserveOrdered(core, address, size, request_gpu);
    if (!ticket) return std::nullopt;  // Must not execute the operation.
    const auto outcome = std::forward<Store>(store)();
    const bool accepted = outcome == StoreOutcome::Modified
        ? queue.PublishAndWake(*ticket, request_gpu)
        : queue.CancelAndWake(*ticket, request_gpu);
    if (!accepted) return std::nullopt;  // Irrecoverable: caller must stop title.
    return outcome;
}
// Reserve the guest CAS FIFO position before reading RAM. The read callback
// must fence ONLY its predecessors, never the unpublished CAS itself. Complete
// the real GPU-to-CPU transfer before reporting ReadBarrierResult::Complete.
// Guest CPU/JIT/fastmem producers must share the GuestStoreOrderGate below.
// This source-only composition intentionally does not enable the native path.
enum class ReadBarrierResult { Complete, Failed };

template<class SyncRead, class Attempt, class RequestGpu>
std::optional<StoreOutcome> CommitConditionalAfterRead(
    Queue& queue, unsigned core, std::uint64_t address, std::uint64_t size,
    SyncRead&& synchronize_read, Attempt&& attempt,
    RequestGpu&& request_gpu) {
    static_assert(std::is_same_v<std::invoke_result_t<SyncRead&, Queue::Ticket>,
                                 ReadBarrierResult>,
                  "Read barrier must report completed prior FIFO work");
    static_assert(std::is_nothrow_invocable_r_v<StoreOutcome, Attempt&>,
                  "Atomic store attempt must be noexcept and report modification");
    // Saturation may drain older invalidations. Reserve BEFORE synchronizing
    // the CPU read so no such drain can occur after the read fence.
    const auto ticket = queue.ReserveOrdered(core, address, size, request_gpu);
    if (!ticket) return std::nullopt;
    // Never wait for our own unpublished ticket. The read callback must
    // complete this predecessor watermark plus the GPU-to-CPU device fence.
    const Queue::Ticket predecessors{ticket->sequence - 1, ticket->generation};
    ReadBarrierResult read_status = ReadBarrierResult::Failed;
    try {
        read_status = std::forward<SyncRead>(synchronize_read)(predecessors);
    } catch (...) {
        (void)queue.CancelAndWake(*ticket, request_gpu);
        throw;
    }
    if (read_status != ReadBarrierResult::Complete) {
        (void)queue.CancelAndWake(*ticket, request_gpu);
        return std::nullopt; // Caller must abort, not attempt stale-memory CAS.
    }
    const auto outcome = std::forward<Attempt>(attempt)();
    const bool accepted = outcome == StoreOutcome::Modified
        ? queue.PublishAndWake(*ticket, request_gpu)
        : queue.CancelAndWake(*ticket, request_gpu);
    if (!accepted) return std::nullopt;
    return outcome;
}

// This per-title gate serializes PARTICIPATING producer transactions across
// read fences, RAM stores, FIFO resolution and scheduling callbacks. It is
// not acquired by the GPU consumer. No callback may recursively take it.
// All native CPU/JIT/fastmem paths must participate before activation.
class GuestStoreOrderGate final {
public:
    explicit GuestStoreOrderGate(Queue& queue) noexcept : queue_{queue} {}
    GuestStoreOrderGate(const GuestStoreOrderGate&) = delete;
    GuestStoreOrderGate& operator=(const GuestStoreOrderGate&) = delete;

    template<class Store, class RequestGpu>
    std::optional<StoreOutcome> Write(unsigned core, std::uint64_t address,
                                      std::uint64_t size, Store&& store,
                                      RequestGpu&& request_gpu) {
        std::lock_guard lock(mutex_);
        return CommitPostStore(queue_, core, address, size,
                               std::forward<Store>(store),
                               std::forward<RequestGpu>(request_gpu));
    }
    template<class SyncRead, class Attempt, class RequestGpu>
    std::optional<StoreOutcome> Conditional(
        unsigned core, std::uint64_t address, std::uint64_t size,
        SyncRead&& synchronize_read, Attempt&& attempt, RequestGpu&& request_gpu) {
        std::lock_guard lock(mutex_);
        return CommitConditionalAfterRead(queue_, core, address, size,
                                          std::forward<SyncRead>(synchronize_read),
                                          std::forward<Attempt>(attempt),
                                          std::forward<RequestGpu>(request_gpu));
    }
private:
    Queue& queue_;
    std::mutex mutex_;
};
} // namespace Eden::GpuDeferredWrite
