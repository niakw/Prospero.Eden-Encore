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
// An unchecked unsigned subtraction makes recently touched textures appear
// older than everything when early GPU memory pressure triggers GC.
constexpr std::uint64_t OldestEvictionTick(std::uint64_t frame_tick,
                                            std::uint64_t min_age) noexcept {
    return frame_tick >= min_age ? frame_tick - min_age : 0;
}

} // namespace Eden::VulkanMemory
