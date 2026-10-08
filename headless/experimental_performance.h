// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Shared PS5 JIT policy, independent of title ID. Development overrides are
// opt-in and never required for ordinary games.
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace Eden::Experimental {
inline std::atomic<unsigned> jit_cache_tier{0};
// Disabled until native console validation; preserve the qualified dense path.
inline std::atomic<bool> sparse_jit_cache{false};
inline std::atomic<bool> vulkan_frame_probe{false};

inline constexpr std::size_t kMiB = std::size_t{1024} * 1024;
inline constexpr std::size_t kBalancedA64Total = 704 * kMiB;
inline constexpr std::size_t kExpandedA64Total = 832 * kMiB;

// At present AllocateMemoryPages commits the whole JIT at creation. These
// headroom floors protect guest/graphics allocations *after* a prospective
// JIT allocation. They are admission safeguards, not a JIT capacity ceiling.
// Once demand-driven backing has been hardware-qualified they can be replaced
// with an actual physical-memory pressure controller.
inline constexpr std::size_t kExpandedHeadroom = 3 * 1024 * kMiB;
inline constexpr std::size_t kBalancedHeadroom = 2 * 1024 * kMiB;

// Once per game start; no hot-path querying or title-based exceptions.
// Unknown firmware memory availability => conservative qualified baseline.
// A32 uses its own independent configuration and is not treated as A64.
inline constexpr unsigned ChooseA64CacheTier(bool safe_launch,
                                               bool memory_query_succeeded,
                                               std::size_t largest_free_block) noexcept {
    if (safe_launch || !memory_query_succeeded) return 0;
    if (largest_free_block >= kExpandedA64Total + kExpandedHeadroom) return 2;
    if (largest_free_block >= kBalancedA64Total + kBalancedHeadroom) return 1;
    return 0;
}

// A64 capacity is still fixed for the JIT's lifetime until the safe
// multi-segment/demand-driven allocator is implemented and PS5-qualified.
inline std::uint32_t A64CacheBytes(std::size_t core, std::uint32_t baseline) noexcept {
    if (core >= 3) return baseline;
    const unsigned tier = jit_cache_tier.load(std::memory_order_relaxed);
    constexpr std::uint32_t mib = 1024u * 1024u;
    if (tier == 1 && core != 0) return 224u * mib;
    if (tier == 2) return (core == 0 ? 320u : 256u) * mib;
    return baseline;
}

static_assert(ChooseA64CacheTier(true, true, 8 * 1024 * kMiB) == 0);
static_assert(ChooseA64CacheTier(false, false, 8 * 1024 * kMiB) == 0);
static_assert(ChooseA64CacheTier(false, true, 8 * 1024 * kMiB) == 2);
static_assert(ChooseA64CacheTier(false, true, 3 * 1024 * kMiB) == 1);
static_assert(ChooseA64CacheTier(false, true, 1024 * kMiB) == 0);
} // namespace Eden::Experimental
