// ProsperoEden - The launcher's textures: its own art and lazily loaded covers.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include "pe/gfx/gl_batch.hpp"
#include "pe/ui/services.hpp"

#include <cstdint>
#include <deque>
#include <future>
#include <string>
#include <unordered_map>
#include <vector>

namespace pe::ui
{

// A cover as far as it is known.
struct Cover
{
    std::uint32_t texture = 0; // 0 while it is queued, and when there is none
    float age = 0.0f;          // seconds since it loaded, for the fade-in
    bool missing = false;      // the game has no cover, or its file cannot be read
    float aspect = 1.0f;       // loaded source width / height, used for CSS-like cover cropping
};

// Owns every GL texture of the launcher. Decoding and geometric scaling are
// off-thread; the UI thread uploads at most one ready texture per frame.
// Distinct display-size buckets avoid uploading 1080p artwork for small tiles.
// The least recently drawn texture variants are discarded.
class Textures
{
  public:
    Textures(gfx::GlBatch &batch, Services &services) : batch_(batch), services_(services) {}
    Textures(const Textures &) = delete;
    Textures &operator=(const Textures &) = delete;
    ~Textures();

    // Launcher background, brand and controller art. The background is generated from Encore art.
    bool load_art(const std::string &directory);
    // Deletes every texture; the GL context must still be current.
    void release();

    std::uint32_t backdrop() const
    {
        return backdrop_;
    }
    std::uint32_t backdrop_blur() const
    {
        return backdrop_blur_;
    }
    std::uint32_t brand() const
    {
        return brand_;
    }
    // A controller in white on transparent (0 when the picture is missing).
    std::uint32_t controller() const
    {
        return controller_;
    }
    // Immutable printed inserts for metadata-composed Switch jackets.
    // Loaded with launcher art, never fetched in a frame.
    std::uint32_t switch_logo() const { return switch_logo_; }
    std::uint32_t switch_rear_footer() const { return switch_rear_footer_; }

    // The cover drawn `size` virtual pixels wide. Queues it on first use.
    Cover cover(const std::string &path, float size);
    // Schedules at most one background image decode and uploads at most one
    // completed texture per frame. Never does file I/O or JPEG/TGA decode
    // on the input/navigation/render thread.
    void pump(float dt, int budget = 2);
    // Called only when Nlib atomically replaces an image with the same path.
    void invalidate(const std::string &path);
    // Compose one offline artwork sleeve with the REAL C++/OpenGL UI painter.
    // Only called once per missing case face after cached input images load.
    // Returns 0 if this GL context cannot render to a texture; caller draws
    // the same opaque paper base, never a raw front screenshot on the back.
    std::uint32_t render_case_page(const gfx::DrawList& drawing,
                                   const gfx::Font* font,
                                   std::uint32_t font_texture,
                                   int width, int height);
    void clear_case_pages();
    // Output pixels per virtual pixel: picks how much detail a cover needs.
    void set_output_scale(float scale)
    {
        output_scale_ = scale;
    }

  private:
    struct Entry
    {
        std::uint32_t texture = 0;
        float age = 0.0f;
        bool loaded = false; // false: queued or decoding
        std::uint64_t generation = 0;
        unsigned failed_loads = 0; // bounded retry backoff when async Nlib media arrive
        std::uint64_t used = 0;
        std::string path;
        int target_pixels = 64; // desired max image dimension, quantized to power of two
        float aspect = 1.0f;
    };

    struct DecodedCover {
        std::string key;
        std::uint64_t generation = 0;
        gfx::Image image;
        bool ok = false;
    };
    std::future<DecodedCover> decode_;
    std::uint32_t create(const gfx::Image &image);

    gfx::GlBatch &batch_;
    Services &services_;
    // At most two short-lived GPU pages for the current launch transition.
    std::vector<std::uint32_t> case_pages_;
    std::uint32_t backdrop_ = 0;
    std::uint32_t backdrop_blur_ = 0;
    std::uint32_t brand_ = 0;
    std::uint32_t controller_ = 0;
    std::uint32_t switch_logo_ = 0;
    std::uint32_t switch_rear_footer_ = 0;
    std::unordered_map<std::string, Entry> covers_;
    std::deque<std::string> queue_; // O(1) pop_front during frame updates
    std::deque<std::uint32_t> pending_deletes_; // invalidated GPU IDs, amortized in pump()
    std::uint64_t frame_ = 0;
    std::uint64_t next_generation_ = 0;
    float output_scale_ = 1.0f;
};

} // namespace pe::ui
