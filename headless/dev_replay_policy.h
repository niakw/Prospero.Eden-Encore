// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string_view>

namespace Eden::DevInput {
// A test-title ID selects an autoboot target, not permission to seize input.
// Live DualSense remains the default even in all-on / FC27 developer builds.
constexpr bool ReplayRequestedAfter(bool requested, std::string_view token) noexcept {
    if (token == "replay=on") return true;
    if (token == "replay=off") return false;
    return requested;
}

constexpr bool ScriptedReplayEnabled(bool requested, std::string_view title_id,
                                      std::string_view profile_title_id) noexcept {
    return requested && title_id == profile_title_id;
}
} // namespace Eden::DevInput
