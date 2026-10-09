// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "settings_store.h"

#include <algorithm>

namespace Eden::EncorePerformance {

// The seven performance controls exposed by current ProsperoEden master. Encore keeps them behind
// its user-facing Minimum / Recommended / High / Ultra profiles so a normal player does not have
// to understand emulator internals.
struct Policy {
    bool compile_ahead;
    bool async_shaders;
    bool fast_gpu;
    bool unsafe_cpu;
    bool unsafe_dma;
    bool reactive_flushing;
    bool skip_invalidation;
};

// Generic PS5 policy. It must work for titles that have no database entry; title-specific data may
// refine video settings but is never required for these controls.
//
// Compile-ahead is deliberately false in shipping Encore today. The shipping build uses ordinary
// per-core Dynarmic and does not compile the experimental shared-JIT path that the saved-block
// precompiler needs. Re-enabling it requires a generic pressure-aware implementation, not a
// hand-maintained game whitelist.
//
// The three unsafe/correctness switches stay conservative in all normal tiers. Minimum gains speed
// through lower render cost + asynchronous shaders + low GPU accuracy, rather than silently risking
// CPU/DMA correctness or stale GPU memory. All Vulkan tiers now enable asynchronous shader
// compilation: a first-use effect may appear a moment late instead of blocking a frame, even
// in High/Ultra. The image-quality tier still controls resolution, AA and accuracy; shader
// compilation completion (not shader omission) remains the target.
inline constexpr Policy kPolicies[EncoreOverrides::kAuthoredProfileCount] = {
    // compile  async  fastGPU unsafeCPU unsafeDMA reactive skipInv
    {false,    true,  true,   false,    false,    true,    false}, // Minimum
    {false,    true,  false,  false,    false,    true,    false}, // Recommended
    {false,    true,  false,  false,    false,    true,    false}, // High
    {false,    true,  false,  false,    false,    true,    false}, // Ultra
};

inline constexpr Policy ForTier(int tier) {
    return kPolicies[static_cast<std::size_t>(
        std::clamp(tier, 0, EncoreOverrides::kAuthoredProfileCount - 1))];
}

} // namespace Eden::EncorePerformance
