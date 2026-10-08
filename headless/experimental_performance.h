// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Per-title PS5 experiments, OFF by default. Read options before guest JIT creation.
#include <atomic>
#include <cstddef>
#include <cstdint>
namespace Eden::Experimental {
inline std::atomic<unsigned> jit_cache_tier{0};
inline std::atomic<bool> vulkan_frame_probe{false};
// A64 guest code cache allocation is fixed for the lifetime of its JIT.
inline std::uint32_t A64CacheBytes(std::size_t core, std::uint32_t baseline) noexcept {
    if (core >= 3) return baseline;
    const unsigned tier = jit_cache_tier.load(std::memory_order_relaxed);
    constexpr std::uint32_t mib = 1024u * 1024u;
    if (tier == 1 && core != 0) return 224u * mib;
    if (tier == 2) return (core == 0 ? 320u : 256u) * mib;
    return baseline;
}
} // namespace Eden::Experimental
