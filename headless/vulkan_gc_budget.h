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

} // namespace Eden::VulkanMemory
