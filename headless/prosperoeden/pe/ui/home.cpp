// ProsperoEden - Launcher home: continue playing, recent games, navigation.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include "pe/ui/launcher.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <string>
#include <string_view>

namespace pe::ui
{

using audio::Cue;

namespace
{

const Color kWhite{1.0f, 1.0f, 1.0f, 1.0f};

// The four controllers, at the right of the hero beside its buttons.
constexpr float kPadsRight = 1768.0f;
Rect pad_rect(int player)
{
    return {kPadsRight - 354.0f + 94.0f * static_cast<float>(player), 506.0f, 72.0f, 50.0f};
}

} // namespace

void Launcher::open_library_at_last()
{
    open(Screen::library, true);
    enter_library();
    for (int i = 0; i < static_cast<int>(games_.size()); ++i)
    {
        if (games_[static_cast<std::size_t>(i)].file == home_.last_file)
        {
            library_.reset(library_.count, i);
            refresh_selected_game();
            break;
        }
    }
}

void Launcher::press_home(Key key)
{
    if (key != Key::cross)
        clear_confirmation();
    const bool ready = home_.setup_ready;
    const bool continue_ready = ready && home_.last_exists;
    // The status panel takes the place of the recent games.
    const bool recents_shown = home_.status.empty();
    const int recent_count = recents_shown ? static_cast<int>(home_.recents.size()) : 0;
    const int before = home_focus_;
    int &focus = home_focus_;

    switch (key)
    {
    case Key::up:
        if (focus == 0 || focus == 4)
            focus = ready ? 1 : 2;
        else if (focus >= 5)
            focus = 0;
        break;
    case Key::down:
        if (focus >= 1 && focus <= 3)
        {
            if (ready)
                focus = 0;
        }
        else if ((focus == 0 || focus == 4) && recents_shown)
        {
            focus = recent_count > 0 ? 5 : 9;
        }
        break;
    case Key::left:
    case Key::right:
    {
        const int delta = key == Key::right ? 1 : -1;
        if (focus >= 1 && focus <= 3)
        {
            focus = 1 + (focus - 1 + delta + 3) % 3;
            if (focus == 1 && !ready)
                focus = delta > 0 ? 2 : 3;
        }
        else if (focus == 0 || focus == 4)
        {
            if (continue_ready)
                focus = focus == 0 ? 4 : 0;
        }
        else
        {
            const int length = recent_count + 1;
            int position = focus == 9 ? recent_count : focus - 5;
            position = (position + delta + length) % length;
            focus = position == recent_count ? 9 : position + 5;
        }
        break;
    }
    case Key::triangle:
        if ((focus == 0 || focus == 4) && continue_ready)
            open_library_at_last();
        return;
    case Key::cross:
        press_ = 1.0f;
        if (focus == 0 && continue_ready)
        {
            if (!confirm_action(Confirmation::launch_game))
                return;
            launch(home_.last_file, home_.last_title, home_.last_cover);
        }
        else if ((focus == 0 || focus == 1 || focus == 9) && ready)
        {
            open(Screen::library, true);
            enter_library();
        }
        else if (focus == 2)
        {
            // "Recent" is a home-screen destination, not a separate full-screen menu.
            focus = recent_count > 0 ? 5 : 9;
            cue(Cue::focus);
        }
        else if (focus == 3)
        {
            open(Screen::settings, true);
            prefs_ = services_.preferences();
            section_.snap(1.0f);
        }
        else if (focus == 4 && continue_ready)
        {
            open_library_at_last();
        }
        else if (focus >= 5 && focus < 5 + recent_count && ready)
        {
            const Recent &recent = home_.recents[static_cast<std::size_t>(focus - 5)];
            if (!confirm_action(Confirmation::launch_game))
                return;
            launch(recent.file, recent.title, recent.cover);
        }
        else
        {
            cue(Cue::error);
        }
        return;
    default:
        return;
    }
    if (focus != before)
        cue(Cue::focus);
}

void Launcher::update_controllers(float dt)
{
    const unsigned now = services_.controllers() & 0xfu;
    bool joined = false;
    bool left = false;
    for (int player = 0; player < 4; ++player)
    {
        const std::size_t index = static_cast<std::size_t>(player);
        const bool on = (now >> player & 1u) != 0;
        controller_lit_[index].target = on ? 1.0f : 0.0f;
        if (!controllers_known_)
        {
            controller_lit_[index].snap(controller_lit_[index].target);
        }
        else if (on != ((controllers_ >> player & 1u) != 0))
        {
            (on ? joined : left) = true;
            if (on)
                controller_pop_[index] = 1.0f;
        }
        controller_lit_[index].update(dt, 10.0f);
        controller_pop_[index] = std::max(0.0f, controller_pop_[index] - dt / 0.5f);
    }
    // One sound however many changed at once; none while a game is starting.
    if ((joined || left) && selected_game_.empty())
        cue(joined ? Cue::saved : Cue::modal_close);
    controllers_ = now;
    controllers_known_ = true;
}

void Launcher::draw_controllers(Canvas &c)
{
    if (textures_.controller() == 0)
        return;
    text(c, tr("CONTROLLERS"), kPadsRight, baseline(462.0f, 30.0f, theme::kSmall), theme::kSmall,
         theme::kCopy, Align::right, 3.0f);
    for (int player = 0; player < 4; ++player)
    {
        const std::size_t index = static_cast<std::size_t>(player);
        const Rect r = pad_rect(player);
        const float lit = tween::clamp01(controller_lit_[index].value);
        // A controller that joins lands with a small bounce.
        const float pop = controller_pop_[index];
        const float bounce = std::sin(3.14159265f * (1.0f - pop)) * pop * motion();
        c.list.push_transform(1.0f + 0.34f * bounce, r.x + r.w * 0.5f, r.y + r.h * 0.5f, 0.0f,
                              -5.0f * bounce);
        controller_icon(c, r, lit);
        c.list.pop_transform();
        const char number[] = {static_cast<char>('1' + player), 0};
        text(c, number, r.x + r.w * 0.5f, baseline(564.0f, 26.0f, theme::kSmall), theme::kSmall,
             gfx::mix(theme::kFaint.with_alpha(0.6f), theme::kLime, lit), Align::center);
    }
}

void Launcher::draw_home(Canvas &c)
{
    gfx::DrawList &list = c.list;
    const bool ready = home_.setup_ready;
    const bool continue_ready = ready && home_.last_exists;
    const auto focus = [&](int index) { return home_springs_[static_cast<std::size_t>(index)].value; };
    const auto measure = [&](std::string_view value, float size, float tracking = 0.0f)
    { return text_width(c, value, size, tracking); };
    const auto arrive = [&](int band)
    { return tween::cubic_out((intro_ - 0.08f - 0.07f * static_cast<float>(band)) / 0.52f); };
    const auto begin_band = [&](int band, float rise)
    {
        const float e = arrive(band);
        list.push_opacity(e);
        list.push_transform(1.0f, 0.0f, 0.0f, 0.0f, (1.0f - e) * rise * motion());
    };
    const auto end_band = [&]
    {
        list.pop_transform();
        list.pop_opacity();
    };
    const auto begin_lift = [&](const Rect &r, float amount, float grow)
    {
        const float scale = 1.0f + (grow * amount - 0.030f * press_ * amount) * motion();
        list.push_transform(scale, r.x + r.w * 0.5f, r.y + r.h * 0.5f, 0.0f,
                            -3.0f * amount * motion());
    };

    const Rect hero{72.0f, 164.0f, 1228.0f, 514.0f};
    const Rect quick{1324.0f, 164.0f, 524.0f, 286.0f};
    const Rect status{1324.0f, 470.0f, 524.0f, 208.0f};

    // ---- brand + TV-first navigation ----
    begin_band(0, -16.0f);
    if (textures_.brand() != 0)
        list.rounded_image(textures_.brand(), {72.0f, 28.0f, 84.0f, 84.0f},
                           {0.0f, 0.0f, 1.0f, 1.0f}, 18.0f, kWhite);
    text(c, "EDEN", 176.0f, baseline(43.0f, 35.0f, theme::kText24), theme::kText24,
         theme::kTitle, Align::left, 3.0f);
    text(c, "ENCORE", 176.0f, baseline(77.0f, 24.0f, theme::kSmall), theme::kSmall,
         theme::kLime, Align::left, 5.0f);

    const Rect home_nav{720.0f, 44.0f, 154.0f, 54.0f};
    plate(c, kNavPlate, home_nav, 1.0f);
    text(c, tr("Home"), home_nav.x + home_nav.w * 0.5f,
         baseline(home_nav.y, home_nav.h, theme::kSmall), theme::kSmall, theme::kTitle,
         Align::center);

    static constexpr const char *kNav[] = {TR("Library"), TR("RECENTLY PLAYED"), TR("Settings")};
    const float nav_x[] = {886.0f, 1046.0f, 1260.0f};
    const float nav_w[] = {148.0f, 202.0f, 160.0f};
    for (int i = 0; i < 3; ++i)
    {
        const Rect r{nav_x[i], 44.0f, nav_w[i], 54.0f};
        const float f = focus(1 + i);
        list.push_opacity(i == 0 && !ready ? 0.45f : 1.0f);
        plate(c, kNavPlate, r, f);
        text_shrink(c, tr(kNav[i]), r.x + r.w * 0.5f,
                    baseline(r.y, r.h, theme::kSmall), theme::kSmall,
                    gfx::mix(theme::kMuted, theme::kTitle, f), r.w - 24.0f, Align::center);
        list.pop_opacity();
    }
    text(c, clock_, 1848.0f, baseline(42.0f, 54.0f, theme::kClock), theme::kClock,
         theme::kTitle, Align::right);
    list.rounded_rect({72.0f, 126.0f, 1776.0f, 1.0f}, 0.0f, theme::kText.with_alpha(0.12f));
    end_band();

    // ---- cinematic continue card ----
    begin_band(1, 24.0f);
    list.shadow({hero.x - 12.0f, hero.y - 8.0f, hero.w + 24.0f, hero.h + 24.0f},
                36.0f, 74.0f, theme::kLime.with_alpha(0.13f));
    glass(c, hero, 30.0f, theme::kGlass.with_alpha(0.58f), theme::kLime.with_alpha(0.28f), 1.1f);
    // The game art owns the right side of the hero instead of becoming a detached square tile.
    const Rect hero_art{884.0f, 192.0f, 380.0f, 380.0f};
    cover(c, home_.last_cover, hero_art, 26.0f, 0.75f);
    list.rounded_rect({844.0f, 192.0f, 72.0f, 380.0f}, 20.0f, theme::kGlass.with_alpha(0.34f));

    text(c, tr("CONTINUE PLAYING"), 118.0f, baseline(207.0f, 28.0f, theme::kSmall),
         theme::kSmall, theme::kLime, Align::left, 3.5f);
    text_block(c, home_.last_file.empty() ? tr("Your next adventure") : home_.last_title,
               118.0f, baseline(252.0f, 64.0f, theme::kDisplay), theme::kDisplay, 62.0f,
               theme::kTitle, 690.0f, 2, kShrink);
    notice(c, home_.last_file.empty() ? tr("Choose a game from your library.") : home_.last_caption,
           118.0f, baseline(390.0f, 34.0f, theme::kText24), theme::kText24,
           home_.last_caption_warning ? theme::kWarning : theme::kBody, 690.0f,
           home_.last_caption_warning);
    if (!home_.last_language.empty())
        text_shrink(c,
                    fill(tr("Add-ons: {0}  /  Language: {1}"),
                         {addons_line(home_.last_addons, home_.last_mods, home_.last_mods_on),
                          home_.last_language}),
                    118.0f, baseline(432.0f, 28.0f, theme::kSmall), theme::kSmall,
                    theme::kMeta, 700.0f);

    const char *first = continue_ready ? tr("Launch game") : tr("Open library");
    const char *second = tr("Game details");
    const float button = std::clamp(
        std::max(measure(first, theme::kText24), measure(second, theme::kText24)) + 66.0f,
        270.0f, 350.0f);
    const Rect continue_rect{118.0f, 494.0f, button, 70.0f};
    const Rect details_rect{118.0f + button + 16.0f, 494.0f, button, 70.0f};
    const auto hero_button = [&](const Rect &r, const char *label, float f, bool enabled)
    {
        list.push_opacity(enabled ? 1.0f : 0.38f);
        begin_lift(r, f, 0.032f);
        plate(c, kButtonPlate, r, f);
        text_shrink(c, label, r.x + r.w * 0.5f, baseline(r.y, r.h, theme::kText24),
                    theme::kText24, theme::kTitle, r.w - 30.0f, Align::center);
        list.pop_transform();
        list.pop_opacity();
    };
    hero_button(continue_rect, first, focus(0), ready);
    hero_button(details_rect, second, focus(4), continue_ready);

    // Small launch profile chips, as in the approved concept.
    const std::string renderer = prefs_.renderer == 0 ? "OpenGL" : "Vulkan";
    const char *outputs[] = {"1080p", "1440p", "2160p"};
    const std::string output = outputs[std::clamp(prefs_.output, 0, 2)];
    std::string resolution = "-";
    const auto &resolutions = services_.resolution_labels();
    if (prefs_.resolution >= 0 && prefs_.resolution < static_cast<int>(resolutions.size()))
        resolution = resolutions[static_cast<std::size_t>(prefs_.resolution)];
    const auto &profiles = services_.performance_profile_labels();
    std::string profile = prefs_.performance_profile >= 0 &&
                                  prefs_.performance_profile < static_cast<int>(profiles.size()) ?
                              profiles[static_cast<std::size_t>(prefs_.performance_profile)] : "-";
    const std::array<std::string, 4> chips{profile, renderer, output, resolution};
    float chip_x = 118.0f;
    for (const auto &chip : chips)
    {
        const float w = std::clamp(measure(chip, 18.0f) + 30.0f, 92.0f, 210.0f);
        list.rounded_rect({chip_x, 606.0f, w, 34.0f}, 17.0f, theme::kPanel.with_alpha(0.78f));
        text_shrink(c, chip, chip_x + w * 0.5f, baseline(606.0f, 34.0f, 18.0f), 18.0f,
                    theme::kLimePale, w - 18.0f, Align::center, 0.0f, 0.72f);
        chip_x += w + 10.0f;
    }
    end_band();

    // ---- right column: quick settings ----
    begin_band(2, 22.0f);
    glass(c, quick, 26.0f, theme::kGlass.with_alpha(0.68f), theme::kPanelEdge.with_alpha(0.72f), 0.8f);
    text(c, tr("PREFERENCES"), quick.x + 28.0f, baseline(quick.y + 24.0f, 30.0f, theme::kSmall),
         theme::kSmall, theme::kLimePale, Align::left, 3.0f);
    struct QuickRow { const char *label; std::string value; };
    const QuickRow quick_rows[] = {
        {tr("Performance"), profile},
        {tr("Renderer"), renderer},
        {tr("Output resolution"), output},
        {tr("Resolution"), resolution},
    };
    for (int i = 0; i < 4; ++i)
    {
        const float y = quick.y + 76.0f + static_cast<float>(i) * 47.0f;
        if (i != 0)
            list.rounded_rect({quick.x + 28.0f, y - 13.0f, quick.w - 56.0f, 1.0f}, 0.0f,
                              theme::kRule.with_alpha(0.50f));
        text_shrink(c, quick_rows[i].label, quick.x + 28.0f,
                    baseline(y - 4.0f, 32.0f, theme::kSmall), theme::kSmall, theme::kMuted,
                    240.0f);
        text_shrink(c, quick_rows[i].value, quick.x + quick.w - 28.0f,
                    baseline(y - 4.0f, 32.0f, theme::kSmall), theme::kSmall, theme::kLimePale,
                    220.0f, Align::right);
    }

    // ---- right column: system state ----
    glass(c, status, 26.0f, theme::kGlass.with_alpha(0.68f), theme::kPanelEdge.with_alpha(0.72f), 0.8f);
    text(c, tr("DIAGNOSTICS"), status.x + 28.0f,
         baseline(status.y + 22.0f, 30.0f, theme::kSmall), theme::kSmall,
         theme::kLimePale, Align::left, 3.0f);
    text_fit(c, home_.system_status, status.x + 28.0f,
             baseline(status.y + 70.0f, 34.0f, theme::kText24), theme::kText24,
             theme::kTitle, status.w - 56.0f);
    text(c, tr("Language"), status.x + 28.0f,
         baseline(status.y + 122.0f, 28.0f, theme::kSmall), theme::kSmall, theme::kMuted);
    text(c, services_.language_region(prefs_.language), status.x + status.w - 28.0f,
         baseline(status.y + 122.0f, 28.0f, theme::kSmall), theme::kSmall,
         theme::kValue, Align::right);
    text(c, "ENCORE", status.x + 28.0f,
         baseline(status.y + 158.0f, 28.0f, theme::kSmall), theme::kSmall, theme::kMuted);
    text(c, version_, status.x + status.w - 28.0f,
         baseline(status.y + 158.0f, 28.0f, theme::kSmall), theme::kSmall,
         theme::kValue, Align::right);
    // Connected controllers become a compact status instead of consuming the hero.
    float cx = status.x + 28.0f;
    for (int player = 0; player < 4; ++player)
    {
        if ((controllers_ & (1u << player)) == 0) continue;
        controller_icon(c, {cx, status.y + 176.0f, 46.0f, 32.0f}, 1.0f);
        cx += 56.0f;
    }
    end_band();

    // ---- recently played ----
    begin_band(3, 20.0f);
    if (!home_.status.empty())
    {
        const Rect panel{72.0f, 720.0f, 1776.0f, 214.0f};
        const Color accent = home_.launch_failed ? theme::kWarning : theme::kLime;
        glass(c, panel, 24.0f, theme::kPanel.with_alpha(0.80f), accent.with_alpha(0.30f), 0.7f);
        list.rounded_rect({panel.x + 18.0f, panel.y + 24.0f, 5.0f, panel.h - 48.0f}, 2.0f, accent);
        notice_block(c, home_.status, panel.x + 48.0f,
                     baseline(panel.y + 42.0f, 38.0f, theme::kText24),
                     theme::kText24, 38.0f, theme::kText, panel.w - 86.0f, 4,
                     home_.launch_failed);
    }
    else
    {
        text(c, tr("RECENTLY PLAYED"), 72.0f, baseline(712.0f, 28.0f, theme::kSmall),
             theme::kSmall, theme::kTitle, Align::left, 3.0f);
        const float vf = focus(9);
        const Rect all{1590.0f, 704.0f, 258.0f, 44.0f};
        plate(c, kNavPlate, all, vf);
        text_shrink(c, tr("VIEW ALL GAMES"), all.x + all.w * 0.5f,
                    baseline(all.y, all.h, theme::kSmall), theme::kSmall,
                    gfx::mix(theme::kMuted, theme::kLime, vf), all.w - 24.0f, Align::center);

        if (home_.recents.empty())
            text(c, tr("Games you launch will appear here."), 72.0f,
                 baseline(786.0f, 36.0f, theme::kText24), theme::kText24, theme::kMuted);

        const int shown = std::min<int>(4, static_cast<int>(home_.recents.size()));
        const float gap = 18.0f;
        const float width = (1776.0f - gap * 3.0f) / 4.0f;
        for (int i = 0; i < shown; ++i)
        {
            const Recent &recent = home_.recents[static_cast<std::size_t>(i)];
            const Rect r{72.0f + (width + gap) * static_cast<float>(i), 766.0f, width, 168.0f};
            const float f = focus(5 + i);
            begin_lift(r, f, 0.025f);
            plate(c, kTilePlate, r, f);
            cover(c, recent.cover, {r.x + 14.0f, r.y + 14.0f, 140.0f, 140.0f}, 20.0f, 0.45f);
            text_block(c, recent.title, r.x + 174.0f,
                       baseline(r.y + 28.0f, 34.0f, theme::kText24),
                       theme::kText24, 34.0f, gfx::mix(theme::kBody, theme::kTitle, f),
                       r.w - 194.0f, 3, kShrink);
            list.pop_transform();
        }
    }
    end_band();

    // ---- footer ----
    begin_band(4, 0.0f);
    list.rounded_rect({72.0f, 970.0f, 1776.0f, 1.0f}, 0.0f, theme::kText.with_alpha(0.11f));
    static constexpr Hint kHints[] = {
        {Pad::cross, TR("Select")}, {Pad::triangle, TR("Details")}, {Pad::dpad, TR("Navigate")}};
    draw_hints(c, kHints, 3, 72.0f, 1000.0f, theme::kMuted, 1200.0f);
    text(c, home_.system_status, 1848.0f, 1007.0f, theme::kSmall, theme::kMeta, Align::right);
    end_band();
}

} // namespace pe::ui
