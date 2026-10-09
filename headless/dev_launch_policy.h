// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string_view>

namespace Eden::DevLaunch {
// Diagnostic app builds must open the normal library by default. The
// development title ID selects a target for explicit unattended tests only.
// "launcher=first" and "autoboot=off" take precedence over autoboot=on.
struct BootIntent {
    bool requested = false;
    bool force_launcher = false;

    constexpr void Observe(std::string_view token) noexcept {
        if (token == "autoboot=on") requested = true;
        if (token == "autoboot=off" || token == "launcher=first")
            force_launcher = true;
    }
    constexpr bool ShouldAutoboot(bool previous_crash) const noexcept {
        return requested && !force_launcher && !previous_crash;
    }
};
} // namespace Eden::DevLaunch
