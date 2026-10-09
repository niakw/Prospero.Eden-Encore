// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstddef>
#include <limits>

namespace pe::gfx {
// Rotate independent VBO storage to avoid rewriting a buffer still being read
// by the previous display frame. GL itself orders reuse if the queue backs up.
inline constexpr std::size_t kStreamBufferSlots = 3;

// Grow only when the current GL store is genuinely too small. Amortize
// scrolling UI size changes; do not re-specify same-sized storage per frame.
constexpr std::size_t StreamCapacity(std::size_t current, std::size_t required) noexcept {
    if (required <= current) return current;
    std::size_t result = current ? current : 512u;
    while (result < required) {
        if (result > std::numeric_limits<std::size_t>::max() / 2u)
            return required;  // no multiplication overflow
        result *= 2u;
    }
    return result;
}
} // namespace pe::gfx
