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
    int fsr_sharpness;
    int anti_aliasing;
    int refresh;
};

// Conservative PS5 presets. Advanced rows remain editable after applying a preset.
inline constexpr VideoPresetValues kVideoPresets[] = {
    // Recommended: native game resolution, moderate TV output, no sharpening artifacts.
    {1, 1, 3, 0, 88, 0, 0},
    // Smooth: native game resolution at the lightest stable output path.
    {1, 0, 3, 0, 88, 0, 0},
    // Performance: lower internal load, recovered with moderate FSR sharpening.
    {1, 0, 2, 1, 50, 0, 0},
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
    preferences.fsr_sharpness = value.fsr_sharpness;
    preferences.anti_aliasing = value.anti_aliasing;
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
