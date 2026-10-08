// ProsperoEden - The launcher's textures: its own art and lazily loaded covers.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include "pe/ui/textures.hpp"

#include "pe/core/log.hpp"

#include <algorithm>
#include <chrono>
#include <future>
#include <utility>

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
    // The worker only reads/decompresses CPU-side bytes. Its lifetime must
    // end before the Services reference backing it can be destroyed.
    if (decode_.valid()) {
        decode_.wait();
        try { (void)decode_.get(); } catch (...) {}
    }
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
        entry.generation = ++next_generation_;
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

void Textures::invalidate(const std::string &path)
{
    if (path.empty()) return;
    for (auto it = covers_.begin(); it != covers_.end(); )
    {
        if (it->second.path == path) {
            batch_.delete_texture(it->second.texture);
            it = covers_.erase(it);
        } else {
            ++it;
        }
    }
}

void Textures::pump(float dt, int budget)
{
    ++frame_;
    for (auto &[key, entry] : covers_)
        if (entry.loaded)
            entry.age += dt;

    // Decoding a 1920x1080 Nlib JPEG/TGA and generating downsized copies on
    // the UI thread caused visible menu repeat/scroll stalls (>100 ms).
    // Only the GL texture upload stays on the owner thread. Handle *at most
    // one* completed upload this frame and prefetch the next image afterwards.
    if (decode_.valid() &&
        decode_.wait_for(std::chrono::seconds(0)) == std::future_status::ready)
    {
        try {
            DecodedCover result = decode_.get();
            const auto it = covers_.find(result.key);
            if (it != covers_.end() &&
                it->second.generation == result.generation) {
                Entry &entry = it->second;
                entry.loaded = true;
                entry.age = 0.0f;
                if (!result.ok || result.image.empty()) {
                    entry.failed_loads = std::min(entry.failed_loads + 1u, 4u);
                } else {
                    entry.failed_loads = 0;
                    entry.aspect = static_cast<float>(result.image.width) /
                                   static_cast<float>(result.image.height);
                    entry.texture = create(result.image);
                    if (entry.texture == 0)
                        entry.failed_loads = std::min(entry.failed_loads + 1u, 4u);
                }
            }
        } catch (const std::exception& error) {
            sys::log("cover decode failed: %s", error.what());
        } catch (...) {
            sys::log("cover decode failed: unknown error");
        }
        // A consumed future is invalid. The next queued image can start now.
    }

    if (budget > 0 && !decode_.valid()) {
        while (!queue_.empty()) {
            std::string key = std::move(queue_.front());
            queue_.erase(queue_.begin());
            const auto it = covers_.find(key);
            if (it == covers_.end() || it->second.loaded) continue;
            const std::string path = it->second.path;
            const int level = it->second.level;
            const auto generation = it->second.generation;
            try {
                decode_ = std::async(std::launch::async,
                    [this, key = std::move(key), path, level, generation]() mutable {
                        DecodedCover decoded;
                        decoded.key = std::move(key);
                        decoded.generation = generation;
                        decoded.ok = services_.load_image(path, &decoded.image);
                        if (decoded.ok) {
                            for (int i = 0; i < level &&
                                 decoded.image.width > 64 &&
                                 decoded.image.height > 64; ++i)
                                decoded.image = gfx::halve(decoded.image);
                        }
                        return decoded;
                    });
            } catch (const std::exception& error) {
                sys::log("cover queue failed: %s", error.what());
                it->second.loaded = true;
                it->second.failed_loads = std::min(it->second.failed_loads + 1u, 4u);
            }
            break;
        }
    }

    if (covers_.size() > kMaxCovers)
    {
        // Drop textures not drawn recently, but never an entry that is still
        // loading. A completed stale worker response is rejected by its
        // generation token if the path was invalidated/recreated meanwhile.
        std::vector<std::pair<std::uint64_t, std::string>> order;
        for (const auto &[key, entry] : covers_)
            if (entry.loaded && entry.used + 2 < frame_)
                order.emplace_back(entry.used, key);
        std::sort(order.begin(), order.end());
        for (std::size_t index = 0; index < order.size() && covers_.size() > kMaxCovers * 3 / 4;
             ++index)
        {
            const auto found = covers_.find(order[index].second);
            if (found == covers_.end()) continue;
            batch_.delete_texture(found->second.texture);
            covers_.erase(found);
        }
    }
}

} // namespace pe::ui
