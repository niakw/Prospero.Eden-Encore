// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Common PS5 CPU-code budget, not game-specific C/B/A settings.
// Dense JIT allocation currently commits this entire budget at launch.
// Sparse physical backing and multi-arena growth need separate qualification.
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
    std::size_t desired_active_jit_bytes = 0;
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

    const std::size_t native_floor = std::size_t{640} * kMiB;
    const std::size_t budget = ((largest_free_block - kHostReserve) / 2) / kLargePage * kLargePage;
    if (budget <= native_floor) return plan;
    const std::size_t growth = budget - native_floor;

    const auto clamp_arena = [](std::size_t bytes) constexpr -> std::uint32_t {
        if (bytes > kSingleArenaAddressingLimit)
            bytes = kSingleArenaAddressingLimit;
        return static_cast<std::uint32_t>(bytes / kLargePage * kLargePage);
    };
    // A64 distributes new code capacity among the three guest workers.
    // A32 gives core 0 more room because its legacy baseline is larger.
    plan.a64[0] = clamp_arena(std::size_t{kA64Baseline[0]} + growth * 4 / 10);
    plan.a64[1] = clamp_arena(std::size_t{kA64Baseline[1]} + growth * 3 / 10);
    plan.a64[2] = clamp_arena(std::size_t{kA64Baseline[2]} + growth * 3 / 10);
    plan.a32[0] = clamp_arena(std::size_t{kA32Baseline[0]} + growth * 5 / 10);
    plan.a32[1] = clamp_arena(std::size_t{kA32Baseline[1]} + growth / 4);
    plan.a32[2] = clamp_arena(std::size_t{kA32Baseline[2]} + growth / 4);
    plan.desired_active_jit_bytes = budget;
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
} // namespace Eden::Experimental
