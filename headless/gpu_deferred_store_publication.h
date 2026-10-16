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
} // namespace Eden::GpuDeferredWrite
