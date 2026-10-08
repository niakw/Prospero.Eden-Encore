// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Common PS5 CPU-code budget, not game-specific C/B/A settings.
// Dense JIT allocation currently commits this entire budget at launch.
// Sparse physical backing and multi-arena growth need separate qualification.
#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace Eden::Experimental {
inline std::atomic<bool> sparse_jit_cache{false}; // developer-only / not PS5-qualified
inline std::atomic<bool> vulkan_frame_probe{false};

inline constexpr std::uint32_t kMiB = 1024u * 1024u;
inline constexpr std::size_t kHostReserve = std::size_t{3} * 1024 * kMiB;
inline constexpr std::size_t kLargePage = std::size_t{2} * kMiB;
// Single Dynarmic Xbyak code areas use x64 RIP-relative branch displacements.
// This is a *per-arena addressing limit*, NOT a global physical JIT budget.
// Increasing past it needs relocatable trampolines and multiple code arenas.
inline constexpr std::uint32_t kSingleArenaAddressingLimit = 1536u * kMiB;
inline constexpr std::array<std::uint32_t, 4> kA64Baseline{
    256u*kMiB, 192u*kMiB, 192u*kMiB, 16u*kMiB
};
inline constexpr std::array<std::uint32_t, 4> kA32Baseline{
    512u*kMiB, 64u*kMiB, 64u*kMiB, 16u*kMiB
};

struct JitMemoryPlan {
    std::array<std::uint32_t, 4> a64 = kA64Baseline;
    std::array<std::uint32_t, 4> a32 = kA32Baseline;
    std::size_t admission_budget_bytes = 0;
    bool memory_known = false;
    bool expanded = false;
};

// A physical admission plan, computed *once per game* for BOTH guest ISAs.
// Only the active ISA is instantiated, never both full sets simultaneously.
// Half the post-reserve contiguous free pool may be committed by today's
// dense JIT; the remaining half stays available for guest/GPU/I/O growth.
// No hard-coded "C" cache ceiling or title-ID list is involved.
// Memory rebalancing at runtime requires a separately proven sparse allocator.
inline constexpr JitMemoryPlan ChooseJitMemoryPlan(
    bool safe_launch, bool memory_query_ok, std::size_t largest_free_block) noexcept {
    JitMemoryPlan plan{};
    plan.memory_known = memory_query_ok;
    if (safe_launch || !memory_query_ok || largest_free_block <= kHostReserve)
        return plan;

    // Account for ALL four cores, including core 3's 16 MiB. The previous
    // 640 MiB floor covered only cores 0-2 while each actual baseline totals
    // 656 MiB, silently admitting 16 MiB beyond the advertised budget.
    constexpr std::size_t native_floor =
        std::size_t{kA64Baseline[0]} + kA64Baseline[1] +
        kA64Baseline[2] + kA64Baseline[3];
    static_assert(native_floor == std::size_t{kA32Baseline[0]} +
                                  kA32Baseline[1] + kA32Baseline[2] +
                                  kA32Baseline[3]);
    const std::size_t budget = ((largest_free_block - kHostReserve) / 2) / kLargePage * kLargePage;
    // AllocateMemoryPages gives every dense JIT cache its own 2 MiB direct-
    // memory header/alignment page. Four baseline arenas therefore commit
    // 656 + 8 MiB, not only the advertised 656 MiB code capacity. Account
    // for that *physical* overhead before admitting new code capacity.
    constexpr std::size_t dense_allocation_overhead = 4 * kLargePage;
    if (budget <= native_floor + dense_allocation_overhead) return plan;
    const std::size_t growth = budget - native_floor - dense_allocation_overhead;

    const auto clamp_arena = [](std::size_t bytes) constexpr -> std::uint32_t {
        if (bytes > kSingleArenaAddressingLimit)
            bytes = kSingleArenaAddressingLimit;
        return static_cast<std::uint32_t>(bytes / kLargePage * kLargePage);
    };
    // A64 distributes new code capacity among the three guest workers.
    // A32 gives core 0 more room because its legacy baseline is larger.
    plan.a64[0] = clamp_arena(std::size_t{kA64Baseline[0]} + (growth / 10) * 4);
    plan.a64[1] = clamp_arena(std::size_t{kA64Baseline[1]} + (growth / 10) * 3);
    plan.a64[2] = clamp_arena(std::size_t{kA64Baseline[2]} + (growth / 10) * 3);
    plan.a32[0] = clamp_arena(std::size_t{kA32Baseline[0]} + growth / 2);
    plan.a32[1] = clamp_arena(std::size_t{kA32Baseline[1]} + growth / 4);
    plan.a32[2] = clamp_arena(std::size_t{kA32Baseline[2]} + growth / 4);

    // A large contiguous free pool can saturate guest core 0's mandatory
    // x64 relative-branch arena limit before the other workers reach theirs.
    // Redistribute ONLY the capacity actually lost to clamping, not the
    // few rounding bytes (which could make a growing budget reduce another
    // core's arena at a 2 MiB boundary). Keep every plan monotonic, capped,
    // and bounded by the SAME admitted physical byte budget.
    const auto redistribute_saturated = [&](auto& arenas, const auto& floor,
                                            const std::array<std::size_t, 3>& desired) {
        std::size_t spill = 0;
        for (std::size_t i = 0; i < 3; ++i) {
            const std::size_t clamped = arenas[i];
            if (desired[i] > clamped + kLargePage)
                spill += (desired[i] - clamped) / kLargePage * kLargePage;
        }
        for (std::size_t i = 0; i < 3 && spill >= kLargePage; ++i) {
            const auto room = std::size_t{kSingleArenaAddressingLimit} - arenas[i];
            const auto add = (std::min(room, spill) / kLargePage) * kLargePage;
            arenas[i] += static_cast<std::uint32_t>(add);
            spill -= add;
        }
        (void)floor;
    };
    redistribute_saturated(plan.a64, kA64Baseline, {
        std::size_t{kA64Baseline[0]} + (growth / 10) * 4,
        std::size_t{kA64Baseline[1]} + (growth / 10) * 3,
        std::size_t{kA64Baseline[2]} + (growth / 10) * 3
    });
    redistribute_saturated(plan.a32, kA32Baseline, {
        std::size_t{kA32Baseline[0]} + growth / 2,
        std::size_t{kA32Baseline[1]} + growth / 4,
        std::size_t{kA32Baseline[2]} + growth / 4
    });
    plan.admission_budget_bytes = budget;
    plan.expanded = true;
    return plan;
}

