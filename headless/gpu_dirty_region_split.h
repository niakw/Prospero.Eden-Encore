// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// The GPU dirty collector's 32-bit mask represents exactly 32 x 64-byte
// cells (2 KiB). A guest write crossing a collector boundary must be split
// BEFORE calling GPUDirtyMemoryManager::Collect(), not after.
#include <algorithm>
#include <cstdint>
#include <exception>
#include <limits>

namespace Eden::GpuDirty {
inline constexpr std::uint64_t kRegionBytes = 2048;

template <class Collect>
void ForEachRegion(std::uint64_t address, std::uint64_t size, Collect&& collect) {
    // Fail closed rather than silently wrap a guest address or lose a range.
    if (size > std::numeric_limits<std::uint64_t>::max() - address) {
        std::terminate();
    }
    while (size != 0) {
        const auto amount = std::min(size, kRegionBytes - (address % kRegionBytes));
        collect(address, amount);
        address += amount;
        size -= amount;
    }
}
} // namespace Eden::GpuDirty
