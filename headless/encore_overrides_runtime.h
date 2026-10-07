// SPDX-License-Identifier: GPL-3.0-or-later
// Optional runtime layer over the generated encore-overrides snapshot.
#pragma once

#include "encore_overrides_generated.h"
#include "storage_paths.h"

#include <array>
#include <cctype>
#include <cstdint>
#include <fstream>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

namespace Eden::EncoreOverridesRuntime {

using VideoProfile = EncoreOverrides::VideoProfile;

struct TitleProfiles {
    std::uint64_t title_id = 0;
    std::array<VideoProfile, EncoreOverrides::kAuthoredProfileCount> profiles{};
};

struct State {
    bool valid = false;
    int database_revision = 0;
    std::array<VideoProfile, EncoreOverrides::kAuthoredProfileCount> general{};
    std::vector<TitleProfiles> titles;
};

inline std::string ManifestPath() {
    return ConfigFile("encore-overrides-runtime.json");
}

inline std::optional<std::uint64_t> ParseTitleId(std::string_view value) {
    if (value.size() != 16) return std::nullopt;
    std::uint64_t result = 0;
    for (unsigned char c : value) {
        unsigned digit = 0;
        if (c >= '0' && c <= '9') digit = c - '0';
        else if (c >= 'A' && c <= 'F') digit = c - 'A' + 10;
        else if (c >= 'a' && c <= 'f') digit = c - 'a' + 10;
        else return std::nullopt;
        result = (result << 4) | digit;
    }
    return result == 0 ? std::nullopt : std::optional<std::uint64_t>{result};
}

inline std::optional<VideoProfile> ParseProfile(const nlohmann::json& settings) {
    if (!settings.is_object()) return std::nullopt;
    const auto string_value = [&](const char* key) -> std::optional<std::string> {
        const auto it = settings.find(key);
        return it != settings.end() && it->is_string() ?
            std::optional<std::string>{it->get<std::string>()} : std::nullopt;
    };
    const auto int_value = [&](const char* key) -> std::optional<int> {
        const auto it = settings.find(key);
        return it != settings.end() && it->is_number_integer() ?
            std::optional<int>{it->get<int>()} : std::nullopt;
    };
    const auto renderer = string_value("renderer");
    const auto output = string_value("tv_output");
    const auto filter = string_value("upscaling_filter");
    const auto aa = string_value("anti_aliasing");
    const auto mode = string_value("console_mode");
    const auto fsr = int_value("fsr_sharpness");
    const auto refresh = int_value("refresh_rate_hz");
    const auto resolution_it = settings.find("game_resolution");
    if (!renderer || !output || !filter || !aa || !mode || !fsr || !refresh ||
        resolution_it == settings.end() || !resolution_it->is_number())
        return std::nullopt;

    VideoProfile p{};
    if (*renderer == "opengl") p.renderer = 0;
    else if (*renderer == "vulkan") p.renderer = 1;
    else return std::nullopt;

    if (*output == "1080p") p.output = 0;
    else if (*output == "1440p") p.output = 1;
    else if (*output == "2160p") p.output = 2;
    else return std::nullopt;

    const double resolution = resolution_it->get<double>();
    static constexpr std::array<double, 9> scales{0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0};
    p.resolution = -1;
    for (std::size_t i = 0; i < scales.size(); ++i)
        if (resolution > scales[i] - 0.001 && resolution < scales[i] + 0.001) {
            p.resolution = static_cast<int>(i);
            break;
        }
    if (p.resolution < 0) return std::nullopt;

    if (*filter == "bilinear") p.filter = 0;
    else if (*filter == "fsr") p.filter = 1;
    else if (*filter == "bicubic") p.filter = 2;
    else if (*filter == "nearest") p.filter = 3;
    else return std::nullopt;

    if (*fsr < 0 || *fsr > 100) return std::nullopt;
    p.fsr_sharpness = *fsr;
    if (*aa == "none") p.anti_aliasing = 0;
    else if (*aa == "fxaa") p.anti_aliasing = 1;
    else if (*aa == "smaa") p.anti_aliasing = 2;
    else return std::nullopt;
    if (*refresh == 60) p.refresh = 0;
    else if (*refresh == 120) p.refresh = 1;
    else return std::nullopt;
    if (*mode == "docked") p.docked = true;
    else if (*mode == "handheld") p.docked = false;
    else return std::nullopt;
    return p;
}

inline bool ParseManifest(const nlohmann::json& root, State* out) {
    if (out == nullptr || !root.is_object() || root.value("schema_version", 0) != 1)
        return false;
    const int revision = root.value("database_revision", -1);
    // Never let an older remote database override the snapshot shipped with this binary.
    if (revision < EncoreOverrides::kDatabaseRevision) return false;
    const auto general_it = root.find("general_profiles");
    const auto titles_it = root.find("specific_titles");
    if (general_it == root.end() || !general_it->is_object() || titles_it == root.end() ||
        !titles_it->is_array() || titles_it->size() > 512)
        return false;

    State parsed;
    parsed.database_revision = revision;
    static constexpr const char* names[] = {"minimum", "recommended", "high", "ultra"};
    for (int tier = 0; tier < EncoreOverrides::kAuthoredProfileCount; ++tier) {
        const auto profile_it = general_it->find(names[tier]);
        if (profile_it == general_it->end() || !profile_it->is_object()) return false;
        const auto settings_it = profile_it->find("settings");
        if (settings_it == profile_it->end()) return false;
        const auto profile = ParseProfile(*settings_it);
        if (!profile) return false;
        parsed.general[static_cast<std::size_t>(tier)] = *profile;
    }
    for (const auto& item : *titles_it) {
        if (!item.is_object()) return false;
        const auto id_it = item.find("title_id");
        const auto profiles_it = item.find("profiles");
        if (id_it == item.end() || !id_it->is_string() || profiles_it == item.end() ||
            !profiles_it->is_object())
            return false;
        const auto title_id = ParseTitleId(id_it->get<std::string>());
        if (!title_id) return false;
        TitleProfiles entry;
        entry.title_id = *title_id;
        for (int tier = 0; tier < EncoreOverrides::kAuthoredProfileCount; ++tier) {
            const auto it = profiles_it->find(names[tier]);
            if (it == profiles_it->end()) return false;
            const auto profile = ParseProfile(*it);
            if (!profile) return false;
            entry.profiles[static_cast<std::size_t>(tier)] = *profile;
        }
        parsed.titles.push_back(entry);
    }
    parsed.valid = true;
    *out = std::move(parsed);
    return true;
}

inline bool ParseManifestText(std::string_view body, State* out) {
    if (body.empty() || body.size() > (128u << 10)) return false;
    try {
        return ParseManifest(nlohmann::json::parse(body.begin(), body.end()), out);
    } catch (...) {
        return false;
    }
}

inline State LoadCachedState() {
    std::ifstream file(ManifestPath(), std::ios::binary);
    if (!file) return {};
    std::string body((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    State state;
    return ParseManifestText(body, &state) ? state : State{};
}

inline const State& CachedState() {
    static const State state = LoadCachedState();
    return state;
}

inline VideoProfile ProfileForTitle(std::uint64_t title_id, int tier) {
    tier = EncoreOverrides::ClampTier(tier);
    const State& state = CachedState();
    if (state.valid) {
        for (const auto& entry : state.titles)
            if (entry.title_id == title_id)
                return entry.profiles[static_cast<std::size_t>(tier)];
        return state.general[static_cast<std::size_t>(tier)];
    }
    return EncoreOverrides::ProfileForTitle(title_id, tier);
}

inline bool HasRemoteProfile(std::uint64_t title_id) {
    const State& state = CachedState();
    if (!state.valid) return false;
    for (const auto& entry : state.titles)
        if (entry.title_id == title_id) return true;
    return false;
}

} // namespace Eden::EncoreOverridesRuntime
