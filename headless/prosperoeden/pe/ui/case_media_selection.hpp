// Eden Encore — deterministic selection for procedurally composed case art.
// Only real, already-cached media is eligible. No external source fetches,
// guessed screenshots, duplicates or allocated copies in the draw loop.
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <array>
#include <string>
#include <vector>

namespace pe::ui::case_media {

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

// Back: a hero often comes from screenshots[0]. Iterate ALL available
// screenshots so screenshots[2+] can still populate two *different*
// panels. Never portray one scene twice as two distinct game captures.
// A real icon/poster may occupy one otherwise-empty slot, with aspect-fit.
inline std::array<const std::string*, 2> BackScenes(
    const std::string& featured, const std::string& cover,
    const std::vector<std::string>& screenshots) noexcept
{
    std::array<const std::string*, 2> selected{nullptr, nullptr};
    const auto accept = [&](const std::string& image) {
        if (image.empty() || image == featured ||
            (selected[0] && *selected[0] == image)) return;
        if (!selected[0]) selected[0] = &image;
        else if (!selected[1]) selected[1] = &image;
    };
    for (const auto& shot : screenshots) {
        accept(shot);
        if (selected[1]) break;
    }
    if (!selected[1]) accept(cover);
    return selected;
}

} // namespace pe::ui::case_media
