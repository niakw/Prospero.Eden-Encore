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

// Back: only independent screenshots. Never reinsert the front scene or
// the cover/icon as a floating panel with an opaque black matte. If no
// independent scenic asset exists, show the full paper ink and footer.
inline std::array<const std::string*, 2> BackScenes(
    const std::string& featured, const std::string& cover,
    const std::vector<std::string>& screenshots) noexcept
{
    std::array<const std::string*, 2> selected{nullptr, nullptr};
    const auto accept = [&](const std::string& image) {
        if (image.empty() || image == featured || image == cover ||
            (selected[0] && *selected[0] == image)) return;
        if (!selected[0]) selected[0] = &image;
        else if (!selected[1]) selected[1] = &image;
    };
    for (const auto& shot : screenshots) {
        accept(shot);
        if (selected[1]) break;
    }
    return selected;
}

} // namespace pe::ui::case_media
