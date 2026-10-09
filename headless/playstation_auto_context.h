// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>

namespace Eden::Controls {
// No generic Nintendo HID field says "menu", "match", or "cutscene".
// Avoid switching A/B or X/Y from a lone D-pad or Options press: these are
// ordinary gameplay inputs in FC27. A sustained quiet/navigation sequence can
// restore menu semantics; user has a deliberate chord fallback when the title
// UI cannot be detected from controller activity alone.
class PlayStationAutoContext {
public:
    enum class Mode : unsigned char { menu, gameplay };
    enum class Transition : unsigned char { none, to_gameplay, to_menu };
    constexpr Mode mode() const noexcept { return mode_; }
    constexpr bool gameplay() const noexcept { return mode_ == Mode::gameplay; }
    constexpr bool manually_selected() const noexcept { return manual_; }

    // Touchpad + Square: cycle to the other physical semantic mapping.
    // A manual choice is stable for the remainder of the title, or until
    // explicitly toggled again. Automatic inferences must never undo it.
    constexpr Transition manual_toggle() noexcept {
        mode_ = gameplay() ? Mode::menu : Mode::gameplay;
        manual_ = true;
        evidence_ = quiet_ = menu_evidence_ = 0;
        return gameplay() ? Transition::to_gameplay : Transition::to_menu;
    }

    constexpr Transition observe(bool gameplay_motion, bool face_button_held,
                                 bool navigation_edge, bool options_edge,
                                 unsigned gain, unsigned gameplay_threshold,
                                 unsigned quiet_threshold, unsigned menu_threshold,
                                 unsigned navigation_gain, unsigned options_gain) noexcept {
        if (manual_) return Transition::none;
        if (gameplay()) {
            if (gameplay_motion) {
                quiet_ = menu_evidence_ = 0;
                return Transition::none;
            }
            if (quiet_ < quiet_threshold) ++quiet_;
            if (quiet_ < quiet_threshold) return Transition::none;
            // The game may accept a D-pad tap as a tactical command in match.
            // Require a *sequence* of independent navigation presses after
            // sustained stick+trigger inactivity, not one press or held key.
            if (navigation_edge)
                menu_evidence_ = std::min(menu_evidence_ + navigation_gain, menu_threshold);
            if (options_edge)
                menu_evidence_ = std::min(menu_evidence_ + options_gain, menu_threshold);
            if (menu_evidence_ < menu_threshold || face_button_held)
                return Transition::none;
            mode_ = Mode::menu;
            evidence_ = quiet_ = menu_evidence_ = 0;
            return Transition::to_menu;
        }
        if (gameplay_motion)
            evidence_ = std::min(evidence_ + gain, gameplay_threshold + 8u);
        else if (evidence_ > 0)
            --evidence_;
        // Do not synthesize a release/press across a face button being held.
        if (evidence_ < gameplay_threshold || face_button_held)
            return Transition::none;
        mode_ = Mode::gameplay;
        quiet_ = menu_evidence_ = 0;
        return Transition::to_gameplay;
    }
    constexpr void reset() noexcept {
        mode_ = Mode::menu;
        manual_ = false;
        evidence_ = quiet_ = menu_evidence_ = 0;
    }

private:
    Mode mode_ = Mode::menu;
    bool manual_ = false;
    unsigned evidence_ = 0;
    unsigned quiet_ = 0;
    unsigned menu_evidence_ = 0;
};
} // namespace Eden::Controls
