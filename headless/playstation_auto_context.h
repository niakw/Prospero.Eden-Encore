// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>

namespace Eden::Controls {
// A Nintendo title does not expose a generic "on pitch", "popup", "pause
// overlay" or "main menu" bit through the controller API. Guessing a return
// to menus from D-pad / Options / Touchpad **while a game is running** changes
// face-button bindings in the middle of a match. Once gameplay was observed,
// keep its qualified mapping for the rest of the title launch. A fresh title
// creates a fresh Pad and therefore resets this state.
//
// This deliberately does NOT claim to identify the game's internal UI. The
// user can select a fixed Switch/Custom mapping instead of PlayStation Auto.
class PlayStationAutoContext {
public:
    enum class Mode : unsigned char { menu, gameplay };
    constexpr Mode mode() const noexcept { return mode_; }
    constexpr bool gameplay() const noexcept { return mode_ == Mode::gameplay; }
    constexpr bool observe(bool gameplay_motion, bool face_button_held,
                           unsigned gain, unsigned threshold) noexcept {
        if (gameplay()) return false;  // Pause/modal/d-pad never undo gameplay.
        if (gameplay_motion)
            evidence_ = std::min(evidence_ + gain, threshold + 8u);
        else if (evidence_ > 0)
            --evidence_;
        // Do not swap physical A/B or X/Y while a face button is down: the
        // guest would see a synthetic release/press crossing scene boundaries.
        if (evidence_ < threshold || face_button_held) return false;
        mode_ = Mode::gameplay;
        return true;
    }
    constexpr void reset() noexcept {
        mode_ = Mode::menu;
        evidence_ = 0;
    }
private:
    Mode mode_ = Mode::menu;
    unsigned evidence_ = 0;
};
} // namespace Eden::Controls
