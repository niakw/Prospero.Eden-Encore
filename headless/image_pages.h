// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// R433: monotonic page occupancy for PS5 Vulkan texture-cache lock elision.
// A positive bit only means an image has EVER occupied this CPU address; no
// unregister clears it. This is conservative, including between game launches.
#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
namespace Eden::ImagePages {
inline constexpr unsigned kPageBits = 12; // Core::DEVICE_PAGEBITS
inline constexpr std::uint64_t kSpace = std::uint64_t{1} << 34;
inline constexpr std::size_t kWords = static_cast<std::size_t>(kSpace >> kPageBits) / 64;
inline std::array<std::atomic<std::uint64_t>, kWords> held{};
constexpr std::uint64_t Bits(unsigned first, unsigned last) noexcept {
    return (~std::uint64_t{0} >> (63 - last)) & (~std::uint64_t{0} << first);
}
// Publish the page BEFORE it is inserted into the registered image slot map.
inline void Mark(std::uint64_t address, std::uint64_t size) noexcept {
    if (size == 0 || address >= kSpace) return;
    const auto first = address >> kPageBits;
    const auto last = ((std::min)(size, kSpace - address) + address - 1) >> kPageBits;
    for (auto word = first / 64; word <= last / 64; ++word) {
        const auto bits = Bits(word == first / 64 ? first % 64 : 0,
                               word == last / 64 ? last % 64 : 63);
        if ((held[word].load(std::memory_order_relaxed) & bits) != bits)
            held[word].fetch_or(bits, std::memory_order_release);
    }
}
// Return true ONLY when it is safe to skip the cache lock. Large and invalid
// queries use the unchanged blocking path; cap bitmap scanning on guest calls.
inline bool NeverHeld(std::uint64_t address, std::uint64_t size) noexcept {
    if (size == 0) size = 1;
    if (address >= kSpace || size > kSpace - address) return false;
    if (size > 256 * 1024) return false;
    const auto first = address >> kPageBits;
    const auto last = (address + size - 1) >> kPageBits;
    for (auto word = first / 64; word <= last / 64; ++word) {
        const auto bits = Bits(word == first / 64 ? first % 64 : 0,
                               word == last / 64 ? last % 64 : 63);
        if (held[word].load(std::memory_order_acquire) & bits) return false;
    }
    return true;
}
} // namespace Eden::ImagePages