// These stores happen after the previous title has shut down and before new
// Dynarmic JIT instances are constructed. Cache sizes remain immutable while
// guest worker threads execute (no per-frame atomic reads).
inline std::array<std::atomic<std::uint32_t>,4> a64_cache_bytes{
    256u*kMiB, 192u*kMiB, 192u*kMiB, 16u*kMiB
};
inline std::array<std::atomic<std::uint32_t>,4> a32_cache_bytes{
    512u*kMiB, 64u*kMiB, 64u*kMiB, 16u*kMiB
};
inline void ApplyJitMemoryPlan(const JitMemoryPlan& plan) noexcept {
    for (std::size_t core = 0; core < 4; ++core) {
        a64_cache_bytes[core].store(plan.a64[core], std::memory_order_relaxed);
        a32_cache_bytes[core].store(plan.a32[core], std::memory_order_relaxed);
    }
}
inline std::uint32_t A64CacheBytes(std::size_t core, std::uint32_t baseline) noexcept {
    return core < 4 ? a64_cache_bytes[core].load(std::memory_order_relaxed) : baseline;
}
inline std::uint32_t A32CacheBytes(std::size_t core, std::uint32_t baseline) noexcept {
    return core < 4 ? a32_cache_bytes[core].load(std::memory_order_relaxed) : baseline;
}

static_assert(ChooseJitMemoryPlan(true, true, 8ull * 1024 * kMiB).a64 == kA64Baseline);
static_assert(ChooseJitMemoryPlan(false, false, 8ull * 1024 * kMiB).a32 == kA32Baseline);
static_assert(ChooseJitMemoryPlan(false, true, 8ull * 1024 * kMiB).a64[0] > 320u*kMiB);
static_assert(ChooseJitMemoryPlan(false, true, 8ull * 1024 * kMiB).a32[1] > 64u*kMiB);
static_assert(ChooseJitMemoryPlan(false, true, 2ull * 1024 * kMiB).a64 == kA64Baseline);
static_assert(ChooseJitMemoryPlan(false, true, 8ull * 1024 * kMiB).a64[3] == 16u*kMiB);
static_assert(ChooseJitMemoryPlan(false, true, std::numeric_limits<std::size_t>::max()).a64[0] <= kSingleArenaAddressingLimit);
} // namespace Eden::Experimental
