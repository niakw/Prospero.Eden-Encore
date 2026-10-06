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
    {1, 1, 3, 0, 50, 1, 0},
    // Smooth: native game resolution at the lightest stable output path.
    {1, 0, 3, 0, 50, 0, 0},
    // Performance: lower internal load, recovered with moderate FSR sharpening.
    {1, 0, 2, 1, 50, 0, 0},
};

inline int ClampVideoPreset(int preset) {
    return std::clamp(preset, 0, static_cast<int>(std::size(kVideoPresets)) - 1);
}

inline constexpr int kCustomVideoProfile = 3;

inline int CycleVideoPreset(int current, int step) {
    // Custom is derived from manual edits, never an authored preset to apply. From Custom, moving
    // right starts again at Recommended; moving left starts at Performance.
    if (current == kCustomVideoProfile)
        return step >= 0 ? 0 : 2;
    current = std::clamp(current, 0, 2);
    return (current + step + 3) % 3;
}

inline int DetectVideoProfile(const Preferences& preferences) {
    for (int preset = 0; preset < static_cast<int>(std::size(kVideoPresets)); ++preset) {
        const auto& value = kVideoPresets[preset];
        if (preferences.renderer == value.renderer && preferences.output == value.output &&
            preferences.resolution == value.resolution && preferences.filter == value.filter &&
            preferences.fsr_sharpness == value.fsr_sharpness &&
            preferences.anti_aliasing == value.anti_aliasing && preferences.refresh == value.refresh)
            return preset;
    }
    return kCustomVideoProfile;
}

inline void RefreshVideoProfile(Preferences& preferences) {
    preferences.performance_profile = DetectVideoProfile(preferences);
}

inline int DetectVideoProfile(const GameSettings& settings, const Preferences& global) {
    const auto effective = [](int local, int fallback) { return local >= 0 ? local : fallback; };
    for (int preset = 0; preset < static_cast<int>(std::size(kVideoPresets)); ++preset) {
        const auto& value = kVideoPresets[preset];
        if (effective(settings.renderer, global.renderer) == value.renderer &&
            effective(settings.output, global.output) == value.output &&
            effective(settings.resolution, global.resolution) == value.resolution &&
            effective(settings.filter, global.filter) == value.filter &&
            effective(settings.fsr_sharpness, global.fsr_sharpness) == value.fsr_sharpness &&
            effective(settings.anti_aliasing, global.anti_aliasing) == value.anti_aliasing &&
            effective(settings.refresh, global.refresh) == value.refresh)
            return preset;
    }
    return kCustomVideoProfile;
}

inline void RefreshVideoProfile(GameSettings& settings, const Preferences& global) {
    settings.performance_profile = DetectVideoProfile(settings, global);
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
    settings.output = value.output;
    settings.resolution = value.resolution;
    settings.filter = value.filter;
    settings.fsr_sharpness = value.fsr_sharpness;
    settings.anti_aliasing = value.anti_aliasing;
    settings.refresh = value.refresh;
}

} // namespace pe::ui
