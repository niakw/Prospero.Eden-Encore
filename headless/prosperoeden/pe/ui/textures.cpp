// ProsperoEden - The launcher's textures: its own art and lazily loaded covers.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include "pe/ui/textures.hpp"

#include "pe/core/log.hpp"

#include <algorithm>

namespace pe::ui
{

namespace
{

constexpr std::size_t kMaxCovers = 160;

} // namespace

Textures::~Textures()
{
    release();
}

std::uint32_t Textures::create(const gfx::Image &image)
{
    return image.empty() ? 0 : batch_.create_texture(image.width, image.height, image.rgba.data());
}

bool Textures::load_art(const std::string &directory)
{
    const auto load = [&](const char *name, std::uint32_t *texture)
    {
        gfx::Image image;
        if (!gfx::load_tga(directory + "/" + name, &image))
        {
            sys::log("art %s could not be read", name);
            return false;
        }
        *texture = create(image);
        return *texture != 0;
    };
    // The package generates this from assets/encore-background.jpg. It is launcher-only and is
    // released before a game starts, so it does not consume gameplay VRAM.
    (void)load("art/backdrop.tga", &backdrop_);
    const bool brand = load("art/brand.tga", &brand_);
    // Only the home screen's controller display needs this one.
    (void)load("art/controller.tga", &controller_);
    return brand;
}

void Textures::release()
{
    for (std::uint32_t *texture : {&backdrop_, &backdrop_blur_, &brand_, &controller_})
    {
        batch_.delete_texture(*texture);
        *texture = 0;
    }
    for (auto &[key, entry] : covers_)
        batch_.delete_texture(entry.texture);
    covers_.clear();
    queue_.clear();
}

Cover Textures::cover(const std::string &path, float size)
{
    if (path.empty())
        return {0, 0.0f, true, 1.0f};
    // Covers are 256 pixels a side: draw a small one from a halved copy, which
    // a single-level texture cannot do for itself.
    const float pixels = size * output_scale_;
    const int level = pixels > 128.0f ? 0 : pixels > 64.0f ? 1 : 2;
    const std::string key = path + '#' + static_cast<char>('0' + level);
    auto it = covers_.find(key);
    if (it == covers_.end())
    {
        Entry entry;
        entry.path = path;
        entry.level = level;
        it = covers_.emplace(key, std::move(entry)).first;
        queue_.push_back(key);
    }
    it->second.used = frame_;
    // Nlib downloads arrive by atomic rename. Poll a missing *visible* cover
    // once after 450 ms (instead of freezing its placeholder for three seconds),
    // then back off to 1.5 / 3 s if it is truly absent. No per-frame stat().
    const float retry_after = it->second.failed_loads <= 1 ? 0.45f :
                              it->second.failed_loads == 2 ? 1.5f : 3.0f;
    if (it->second.loaded && it->second.texture == 0 &&
        it->second.age >= retry_after) {
        it->second.loaded = false;
        it->second.age = 0.0f;
        queue_.push_back(key);
    }
    return {it->second.texture, it->second.age, it->second.loaded && it->second.texture == 0,
            it->second.aspect};
}

void Textures::pump(float dt, int budget)
{
    ++frame_;
    for (auto &[key, entry] : covers_)
        if (entry.loaded)
            entry.age += dt;
    while (budget > 0 && !queue_.empty())
    {
        const std::string key = queue_.front();
        queue_.erase(queue_.begin());
        const auto it = covers_.find(key);
        if (it == covers_.end() || it->second.loaded)
            continue;
        Entry &entry = it->second;
        entry.loaded = true;
        // Count every attempted disk read against the frame budget, including
        // missing files. Previously failures did not consume budget; with a
        // large library this could probe hundreds of absent Nlib files in ONE
        // UI frame and produce a visible stall.
        --budget;
        gfx::Image image;
        if (!services_.load_image(entry.path, &image)) {
            entry.failed_loads = std::min(entry.failed_loads + 1u, 4u);
            continue; // neutral placeholder; visible tiles retry with backoff
        }
        entry.failed_loads = 0;
        for (int level = 0; level < entry.level && image.width > 64; ++level)
            image = gfx::halve(image);
        if (image.height > 0)
            entry.aspect = static_cast<float>(image.width) / static_cast<float>(image.height);
        entry.texture = create(image);
    }
    if (covers_.size() > kMaxCovers)
    {
        // Drop the covers not drawn for the longest time.
        std::vector<std::pair<std::uint64_t, std::string>> order;
        for (const auto &[key, entry] : covers_)
            if (entry.loaded && entry.used + 2 < frame_)
                order.emplace_back(entry.used, key);
        std::sort(order.begin(), order.end());
        for (std::size_t index = 0; index < order.size() && covers_.size() > kMaxCovers * 3 / 4;
             ++index)
        {
            batch_.delete_texture(covers_[order[index].second].texture);
            covers_.erase(order[index].second);
        }
    }
}

} // namespace pe::ui
