// ProsperoEden - The launcher's textures: its own art and lazily loaded covers.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include "pe/ui/textures.hpp"

#include "pe/ui/dualsense_mask_asset.hpp"
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
constexpr std::size_t kMaxTextureReclaimsPerFrame = 2;
// Nlib replaces images by atomic rename. Multiple invalidations can leave
// stale decode requests in the FIFO. Never drain an unbounded number of
// invalid keys in one held-D-pad UI frame; finish the backlog next frame.
constexpr std::size_t kMaxCoverQueueLookupsPerFrame = 24;

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
    // Licensed DualSense artwork is a compact 144x100 mask embedded in the
    // launcher. Decode it ONCE before any frame; no SVG parser, PNG I/O or
    // texture upload inside navigation/gameplay. Fall back to the old local
    // controller TGA if an asset revision is ever malformed.
    gfx::Image pad_image;
    pad_image.width = art::kDualSenseWidth;
    pad_image.height = art::kDualSenseHeight;
    constexpr std::size_t kPixels =
        static_cast<std::size_t>(art::kDualSenseWidth) * art::kDualSenseHeight;
    pad_image.rgba.resize(kPixels * 4u);
    std::size_t pixel = 0;
    bool valid = true;
    for (std::size_t i = 0; i < art::kDualSenseRunsCount; i += 2) {
        const std::size_t length = art::kDualSenseAlphaRuns[i];
        const auto level = art::kDualSenseAlphaRuns[i + 1];
        if (length == 0 || level > 3 || length > kPixels - pixel) {
            valid = false;
            break;
        }
        for (std::size_t n = 0; n < length; ++n, ++pixel) {
            auto* color = pad_image.rgba.data() + pixel * 4u;
            color[0] = color[1] = color[2] = 255;
            color[3] = static_cast<std::uint8_t>(level * 85u);
        }
    }
    if (valid && pixel == kPixels)
        controller_ = create(pad_image);
    if (!controller_)
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
    // A context is still current during release; drain the bounded-per-frame
    // invalidation backlog before destroying it to prevent orphaned GL IDs.
    for (const std::uint32_t texture : pending_deletes_)
        batch_.delete_texture(texture);
    pending_deletes_.clear();
    queue_.clear();
}

Cover Textures::cover(const std::string &path, float size)
{
    if (path.empty())
        return {0, 0.0f, true, 1.0f};
    // A 1920px Nlib screenshot used as a 300px library tile must not
    // upload the full 8 MiB RGBA image on the GL/UI thread. Quantize
    // requested physical pixels into stable power-of-two buckets, retaining
    // the unscaled source for the 1920px Home Hero.
    const float pixels = std::clamp(size * output_scale_, 1.0f, 2048.0f);
    int target_pixels = 64;
    while (target_pixels < pixels && target_pixels < 2048)
        target_pixels *= 2;
    const std::string key = path + '#' + std::to_string(target_pixels);
    auto it = covers_.find(key);
    if (it == covers_.end())
    {
        Entry entry;
        entry.path = path;
        entry.target_pixels = target_pixels;
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
            if (it->second.texture != 0)
                pending_deletes_.push_back(it->second.texture);
            it = covers_.erase(it);
        } else {
            ++it;
        }
    }
}

void Textures::pump(float dt, int budget)
{
    ++frame_;
    // Nlib can replace a banner, icon and three screenshots at once.
    // Invalidation itself performs zero GL calls; retire at most two of
    // their old textures here, spreading driver cleanup across frames.
    std::size_t deleted_this_frame = 0;
    while (deleted_this_frame < kMaxTextureReclaimsPerFrame &&
           !pending_deletes_.empty()) {
        batch_.delete_texture(pending_deletes_.front());
        pending_deletes_.pop_front();
        ++deleted_this_frame;
    }
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
        std::size_t inspected = 0;
        while (!queue_.empty() && inspected < kMaxCoverQueueLookupsPerFrame) {
            ++inspected;
            std::string key = std::move(queue_.front());
            queue_.pop_front();
            const auto it = covers_.find(key);
            if (it == covers_.end() || it->second.loaded) continue;
            const std::string path = it->second.path;
            const int target_pixels = it->second.target_pixels;
            const auto generation = it->second.generation;
            try {
                decode_ = std::async(std::launch::async,
                    [this, key = std::move(key), path, target_pixels, generation]() mutable {
                        DecodedCover decoded;
                        decoded.key = std::move(key);
                        decoded.generation = generation;
                        try {
                            decoded.ok = services_.load_image(path, &decoded.image);
                            if (decoded.ok) {
                                // Keep the largest dimension near the actual
                                // rendering footprint. This scaling is CPU-side
                                // on the decode worker, never in the UI frame.
                                // The 3/2 threshold avoids uploading a 960px
                                // image for a 512px tile while respecting the
                                // original Hero resolution at 2048px.
                                while (decoded.image.width > 1 &&
                                       decoded.image.height > 1 &&
                                       std::max(decoded.image.width, decoded.image.height) >
                                           target_pixels * 3 / 2)
                                    decoded.image = gfx::halve(decoded.image);
                            }
                        } catch (...) {
                            decoded.image = {};
                            decoded.ok = false; // normal retry/backoff on bad media
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
        // Avoid building and sorting a temporary vector every UI frame.
        // Evict at most two stale, completed covers per update: a bounded
        // number of GL deletes and no heap allocation in this hot path.
        for (std::size_t reclaimed = 0;
             deleted_this_frame + reclaimed < kMaxTextureReclaimsPerFrame &&
             covers_.size() > kMaxCovers * 3 / 4; ++reclaimed)
        {
            auto oldest = covers_.end();
            for (auto it = covers_.begin(); it != covers_.end(); ++it)
            {
                // Never evict in-flight decodes or the last two frames'
                // visible covers, even under a large collection pressure.
                if (!it->second.loaded || it->second.used + 2 >= frame_)
                    continue;
                if (oldest == covers_.end() ||
                    it->second.used < oldest->second.used)
                    oldest = it;
            }
            if (oldest == covers_.end())
                break;
            batch_.delete_texture(oldest->second.texture);
            covers_.erase(oldest);
        }
    }
}

} // namespace pe::ui
