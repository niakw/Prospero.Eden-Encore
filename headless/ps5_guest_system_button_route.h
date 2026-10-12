// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>

// DualSense PS/Home is reserved by Sony and not available in scePadRead.
// Use Touchpad+Options as an explicit guest HOME fallback. A completed chord
// latches suppression of both input buttons until BOTH have been released,
// avoiding an unwanted guest Plus or Minus when one side releases first.
namespace Eden {
struct GuestSystemButtonRoute {
    bool home_latched = false;

    bool Observe(bool touchpad, bool options, bool other_touch_shortcut) noexcept {
        const bool home_down = touchpad && options && !other_touch_shortcut;
        if (home_down) home_latched = true;
        if (!touchpad && !options) home_latched = false;
        return home_down;
    }
    bool BlockChordButtons() const noexcept { return home_latched; }
};
} // namespace Eden
