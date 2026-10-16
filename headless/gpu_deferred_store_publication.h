// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Source-only post-store publication primitive. This is NOT wired into the
// shipping core or the disabled native bridge.
#include "gpu_deferred_write_queue.h"
#include <cstdint>
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
// Conditional stores read guest RAM before attempting modification. A caller
// MUST synchronously complete all older deferred cache invalidations and the
// GPU-to-CPU download *before* it provides a ReadBarrierResult::Complete.
// A mere queued/asynchronous scheduling acceptance is NOT completion.
// The read fence must also be ordered with competing producers by the caller.
// This source-only composition intentionally does not enable the native path.
enum class ReadBarrierResult { Complete, Failed };

template<class SyncRead, class Attempt, class RequestGpu>
std::optional<StoreOutcome> CommitConditionalAfterRead(
    Queue& queue, unsigned core, std::uint64_t address, std::uint64_t size,
    SyncRead&& synchronize_read, Attempt&& attempt,
    RequestGpu&& request_gpu) {
    static_assert(std::is_same_v<std::invoke_result_t<SyncRead&>, ReadBarrierResult>,
                  "Conditional read barrier must explicitly report completion");
    static_assert(std::is_nothrow_invocable_r_v<StoreOutcome, Attempt&>,
                  "Atomic store attempt must be noexcept and report modification");
    // A failed/incomplete read must not reserve an invalidation, touch RAM, or
    // fall back to a direct unsynchronized CAS. Caller must abort the title.
    if (std::forward<SyncRead>(synchronize_read)() != ReadBarrierResult::Complete)
        return std::nullopt;
    return CommitPostStore(queue, core, address, size,
                           std::forward<Attempt>(attempt),
                           std::forward<RequestGpu>(request_gpu));
}
} // namespace Eden::GpuDeferredWrite
