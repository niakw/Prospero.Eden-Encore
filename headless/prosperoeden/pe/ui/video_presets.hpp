// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "pe/ui/services.hpp"

#include <algorithm>
#include <iterator>

namespace pe::ui {

struct VideoPresetValues {
    int renderer;
    int output;
    int resolution;
    int filter;
    int refresh;
};

// Conservative PS5 presets. Advanced rows remain editable after applying a preset.
inline constexpr VideoPresetValues kVideoPresets[] = {
    // Recommended: native internal resolution and the lightest scaler.
    {1, 0, 3, 0, 0},
    // Smooth: a small resolution reduction, recovered with FSR.
    {1, 0, 2, 1, 0},
    // Performance: prioritize headroom and memory pressure over sharpness.
    {1, 0, 1, 1, 0},
};

inline int ClampVideoPreset(int preset) {
    return std::clamp(preset, 0, static_cast<int>(std::size(kVideoPresets)) - 1);
}

inline void ApplyVideoPreset(Preferences& preferences, int preset) {
    preset = ClampVideoPreset(preset);
    const auto& value = kVideoPresets[preset];
    preferences.performance_profile = preset;
    preferences.renderer = value.renderer;
    preferences.output = value.output;
    preferences.resolution = value.resolution;
    preferences.filter = value.filter;
    preferences.refresh = value.refresh;
}

inline void ApplyVideoPreset(GameSettings& settings, int preset) {
    preset = ClampVideoPreset(preset);
    const auto& value = kVideoPresets[preset];
    settings.performance_profile = preset;
    settings.renderer = value.renderer;
    settings.resolution = value.resolution;
    settings.filter = value.filter;
    settings.refresh = value.refresh;
}

} // namespace pe::ui
