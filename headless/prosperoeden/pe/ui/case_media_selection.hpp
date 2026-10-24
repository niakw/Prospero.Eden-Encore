// Eden Encore — deterministic selection for procedurally composed case art.
// Only real, already-cached media is eligible. No external source fetches,
// guessed screenshots, duplicates or allocated copies in the draw loop.
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <array>
#include <string>
#include <vector>

namespace pe::ui::case_media {

// The front uses an edge-to-edge source: hero, first usable screenshot,
// finally the icon. All cases preserve the source's aspect via cover UVs.
inline const std::string* FrontPaper(
    const std::string& featured, const std::string& cover,
    const std::vector<std::string>& screenshots) noexcept
{
    if (!featured.empty()) return &featured;
    for (const auto& shot : screenshots)
        if (!shot.empty()) return &shot;
    return cover.empty() ? nullptr : &cover;
}

// Front: choose the first genuine alternate scene, not a duplicate of
// the feature image. Fall back to an independent cached app icon/poster.
inline const std::string* FrontAlternate(
    const std::string& featured, const std::string& cover,
    const std::vector<std::string>& screenshots) noexcept
{
    for (const auto& shot : screenshots) {
        if (!shot.empty() && shot != featured)
            return &shot;
    }
    return !cover.empty() && cover != featured ? &cover : nullptr;
}

// Rear source priorities: LaunchBox fanart, game-title screenshot, gameplay.
// Missing categories use distinct Nlib screenshots; the cover/front is never
// injected as a floating square. Results reference owned game metadata.
inline std::array<const std::string*, 3> BackScenes(
    const std::string& featured, const std::string& cover,
    const std::vector<std::string>& screenshots) noexcept
{
    std::array<const std::string*, 3> selected{nullptr, nullptr, nullptr};
    const auto accept = [&](const std::string& image) {
        if (image.empty() || image == featured || image == cover) return;
        for (const auto* existing : selected)
            if (existing && *existing == image) return;
        for (auto& entry : selected)
            if (!entry) { entry = &image; return; }
    };
    // These canonical local filenames are built by EnsureRetailCase; unlike
    // arbitrary Nlib screenshots they identify three actual media categories.
    for (int category = 1; category <= 3; ++category) {
        const std::string marker =
            "/box-scene-" + std::to_string(category) + "-";
        for (const auto& image : screenshots)
            if (image.find(marker) != std::string::npos) {
                accept(image);
                break;
            }
    }
    for (const auto& image : screenshots) accept(image);
    return selected;
}

} // namespace pe::ui::case_media
