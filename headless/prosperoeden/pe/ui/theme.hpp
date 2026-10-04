// ProsperoEden - Launcher colours, type sizes and motion constants.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include "pe/gfx/draw_list.hpp"

#include <algorithm>

namespace pe::ui
{

using gfx::Align;
using gfx::Color;
using gfx::Rect;

namespace theme
{

// Eden brand palette: dark neutral surfaces with the official violet/pink/blue accents.
inline const Color kBase = Color::rgb(0x090a12);
inline const Color kScrim = Color::rgb(0x05060d);
inline const Color kGlass = Color::rgb(0x151522);  // home panels
inline const Color kPanel = Color::rgb(0x10111b);  // screens and dialogs
inline const Color kPanelEdge = Color::rgb(0x58536f);
inline const Color kRow = Color::rgb(0x191a28);
inline const Color kRowEdge = Color::rgb(0x4d4965);
inline const Color kRowFocus = Color::rgb(0x2b2140);

// Keep the historic names to avoid touching every widget; values are Eden's official accents.
inline const Color kLime = Color::rgb(0xbf42f6);      // Eden violet
inline const Color kLimeDeep = Color::rgb(0x5d4aa8);  // deep violet/blue
inline const Color kLimePale = Color::rgb(0xd6a4ff);  // pale violet
inline const Color kSun = Color::rgb(0xff44c4);       // Eden pink
inline const Color kBlue = Color::rgb(0x5da5ed);      // Eden blue

// Text
inline const Color kText = Color::rgb(0xf4f2f8);
inline const Color kTitle = Color::rgb(0xffffff);
inline const Color kValue = Color::rgb(0xf0edf7);
inline const Color kBody = Color::rgb(0xdedbe8);
inline const Color kCopy = Color::rgb(0xc5c1d2);
inline const Color kMeta = Color::rgb(0xa9a5b8);
inline const Color kLabel = Color::rgb(0xb7b2c5);
inline const Color kMuted = Color::rgb(0xa19cad);
inline const Color kFaint = Color::rgb(0x7e798b);
inline const Color kWarning = Color::rgb(0xff9f9f);
inline const Color kRule = Color::rgb(0x3f3b51);

// Type sizes (Montserrat Medium)
constexpr float kDisplay = 48.0f;
constexpr float kLead = 40.0f;
constexpr float kBrand = 36.0f;
constexpr float kHeading = 32.0f;
constexpr float kClock = 28.0f;
constexpr float kText24 = 24.0f;
constexpr float kSmall = 20.0f;

// Motion (spring responsiveness in rad/s, durations in seconds)
constexpr float kFocusSpring = 20.0f;
constexpr float kCursorSpring = 26.0f;
constexpr float kScrollSpring = 16.0f;
constexpr float kScreenSeconds = 0.30f;
constexpr float kLaunchSeconds = 0.95f;

} // namespace theme

// How the launcher is shown: Settings > Accessibility.
struct Look
{
    bool large_text = false;    // small text is drawn larger
    bool high_contrast = false; // solid panels, brighter text, an outlined highlight
    bool reduce_motion = false; // nothing drifts, slides or zooms: screens fade
};
inline Look &look()
{
    static Look value;
    return value;
}
// 1 normally, 0 with reduced motion: every slide, zoom and drift is multiplied by it.
inline float motion()
{
    return look().reduce_motion ? 0.0f : 1.0f;
}
// The size text of `size` is drawn at. "Larger text" raises everything under 30 to between 26
// and 30 (26 is the least the console accessibility guidelines ask of text on a 1080p TV).
inline float text_size(float size)
{
    return look().large_text && size < 30.0f ? std::clamp(size * 1.3f, 26.0f, 30.0f) : size;
}

// The baseline that centres text of `size` in a line box of height `line` starting at `top`.
inline float baseline(float top, float line, float size)
{
    return top + line * 0.5f + size * 0.35f;
}

inline bool inside(const Rect &r, float x, float y)
{
    return x >= r.x && y >= r.y && x < r.x + r.w && y < r.y + r.h;
}

} // namespace pe::ui
