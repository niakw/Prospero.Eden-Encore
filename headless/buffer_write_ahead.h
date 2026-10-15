// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Conservative write-ahead for already registered guest buffer pages.
// Caller MUST hold the buffer-cache mutex. Never marks texture/shader pages.
#include <algorithm>
#include <cstdint>
#include <limits>
#include <utility>

namespace Eden::BufferWriteAhead {
inline constexpr std::uint64_t PageBytes = 4096;
inline constexpr unsigned MaxPages = 64;

template <class CoversBuffer, class MarkCpuModified>
unsigned MarkFollowingPages(std::uint64_t address, std::uint64_t size, unsigned requested,
                            CoversBuffer&& covers_buffer, MarkCpuModified&& mark_cpu_modified) {
    if (!size || !requested || size - 1 > UINT64_MAX - address) return 0;
    const std::uint64_t last = address + size - 1;
    // No page after the write fits the address space.
    if (last >= UINT64_MAX - PageBytes) return 0;
    std::uint64_t next = (last & ~(PageBytes - 1)) + PageBytes;
    unsigned marked = 0;
    for (const unsigned limit = std::min(requested, MaxPages); marked < limit; ) {
        // Do not declare an unregistered page CPU-dirty: this cannot invent ownership.
        if (!covers_buffer(next, PageBytes) || mark_cpu_modified(next, PageBytes)) break;
        ++marked;
        if (next > UINT64_MAX - PageBytes) break;
        next += PageBytes;
    }
    return marked;
}
} // namespace Eden::BufferWriteAhead
