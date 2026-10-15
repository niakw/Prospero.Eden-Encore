// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// GPU-owned dirty guest ranges must be split on transform boundaries.
#include "gpu_deferred_write_queue.h"
#include <algorithm>
#include <cstdint>
#include <utility>

namespace Eden::GpuDeferredWrite {
// The origin belongs to the guest's HandleRasterizerWrite invocation, not
// whichever host worker later drains or dispatches a GPU command. The GPU
// thread and all unrelated threads have NoGuestCore by default.
inline constexpr unsigned NoGuestCore = Queue::Cores;
inline thread_local unsigned guest_write_origin_core = NoGuestCore;
struct ScopedGuestWriteOrigin final {
    const unsigned previous;
    explicit ScopedGuestWriteOrigin(unsigned core) noexcept
        : previous{guest_write_origin_core} {
        guest_write_origin_core = core < Queue::Cores ? core : NoGuestCore;
    }
    ~ScopedGuestWriteOrigin() { guest_write_origin_core = previous; }
    ScopedGuestWriteOrigin(const ScopedGuestWriteOrigin&) = delete;
    ScopedGuestWriteOrigin& operator=(const ScopedGuestWriteOrigin&) = delete;
};

// GPU-owner replay must never defer itself. No process-global session queue.
inline thread_local bool replaying_guest_write = false;
struct ScopedReplay final {
    const bool previous = replaying_guest_write;
    ScopedReplay() noexcept { replaying_guest_write = true; }
    ~ScopedReplay() { replaying_guest_write = previous; }
    ScopedReplay(const ScopedReplay&) = delete;
    ScopedReplay& operator=(const ScopedReplay&) = delete;
};
inline constexpr std::uint64_t kDirtyRegionBytes = 2048;
inline constexpr std::uint64_t kDirtyBlockBytes = 64;
struct ReplayTotals {
    std::uint64_t queued_ranges{}, deferred_gpu_owned{}, dirty_segments{};
};

// GPU owner only, outside buffer/texture cache locks and before dependent work.
// on_cpu_write must call the ORIGINAL rasterizer path with DEFER disabled;
// return true only when the cache still owns the old GPU-written contents.
// collect_dirty represents at most one 2048-byte GPUDirty transform per call.
template <class OnCpuWrite, class CollectDirty>
ReplayTotals ReplayQueued(Queue& queue, OnCpuWrite&& on_cpu_write,
                          CollectDirty&& collect_dirty) {
    ReplayTotals totals{};
    queue.Drain([&](unsigned core, std::uint64_t address, std::uint64_t size) {
        ++totals.queued_ranges;
        if (!on_cpu_write(address, size)) return;
        ++totals.deferred_gpu_owned;
        for (std::uint64_t cursor = address, left = size; left != 0;) {
            const auto room = kDirtyRegionBytes - (cursor % kDirtyRegionBytes);
            const auto chunk = std::min(left, room);
            collect_dirty(core, cursor, chunk);
            cursor += chunk;
            left -= chunk;
            ++totals.dirty_segments;
        }
    });
    return totals;
}
} // namespace Eden::GpuDeferredWrite
