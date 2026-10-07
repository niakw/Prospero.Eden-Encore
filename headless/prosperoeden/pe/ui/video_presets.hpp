// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "encore_overrides_generated.h"
#include "encore_overrides_runtime.h"
#include "pe/ui/services.hpp"

#include <algorithm>
#include <cstdint>

namespace pe::ui {

using VideoPresetValues = Eden::EncoreOverrides::VideoProfile;

inline constexpr int kAuthoredVideoProfiles = Eden::EncoreOverrides::kAuthoredProfileCount;
inline constexpr int kCustomVideoProfile = Eden::EncoreOverrides::kCustomProfile;

inline VideoPresetValues VideoPresetForTitle(std::uint64_t title_id, int preset) {
    return Eden::EncoreOverridesRuntime::ProfileForTitle(title_id, preset);
}

inline int ClampVideoPreset(int preset) {
    return std::clamp(preset, 0, kAuthoredVideoProfiles - 1);
}

inline int CycleVideoPreset(int current, int step) {
    // Custom is derived from manual edits, never an authored preset to apply. From Custom, moving
    // right starts at Minimum; moving left starts at Ultra.
    if (current == kCustomVideoProfile)
        return step >= 0 ? 0 : kAuthoredVideoProfiles - 1;
    current = std::clamp(current, 0, kAuthoredVideoProfiles - 1);
    return (current + step + kAuthoredVideoProfiles) % kAuthoredVideoProfiles;
}

inline bool MatchesPreset(const Preferences& preferences, const VideoPresetValues& value) {
    return preferences.renderer == value.renderer && preferences.output == value.output &&
           preferences.resolution == value.resolution && preferences.filter == value.filter &&
           preferences.fsr_sharpness == value.fsr_sharpness &&
           preferences.anti_aliasing == value.anti_aliasing && preferences.refresh == value.refresh;
}

inline int DetectVideoProfile(const Preferences& preferences) {
    for (int preset = 0; preset < kAuthoredVideoProfiles; ++preset)
        if (MatchesPreset(preferences, VideoPresetForTitle(0, preset)))
            return preset;
    return kCustomVideoProfile;
}

inline void RefreshVideoProfile(Preferences& preferences) {
    preferences.performance_profile = DetectVideoProfile(preferences);
}

inline int DetectVideoProfile(const GameSettings& settings, const Preferences& global,
                              std::uint64_t title_id = 0) {
    const auto effective = [](int local, int fallback) { return local >= 0 ? local : fallback; };
    for (int preset = 0; preset < kAuthoredVideoProfiles; ++preset) {
        const auto value = VideoPresetForTitle(title_id, preset);
        if (effective(settings.renderer, global.renderer) == value.renderer &&
            effective(settings.output, global.output) == value.output &&
            effective(settings.resolution, global.resolution) == value.resolution &&
            effective(settings.filter, global.filter) == value.filter &&
            effective(settings.fsr_sharpness, global.fsr_sharpness) == value.fsr_sharpness &&
            effective(settings.anti_aliasing, global.anti_aliasing) == value.anti_aliasing &&
            effective(settings.refresh, global.refresh) == value.refresh &&
            (settings.console_mode < 0 || (settings.console_mode == 1) == value.docked))
            return preset;
    }
    return kCustomVideoProfile;
}

inline void RefreshVideoProfile(GameSettings& settings, const Preferences& global,
                                std::uint64_t title_id = 0) {
    settings.performance_profile = DetectVideoProfile(settings, global, title_id);
}

inline void ApplyVideoPreset(Preferences& preferences, int preset) {
    const auto value = VideoPresetForTitle(0, ClampVideoPreset(preset));
    preferences.performance_profile = ClampVideoPreset(preset);
    preferences.renderer = value.renderer;
    preferences.output = value.output;
    preferences.resolution = value.resolution;
    preferences.filter = value.filter;
    preferences.fsr_sharpness = value.fsr_sharpness;
    preferences.anti_aliasing = value.anti_aliasing;
    preferences.refresh = value.refresh;
}

inline void ApplyVideoPreset(GameSettings& settings, int preset, std::uint64_t title_id = 0) {
    preset = ClampVideoPreset(preset);
    const auto value = VideoPresetForTitle(title_id, preset);
    settings.performance_profile = preset;
    settings.console_mode = value.docked ? 1 : 0;
    settings.renderer = value.renderer;
    settings.output = value.output;
    settings.resolution = value.resolution;
    settings.filter = value.filter;
    settings.fsr_sharpness = value.fsr_sharpness;
    settings.anti_aliasing = value.anti_aliasing;
    settings.refresh = value.refresh;
}

} // namespace pe::ui
