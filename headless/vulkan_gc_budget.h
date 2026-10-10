// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstdint>

namespace Eden::VulkanMemory {

// Predict GPU memory pressure before dirty-texture GC submissions complete.
// Real driver usage and per-image bookkeeping are not interchangeable:
// already released/aliased images can make an anticipated reclaim larger than
// the last sampled usage. Never wrap a u64 into a huge positive value; that
// would keep submitting unnecessary texture readbacks and runtime.Finish waits.
//
// This is a nonallocating arithmetic safeguard, NOT an increase in VRAM budget.
constexpr std::uint64_t AfterProjectedEviction(std::uint64_t used,
                                                std::uint64_t reclaimed) noexcept {
    return reclaimed >= used ? 0 : used - reclaimed;
}

// Frame counters start at zero and eviction ages range from 10 to 50.
// Saturate the unsigned subtraction, and guard the caller's inclusive LRU
// scan until frame_tick >= min_age to preserve the startup grace period.
constexpr std::uint64_t OldestEvictionTick(std::uint64_t frame_tick,
                                            std::uint64_t min_age) noexcept {
    return frame_tick >= min_age ? frame_tick - min_age : 0;
}

} // namespace Eden::VulkanMemory
