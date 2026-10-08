// ProsperoEden - Launcher building blocks: backdrop, panels, plates, lists and hints.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include "pe/ui/widgets.hpp"

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

namespace pe::ui
{

namespace
{

FitReport fit_report = nullptr;

// A text colour as shown: with high contrast, greys go most of the way to white and accents a
// little, and faded text is less faded.
Color text_ink(Color color)
{
    if (!look().high_contrast)
        return color;
    const float high = std::max({color.r, color.g, color.b});
    const float low = std::min({color.r, color.g, color.b});
    const float lift = high - low > 0.24f ? 0.25f : 0.70f;
    return {color.r + (1.0f - color.r) * lift, color.g + (1.0f - color.g) * lift,
            color.b + (1.0f - color.b) * lift, 1.0f - (1.0f - color.a) * 0.5f};
}

// Draws at exactly `drawn` on the line laid out for text of `size`.
float draw_text(Canvas &c, std::string_view value, float x, float baseline, float size, float drawn,
                Color color, Align align, float tracking)
{
    gfx::TextStyle style;
    style.size = drawn;
    style.color = text_ink(color);
    style.align = align;
    style.tracking = tracking;
    return c.list.text(*c.fonts.font, c.fonts.texture, value, x, baseline + (drawn - size) * 0.35f,
                       style);
}
const Color kWhite{1.0f, 1.0f, 1.0f, 1.0f};
const Color kBlack{0.0f, 0.0f, 0.0f, 1.0f};


} // namespace

// ---------------------------------------------------------------- backdrop

void Backdrop::update(float dt)
{
    // With reduced motion the art stands still.
    time_ += dt * motion();
}

Rect Backdrop::art() const
{
    // The art is 2048x1152 around the 1920x1080 screen: room to drift.
    const float dx = 24.0f * std::sin(time_ * 0.050f);
    const float dy = 11.0f * std::sin(time_ * 0.037f + 1.3f);
    return {-64.0f + dx, -36.0f + dy, 2048.0f, 1152.0f};
}

Rect Backdrop::uv(const Rect &r) const
{
    const Rect a = art();
    return {(r.x - a.x) / a.w, (r.y - a.y) / a.h, r.w / a.w, r.h / a.h};
}

void Backdrop::draw(gfx::DrawList &list, const Textures &textures, float dim) const
{
    const Rect screen{0.0f, 0.0f, 1920.0f, 1080.0f};
    list.rounded_rect(screen, 0.0f, theme::kBase);

    // A single Eden art direction across the PS5 shell, launcher and game-loading transition.
    // The oversized crop drifts by only a few pixels, giving the shell depth without making
    // navigation feel busy.
    if (textures.backdrop() != 0 && !look().high_contrast)
    {
        const Rect a = art();
        list.image(textures.backdrop(), a, {0.0f, 0.0f, 1.0f, 1.0f}, kWhite.with_alpha(0.72f));
        list.gradient_rect(screen, 0.0f, Color::rgb(0x07070d, 0.20f), Color::rgb(0x05040b, 0.78f));
    }

    if (!look().high_contrast)
    {
        const float drift = motion();
        const float violet_x = 330.0f + 42.0f * std::sin(time_ * 0.08f) * drift;
        const float pink_x = 1570.0f + 50.0f * std::sin(time_ * 0.065f + 1.8f) * drift;
        const float blue_y = 900.0f + 30.0f * std::sin(time_ * 0.05f + 0.7f) * drift;
        list.shadow({violet_x - 280.0f, 78.0f, 560.0f, 560.0f}, 280.0f, 320.0f,
                    theme::kLime.with_alpha(0.13f));
        list.shadow({pink_x - 260.0f, 120.0f, 520.0f, 520.0f}, 260.0f, 310.0f,
                    theme::kSun.with_alpha(0.09f));
        list.shadow({710.0f, blue_y - 190.0f, 500.0f, 380.0f}, 190.0f, 270.0f,
                    theme::kBlue.with_alpha(0.065f));
    }

    if (look().high_contrast)
        dim = std::max(dim, 0.55f);
    if (dim > 0.0f)
        list.rounded_rect(screen, 0.0f, theme::kScrim.with_alpha(dim));
}

// ---------------------------------------------------------------- text

float text(Canvas &c, std::string_view value, float x, float baseline, float size, Color color,
           Align align, float tracking)
{
    return draw_text(c, value, x, baseline, size, text_size(size), color, align, tracking);
}

float text_width(Canvas &c, std::string_view value, float size, float tracking)
{
    return c.fonts.font->measure(value, text_size(size), tracking);
}

float text_fit(Canvas &c, std::string_view value, float x, float baseline, float size, Color color,
               float max_width, Align align)
{
    const float drawn = text_size(size);
    return draw_text(c, c.fonts.font->fit(value, drawn, max_width), x, baseline, size, drawn, color,
                     align, 0.0f);
}

void set_fit_report(FitReport report)
{
    fit_report = report;
}

float text_shrink(Canvas &c, std::string_view value, float x, float baseline, float size,
                  Color color, float max_width, Align align, float tracking, float least)
{
    const gfx::Font &font = *c.fonts.font;
    const float drawn = text_size(size);
    const float width = font.measure(value, drawn, tracking);
    if (width <= max_width)
        return draw_text(c, value, x, baseline, size, drawn, color, align, tracking);
    // Larger text gives its extra size back before anything is cut.
    const float scale = std::max(least * size / drawn, max_width / width);
    if (fit_report != nullptr)
        fit_report(value, scale, width * scale > max_width + 0.5f);
    return draw_text(c, font.fit(value, drawn * scale, max_width + 0.5f, tracking * scale), x,
                     baseline, size, drawn * scale, color, align, tracking * scale);
}

void text_block(Canvas &c, std::string_view value, float x, float first_baseline, float size,
                float line_height, Color color, float max_width, int max_lines, float least)
{
    const gfx::Font &font = *c.fonts.font;
    const float full = text_size(size);
    float drawn = full;
    std::vector<std::string> lines = font.wrap(value, drawn, max_width);
    // A step smaller at a time, until the text fits its lines or the letters are as small as
    // allowed.
    // (Larger text gives its extra size back before anything is cut.)
    const float smallest = size * least;
    while (static_cast<int>(lines.size()) > max_lines && drawn > smallest + 0.01f)
    {
        drawn = std::max(smallest, drawn * 0.94f);
        lines = font.wrap(value, drawn, max_width);
    }
    if (fit_report != nullptr && drawn < full)
        fit_report(value, drawn / full, static_cast<int>(lines.size()) > max_lines);
    const int count = std::min(static_cast<int>(lines.size()), max_lines);
    for (int line = 0; line < count; ++line)
    {
        const bool cut = line == count - 1 && static_cast<int>(lines.size()) > max_lines;
        // The last line that fits swallows the next one, so its ellipsis shows more follows.
        const std::string content =
            !cut ? lines[line] :
            lines[line] + (gfx::joins_without_space(lines[line], lines[line + 1]) ? "" : " ") + lines[line + 1];
        draw_text(c, font.fit(content, drawn, max_width), x,
                  first_baseline + line_height * static_cast<float>(line), size, drawn, color,
                  Align::left, 0.0f);
    }
}

namespace
{

// The warning mark with its left edge at x, centred on the line of text of `size` at `baseline`.
// Returns the room it takes, the gap to the text included.
float warning_mark(Canvas &c, float x, float baseline, float size, Color color, bool draw = true)
{
    const float drawn = text_size(size);
    const float radius = drawn * 0.46f;
    if (draw)
    {
        const Color ink = text_ink(color);
        const float cx = x + radius;
        const float cy = baseline - size * 0.35f;
        c.list.ring(cx, cy, radius - 0.5f, drawn * 0.085f, ink);
        c.list.line(cx, cy - radius * 0.50f, cx, cy + radius * 0.10f, drawn * 0.11f, ink);
        c.list.circle(cx, cy + radius * 0.48f, drawn * 0.065f, ink);
    }
    return radius * 2.0f + drawn * 0.42f;
}

} // namespace

float notice(Canvas &c, std::string_view value, float x, float baseline, float size, Color color,
             float max_width, bool warning, Align align)
{
    if (!warning || value.empty())
        return text_shrink(c, value, x, baseline, size, color, max_width, align);
    const float mark = warning_mark(c, x, baseline, size, color, false);
    if (align == Align::right)
    {
        const float width = text_shrink(c, value, x, baseline, size, color, max_width - mark, align);
        warning_mark(c, x - width - mark, baseline, size, color);
        return width + mark;
    }
    warning_mark(c, x, baseline, size, color);
    return mark + text_shrink(c, value, x + mark, baseline, size, color, max_width - mark, align);
}

void notice_block(Canvas &c, std::string_view value, float x, float first_baseline, float size,
                  float line_height, Color color, float max_width, int max_lines, bool warning)
{
    const float mark = warning && !value.empty() ? warning_mark(c, x, first_baseline, size, color) : 0.0f;
    text_block(c, value, x + mark, first_baseline, size, line_height, color, max_width - mark,
               max_lines, kShrink);
}

float value_column(Canvas &c, std::initializer_list<std::string_view> labels, float left,
                   float column, float size, float tracking)
{
    float widest = 0.0f;
    for (const std::string_view label : labels)
        widest = std::max(widest, text_width(c, label, size, tracking));
    return std::max(column, left + widest + 24.0f);
}

// ---------------------------------------------------------------- surfaces

void glass(Canvas &c, const Rect &r, float radius, Color tint, Color edge, float shadow)
{
    if (shadow > 0.0f) {
        // Two-layer elevation: a broad neutral shadow grounds the glass on the artwork, while a
        // very faint Eden-violet halo gives the premium console-card separation of the mockup.
        c.list.shadow({r.x + 8.0f, r.y + 22.0f, r.w - 16.0f, r.h - 10.0f}, radius, 54.0f,
                      kBlack.with_alpha(0.48f * shadow));
        c.list.shadow({r.x - 4.0f, r.y - 2.0f, r.w + 8.0f, r.h + 8.0f}, radius + 4.0f, 36.0f,
                      theme::kLimeDeep.with_alpha(0.075f * shadow));
    }
    if (look().high_contrast)
    {
        // A solid panel with a clear edge: nothing of the art shows through the text.
        c.list.bordered_rect(r, radius, Color::rgb(0x0b0c14), 2.0f, Color::rgb(0xc5c1d2));
        return;
    }
    if (c.textures.backdrop_blur() != 0)
        c.list.rounded_image(c.textures.backdrop_blur(), r, c.backdrop.uv(r), radius, kWhite);
    c.list.bordered_rect(r, radius, tint, 1.15f, edge);
    // Inner hairline gives the glass the crisp double-edge visible in the reference UI without
    // turning every panel into a thick neon frame.
    if (r.w > 8.0f && r.h > 8.0f)
        c.list.bordered_rect({r.x + 2.0f, r.y + 2.0f, r.w - 4.0f, r.h - 4.0f},
                             std::max(2.0f, radius - 2.0f), kWhite.with_alpha(0.0f), 0.7f,
                             kWhite.with_alpha(0.055f));
    // Light catches the top edge.
    const float sheen = std::min(r.h * 0.45f, 150.0f);
    c.list.gradient_rect({r.x + 1.0f, r.y + 1.0f, r.w - 2.0f, sheen}, radius,
                         kWhite.with_alpha(0.045f), kWhite.with_alpha(0.0f));
}

const Plate kRowPlate{20.0f,
                      theme::kRow.with_alpha(0.82f),
                      theme::kRowEdge.with_alpha(0.42f),
                      theme::kRowFocus.with_alpha(0.92f),
                      theme::kFocusBlue.with_alpha(0.36f),
                      theme::kLimeDeep.with_alpha(0.54f),
                      theme::kFocusCore.with_alpha(0.82f)};
const Plate kListPlate{20.0f,
                       Color::rgb(0x191a28, 0.91f),
                       Color::rgb(0x5b5572, 0.47f),
                       Color::rgb(0x2b2140, 0.95f),
                       theme::kLime.with_alpha(0.44f),
                       theme::kLimeDeep.with_alpha(0.50f),
                       theme::kLime.with_alpha(0.63f)};
const Plate kButtonPlate{22.0f,
                         Color::rgb(0xf0edf7, 0.085f),
                         kWhite.with_alpha(0.16f),
                         Color::rgb(0x1d172b, 0.68f),
                         theme::kFocusBlue.with_alpha(0.35f),
                         theme::kLimeDeep.with_alpha(0.60f),
                         theme::kFocusCore.with_alpha(0.90f)};
const Plate kTilePlate{22.0f,
                       Color::rgb(0xf4f2f8, 0.045f),
                       kWhite.with_alpha(0.105f),
                       Color::rgb(0x1b1428, 0.50f),
                       theme::kFocusBlue.with_alpha(0.30f),
                       theme::kLimeDeep.with_alpha(0.50f),
                       theme::kFocusCore.with_alpha(0.86f)};
const Plate kNavPlate{20.0f,
                      kWhite.with_alpha(0.0f),
                      kWhite.with_alpha(0.0f),
                      Color::rgb(0x241833, 0.34f),
                      theme::kFocusBlue.with_alpha(0.28f),
                      theme::kLimeDeep.with_alpha(0.38f),
                      theme::kFocusCore.with_alpha(0.82f)};

void plate_rest(Canvas &c, const Plate &style, const Rect &r)
{
    if (style.fill.a <= 0.0f && style.edge.a <= 0.0f)
        return;
    if (look().high_contrast)
        c.list.bordered_rect(r, style.radius, Color::rgb(0x12131d), 1.5f, Color::rgb(0xa9a5b8));
    else
        c.list.bordered_rect(r, style.radius, style.fill, 1.0f, style.edge);
}

void plate_focus(Canvas &c, const Plate &style, const Rect &r, float amount)
{
    if (amount <= 0.001f)
        return;
    if (look().high_contrast)
    {
        // The highlight is a dark fill inside a bright outline: it does not rest on colour.
        c.list.bordered_rect(r, style.radius, Color::rgb(0x2a1d3a, amount), 3.0f,
                             Color::rgb(0xd6a4ff, amount));
        return;
    }
    // Eden Encore luminous focus: pink/violet dual halo, crisp outer edge and
    // a dark-to-plum translucent sweep. Unlike a solid focused rectangle,
    // the cover artwork remains fully visible under the selected tile.
    const float breathe = 0.88f + 0.12f * std::sin(c.time * 2.0f * motion());
    const bool artwork_plate = &style == &kTilePlate;
    const float fill_strength = artwork_plate ? 0.24f : 0.82f;
    const float gradient_strength = artwork_plate ? 0.28f : 0.70f;
    c.list.shadow({r.x - 13.0f, r.y - 10.0f, r.w + 26.0f, r.h + 24.0f},
                  style.radius + 13.0f, 43.0f,
                  theme::kLime.with_alpha(0.30f * amount * breathe));
    c.list.shadow({r.x - 5.0f, r.y - 5.0f, r.w + 10.0f, r.h + 10.0f},
                  style.radius + 6.0f, 19.0f,
                  theme::kSun.with_alpha(0.29f * amount * breathe));
    if (style.focus_base.a > 0.0f)
        c.list.rounded_rect(r, style.radius,
                            style.focus_base.with_alpha(fill_strength * amount));
    c.list.hgradient_rect(r, style.radius,
                          style.focus_left.with_alpha(gradient_strength * amount),
                          style.focus_right.with_alpha(0.34f * amount),
                          2.5f, theme::kFocusCore.with_alpha(0.95f * amount));
    c.list.bordered_rect({r.x + 2.3f, r.y + 2.3f, r.w - 4.6f, r.h - 4.6f},
                         std::max(1.0f, style.radius - 2.3f),
                         kWhite.with_alpha(0.0f), 0.9f,
                         theme::kLimePale.with_alpha(0.30f * amount));
    // The top rim catches the neon pink and fades into the darkened right side.
    c.list.hgradient_rect({r.x + style.radius, r.y + 1.2f,
                           std::max(0.0f, r.w - style.radius * 2.0f), 2.2f},
                          1.1f,
                          theme::kSun.with_alpha(0.78f * amount),
                          theme::kLimePale.with_alpha(0.12f * amount));
}

void plate(Canvas &c, const Plate &style, const Rect &r, float focus)
{
    plate_rest(c, style, r);
    plate_focus(c, style, r, focus);
}

void cover(Canvas &c, const std::string &path, const Rect &r, float radius, float shadow)
{
    if (shadow > 0.0f)
        c.list.shadow({r.x + 3.0f, r.y + 10.0f * shadow, r.w - 6.0f, r.h - 4.0f}, radius,
                      24.0f * shadow, kBlack.with_alpha(0.5f));
    const Cover image = c.textures.cover(path, r.w);
    const float fade = image.texture != 0 ? tween::cubic_out(image.age / 0.22f) : 0.0f;
    if (fade < 1.0f)
    {
        // A dark tile until the cover is ready; the app icon when the game has none.
        c.list.gradient_rect(r, radius, Color::rgb(0x191a28), Color::rgb(0x10111b));
        // An absent game image uses a neutral gradient, never the Eden logo.
    }
    if (image.texture != 0)
    {
        // Aspect-safe "contain" for standalone icons and logos; never stretch
        // them. Artwork tiles and banners use the separate object-fit COVER
        // path in cover_crop() and the Home hero respectively.
        Rect fitted = r;
        const float source = std::max(0.01f, image.aspect);
        const float target = std::max(0.01f, r.w / std::max(r.h, 1.0f));
        if (source > target) {
            fitted.h = r.w / source;
            fitted.y += (r.h - fitted.h) * 0.5f;
        } else if (source < target) {
            fitted.w = r.h * source;
            fitted.x += (r.w - fitted.w) * 0.5f;
        }
        c.list.rounded_image(image.texture, fitted, {0.0f, 0.0f, 1.0f, 1.0f},
                             std::min(radius, std::min(fitted.w, fitted.h) * 0.5f),
                             kWhite.with_alpha(fade));
    }
    c.list.bordered_rect(r, radius, kWhite.with_alpha(0.0f), 1.0f, kWhite.with_alpha(0.10f));
}

void cover_crop(Canvas &c, const std::string &path, const Rect &r, float radius, float shadow)
{
    if (shadow > 0.0f)
        c.list.shadow({r.x + 3.0f, r.y + 10.0f * shadow, r.w - 6.0f, r.h - 4.0f}, radius,
                      24.0f * shadow, kBlack.with_alpha(0.5f));
    const Cover image = c.textures.cover(path, std::max(r.w, r.h));
    const float fade = image.texture != 0 ? tween::cubic_out(image.age / 0.22f) : 0.0f;
    if (fade < 1.0f)
    {
        c.list.gradient_rect(r, radius, Color::rgb(0x191a28), Color::rgb(0x10111b));
        // An absent game image uses a neutral gradient, never the Eden logo.
    }
    if (image.texture != 0)
    {
        const float source = std::max(0.01f, image.aspect);
        const float target = std::max(0.01f, r.w / std::max(1.0f, r.h));
        Rect uv{0.0f, 0.0f, 1.0f, 1.0f};
        if (source > target)
        {
            uv.w = target / source;
            uv.x = (1.0f - uv.w) * 0.5f;
        }
        else if (source < target)
        {
            uv.h = source / target;
            uv.y = (1.0f - uv.h) * 0.5f;
        }
        c.list.rounded_image(image.texture, r, uv, radius, kWhite.with_alpha(fade));
    }
    c.list.bordered_rect(r, radius, kWhite.with_alpha(0.0f), 1.0f, kWhite.with_alpha(0.12f));
}

void controller_icon(Canvas &c, const Rect &r, float lit)
{
    const std::uint32_t picture = c.textures.controller();
    if (picture == 0)
        return;
    const float u = r.w / 72.0f; // the picture is drawn in a 72x50 box
    if (lit > 0.01f)
    {
        // The light under a connected controller, breathing slowly.
        const float breath = 0.85f + 0.15f * std::sin(c.time * 1.7f * motion() + r.x * 0.01f);
        c.list.shadow({r.x + 8.0f * u, r.y + 8.0f * u, r.w - 16.0f * u, r.h - 14.0f * u},
                      14.0f * u, 22.0f * u, theme::kLime.with_alpha(0.26f * lit * breath));
    }
    c.list.image(picture, r, {0.0f, 0.0f, 1.0f, 1.0f},
                 gfx::mix(kWhite.with_alpha(0.16f), Color::rgb(0xf4f2f8), lit));
    if (lit > 0.01f)
    {
        // The light bar on either side of the touchpad.
        const Color bar = theme::kLime.with_alpha(lit);
        for (const float x : {26.0f, 46.0f})
            c.list.line(r.x + x * u, r.y + 10.0f * u, r.x + x * u, r.y + 19.0f * u, 1.4f * u, bar);
    }
}

void toggle(Canvas &c, float right, float cy, float position)
{
    constexpr float kWidth = 64.0f;
    constexpr float kHeight = 34.0f;
    const Rect track{right - kWidth, cy - kHeight * 0.5f, kWidth, kHeight};
    c.list.bordered_rect(track, kHeight * 0.5f, Color::rgb(0x252333, 0.95f), 1.0f,
                         theme::kRowEdge.with_alpha(0.7f));
    c.list.hgradient_rect(track, kHeight * 0.5f, theme::kLime.with_alpha(0.95f * position),
                          Color::rgb(0xbf42f6, 0.95f * position));
    const float knob_x = track.x + kHeight * 0.5f + (kWidth - kHeight) * position;
    c.list.shadow({knob_x - 12.0f, cy - 10.0f, 24.0f, 24.0f}, 12.0f, 6.0f, kBlack.with_alpha(0.35f));
    c.list.circle(knob_x, cy, 12.5f, gfx::mix(theme::kCopy, theme::kTitle, position));
}

void level_bar(Canvas &c, float right, float cy, float width, float level, float focus)
{
    constexpr float kHeight = 8.0f;
    const Rect track{right - width, cy - kHeight * 0.5f, width, kHeight};
    c.list.rounded_rect(track, kHeight * 0.5f, Color::rgb(0x302b42, 0.95f));
    const float filled = std::max(kHeight, width * std::clamp(level, 0.0f, 1.0f));
    if (level > 0.0f)
        c.list.hgradient_rect({track.x, track.y, filled, kHeight}, kHeight * 0.5f, theme::kLimeDeep,
                              theme::kLime);
    const float knob = 7.0f + 3.0f * focus;
    c.list.shadow({track.x + filled - knob, cy - knob + 2.0f, knob * 2.0f, knob * 2.0f}, knob, 5.0f,
                  kBlack.with_alpha(0.35f));
    c.list.circle(track.x + (level > 0.0f ? filled : 0.0f), cy, knob, theme::kTitle);
}

float chooser(Canvas &c, std::string_view value, float right, float baseline, float focus,
              Color color)
{
    const float size = theme::kText24;
    const float arrow = 26.0f * focus; // room the chevrons take when focused
    const float width = text(c, value, right - arrow, baseline, size, color, Align::right);
    if (focus <= 0.01f)
        return width;
    const float cy = baseline - size * 0.35f;
    const Color ink = theme::kLimePale.with_alpha(focus);
    const float rx = right - 4.0f;
    c.list.line(rx - 7.0f, cy - 8.0f, rx, cy, 2.2f, ink);
    c.list.line(rx, cy, rx - 7.0f, cy + 8.0f, 2.2f, ink);
    const float lx = right - arrow - width - 16.0f;
    c.list.line(lx + 7.0f, cy - 8.0f, lx, cy, 2.2f, ink);
    c.list.line(lx, cy, lx + 7.0f, cy + 8.0f, 2.2f, ink);
    return width + arrow + 16.0f;
}

// ---------------------------------------------------------------- controller hints

float pad_width(Pad button, float size)
{
    switch (button)
    {
    case Pad::none:
        return 0.0f;
    case Pad::l1:
    case Pad::r1:
    case Pad::l2:
    case Pad::r2:
        return size * 1.45f;
    case Pad::l3:
    case Pad::r3:
    case Pad::options:
    case Pad::create:
        return size * 1.25f;
    case Pad::touchpad:
        return size * 1.60f;
    default:
        return size;
    }
}

void draw_pad(Canvas &c, Pad button, float x, float cy, float size, float alpha)
{
    const float width = pad_width(button, size);
    const float cx = x + width * 0.5f;
    const float half = size * 0.5f;
    const bool bold = look().high_contrast;
    const Color ring = theme::kText.with_alpha((bold ? 0.88f : 0.34f) * alpha);
    const Color ink = theme::kTitle.with_alpha((bold ? 1.0f : 0.96f) * alpha);
    const auto face_ink = [&](Pad value) {
        // PlayStation-style face-button colours used consistently in every Encore footer/dialog.
        // The dark keycap remains neutral so the symbol itself is the quick visual cue at TV distance.
        switch (value) {
        case Pad::cross: return Color::rgb(0x55b7ff).with_alpha(alpha);
        case Pad::circle: return Color::rgb(0xff6b8a).with_alpha(alpha);
        case Pad::square: return Color::rgb(0xe987ff).with_alpha(alpha);
        case Pad::triangle: return Color::rgb(0x66e6a6).with_alpha(alpha);
        default: return ink;
        }
    };
    const Color dim = theme::kText.with_alpha((bold ? 0.48f : 0.28f) * alpha);
    const float stroke = size * 0.082f;
    // PS5-like input chip: dark circular keycap, hairline rim and a tiny violet underglow.
    if (button == Pad::cross || button == Pad::circle || button == Pad::square ||
        button == Pad::triangle)
    {
        c.list.shadow({cx - half + 2.0f, cy - half + 3.0f, size - 4.0f, size - 4.0f},
                      half, size * 0.48f, theme::kLime.with_alpha(0.11f * alpha));
        c.list.circle(cx, cy, half, theme::kPanel.with_alpha(0.88f * alpha));
        c.list.ring(cx, cy, half - 0.5f, 1.3f, ring);
    }
    switch (button)
    {
    case Pad::none:
        return;
    case Pad::cross:
    {
        const float d = size * 0.17f;
        c.list.ring(cx, cy, half - 0.5f, 1.6f, ring);
        const Color symbol = face_ink(button);
        c.list.line(cx - d, cy - d, cx + d, cy + d, stroke, symbol);
        c.list.line(cx - d, cy + d, cx + d, cy - d, stroke, symbol);
        return;
    }
    case Pad::circle:
        c.list.ring(cx, cy, half - 0.5f, 1.6f, ring);
        c.list.ring(cx, cy, size * 0.21f, stroke, face_ink(button));
        return;
    case Pad::square:
    {
        const float side = size * 0.36f;
        c.list.ring(cx, cy, half - 0.5f, 1.6f, ring);
        const Color symbol = face_ink(button);
        c.list.bordered_rect({cx - side * 0.5f, cy - side * 0.5f, side, side}, 1.5f,
                             symbol.with_alpha(0.0f), stroke, symbol);
        return;
    }
    case Pad::triangle:
    {
        const float w = size * 0.46f;
        const float h = size * 0.40f;
        c.list.ring(cx, cy, half - 0.5f, 1.6f, ring);
        c.list.triangle({cx - w * 0.5f, cy - h * 0.60f, w, h}, face_ink(button), stroke);
        return;
    }
    case Pad::dpad:
    case Pad::updown:
    case Pad::leftright:
    {
        const float arm = size * 0.36f;
        const float thick = size * 0.26f;
        const Color vertical = button == Pad::leftright ? dim : ink;
        const Color horizontal = button == Pad::updown ? dim : ink;
        c.list.rounded_rect({cx - arm, cy - thick * 0.5f, arm * 2.0f, thick}, thick * 0.28f,
                            horizontal);
        c.list.rounded_rect({cx - thick * 0.5f, cy - arm, thick, arm * 2.0f}, thick * 0.28f,
                            vertical);
        if (button != Pad::dpad)
        {
            // Redraw the bright arm over the crossing so it reads as one piece.
            if (button == Pad::updown)
                c.list.rounded_rect({cx - thick * 0.5f, cy - arm, thick, arm * 2.0f},
                                    thick * 0.28f, ink);
            else
                c.list.rounded_rect({cx - arm, cy - thick * 0.5f, arm * 2.0f, thick},
                                    thick * 0.28f, ink);
        }
        return;
    }
    case Pad::l1:
    case Pad::r1:
    case Pad::l2:
    case Pad::r2:
    {
        const float height = size * 0.80f;
        c.list.bordered_rect({x, cy - height * 0.5f, width, height}, height * 0.30f,
                             ink.with_alpha(0.0f), 1.6f, ring);
        const char* label = button == Pad::l1 ? "L1" : button == Pad::r1 ? "R1" :
                            button == Pad::l2 ? "L2" : "R2";
        draw_text(c, label, cx, cy + size * 0.17f, size * 0.48f, size * 0.48f, ink,
                  Align::center, 0.0f);
        return;
    }
    case Pad::l3:
    case Pad::r3:
    {
        c.list.circle(cx, cy, half * 0.76f, theme::kPanel.with_alpha(0.88f * alpha));
        c.list.ring(cx, cy, half * 0.76f, 1.5f, ring);
        draw_text(c, button == Pad::l3 ? "L3" : "R3", cx, cy + size * 0.15f, size * 0.42f,
                  size * 0.42f, ink, Align::center, 0.0f);
        return;
    }
    case Pad::options:
    case Pad::create:
    {
        const float h = size * 0.72f;
        c.list.bordered_rect({x, cy - h * 0.5f, width, h}, h * 0.30f,
                             theme::kPanel.with_alpha(0.72f * alpha), 1.4f, ring);
        const float line_w = size * 0.34f;
        const float dx = button == Pad::options ? size * 0.05f : -size * 0.05f;
        for (int i = -1; i <= 1; ++i)
            c.list.line(cx - line_w * 0.5f + dx, cy + float(i) * size * 0.14f,
                        cx + line_w * 0.5f + dx, cy + float(i) * size * 0.14f,
                        std::max(1.2f, stroke * 0.55f), ink);
        if (button == Pad::create)
            c.list.line(cx - size * 0.28f, cy - size * 0.22f, cx - size * 0.28f,
                        cy + size * 0.22f, std::max(1.2f, stroke * 0.55f), ink);
        return;
    }
    case Pad::touchpad:
    {
        const float h = size * 0.72f;
        c.list.bordered_rect({x, cy - h * 0.5f, width, h}, h * 0.18f,
                             theme::kPanel.with_alpha(0.72f * alpha), 1.5f, ring);
        c.list.line(x + width * 0.20f, cy - h * 0.22f, x + width * 0.80f, cy - h * 0.22f,
                    1.2f, dim);
        return;
    }
    }
}

float draw_hints(Canvas &c, const Hint *hints, int count, float x, float cy, Color color,
                 float max_width)
{
    constexpr float kSize = 28.0f;
    constexpr float kIconGap = 10.0f;
    constexpr float kPairGap = 6.0f;
    constexpr float kItemGap = 34.0f;
    // Laid out once to measure, once to draw.
    const auto run = [&](bool draw)
    {
        float cursor = x;
        for (int i = 0; i < count; ++i)
        {
            const Hint &hint = hints[i];
            if (draw)
                draw_pad(c, hint.button, cursor, cy, kSize);
            cursor += pad_width(hint.button, kSize);
            if (hint.second != Pad::none)
            {
                cursor += kPairGap;
                if (draw)
                    draw_pad(c, hint.second, cursor, cy, kSize);
                cursor += pad_width(hint.second, kSize);
            }
            cursor += kIconGap;
            cursor += draw ? text(c, tr(hint.label), cursor, cy + theme::kSmall * 0.35f,
                                  theme::kSmall, color) :
                             text_width(c, tr(hint.label), theme::kSmall);
            if (i + 1 < count)
                cursor += kItemGap;
        }
        return cursor - x;
    };
    const float width = run(false);
    if (max_width <= 0.0f || width <= max_width)
        return run(true);
    const float scale = max_width / width;
    c.list.push_transform(scale, x, cy, 0.0f, 0.0f);
    run(true);
    c.list.pop_transform();
    return max_width;
}

// ---------------------------------------------------------------- lists

std::string list_position(int selected, int count)
{
    return fill(tr("{0} OF {1}"), {std::to_string(selected), std::to_string(count)});
}

void ListView::follow()
{
    const int max_top = std::max(0, count - visible);
    if (selected < top_)
        top_ = selected;
    if (selected > top_ + visible - 1)
        top_ = selected - (visible - 1);
    top_ = std::clamp(top_, 0, max_top);
    scroll_.target = static_cast<float>(top_) * pitch;
    cursor_.target = static_cast<float>(selected) * pitch;
}

void ListView::reset(int new_count, int new_selected)
{
    count = std::max(0, new_count);
    selected = std::clamp(new_selected, 0, std::max(0, count - 1));
    // Open with the selection a few rows down when the list is long enough.
    top_ = std::max(0, selected - visible / 2);
    follow();
    scroll_.snap(scroll_.target);
    cursor_.snap(cursor_.target);
}

bool ListView::move(int delta)
{
    if (count <= 0)
        return false;
    int next = selected + delta;
    if (wrap)
        next = (next % count + count) % count;
    else
        next = std::clamp(next, 0, count - 1);
    if (next == selected)
        return false;
    selected = next;
    follow();
    return true;
}

bool ListView::page(int delta)
{
    if (count <= 0)
        return false;
    const int next = std::clamp(selected + delta * visible, 0, count - 1);
    if (next == selected)
        return false;
    selected = next;
    follow();
    return true;
}

void ListView::update(float dt)
{
    scroll_.update(dt, theme::kScrollSpring);
    cursor_.update(dt, theme::kCursorSpring);
}

int ListView::first_row() const
{
    return std::max(0, static_cast<int>(std::floor(scroll_.value / pitch)));
}

int ListView::last_row() const
{
    return std::min(count - 1, static_cast<int>(std::floor(scroll_.value / pitch)) + visible);
}

float ListView::row_alpha(int row, float row_height) const
{
    const float y = static_cast<float>(row) * pitch - scroll_.value;
    const float window = static_cast<float>(visible - 1) * pitch + row_height;
    const float above = tween::clamp01((y + row_height) / row_height);
    const float below = tween::clamp01((window - y) / row_height);
    return std::min(above, below);
}

float ListView::thumb() const
{
    const float range = static_cast<float>(std::max(1, count - visible)) * pitch;
    return tween::clamp01(scroll_.value / range);
}

void scrollbar(Canvas &c, const ListView &view, float x, float y, float height)
{
    if (view.count <= view.visible)
        return;
    c.list.rounded_rect({x, y, 10.0f, height}, 5.0f, Color::rgb(0x514b68, 0.53f));
    const float thumb = std::max(
        64.0f, height * static_cast<float>(view.visible) / static_cast<float>(view.count));
    c.list.rounded_rect({x, y + (height - thumb) * view.thumb(), 10.0f, thumb}, 5.0f,
                        Color::rgb(0xd6a4ff));
}

} // namespace pe::ui
