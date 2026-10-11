// SPDX-License-Identifier: GPL-3.0-or-later
// Pure input-edge accounting shared by native pad diagnostics and host replay.
// Called only for usable DualSense samples when Detailed Logging is enabled.
#pragma once
#include <cstdint>
namespace Eden {
struct PadEdgeDiagnostics {
    std::uint64_t changes{}, cross{}, circle{}, square{}, triangle{};
    void Observe(std::uint32_t previous, std::uint32_t pressed,
                 std::uint32_t cross_mask, std::uint32_t circle_mask,
                 std::uint32_t square_mask, std::uint32_t triangle_mask) noexcept {
        if (previous == pressed) return;
        ++changes;
        if ((pressed & cross_mask) && !(previous & cross_mask)) ++cross;
        if ((pressed & circle_mask) && !(previous & circle_mask)) ++circle;
        if ((pressed & square_mask) && !(previous & square_mask)) ++square;
        if ((pressed & triangle_mask) && !(previous & triangle_mask)) ++triangle;
    }
};
} // namespace Eden
