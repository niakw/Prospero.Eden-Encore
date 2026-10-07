// ProsperoEden - Launcher home: continue playing, recent games, navigation.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include "pe/ui/launcher.hpp"
#include "pe/ui/video_presets.hpp"

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

constexpr int kHomeHero = 0;
constexpr int kHomeNavLibrary = 1;
constexpr int kHomeNavRecent = 2;
constexpr int kHomeNavSettings = 3;
constexpr int kHomeDetails = 4;
constexpr int kHomeRecentFirst = 5;
constexpr int kHomeRecentMax = 6;
constexpr int kHomeQuickPanel = kHomeRecentFirst + kHomeRecentMax; // 11
constexpr int kHomeQuickFirst = kHomeQuickPanel + 1;               // 12
constexpr int kHomeQuickCount = 7;
constexpr int kHomeStorage = kHomeQuickFirst + kHomeQuickCount;    // 19
constexpr int kHomeCache = kHomeStorage + 1;                       // 20

enum class HomeIcon { performance, display, output, mode, resolution, filter, antialias, storage, cache, language };

void home_icon(Canvas& c, HomeIcon icon, float x, float cy, Color ink)
{
    auto& list = c.list;
    const float left = x;
    switch (icon)
    {
    case HomeIcon::performance:
        list.ring(left + 12.0f, cy, 10.0f, 1.8f, ink);
        list.line(left + 12.0f, cy, left + 18.0f, cy - 6.0f, 2.0f, ink);
        list.circle(left + 12.0f, cy, 2.2f, ink);
        break;
    case HomeIcon::display:
        list.bordered_rect({left + 1.0f, cy - 9.0f, 23.0f, 15.0f}, 2.5f,
                           ink.with_alpha(0.0f), 1.7f, ink);
        list.line(left + 9.0f, cy + 9.0f, left + 16.0f, cy + 9.0f, 1.7f, ink);
        list.line(left + 12.5f, cy + 6.0f, left + 12.5f, cy + 9.0f, 1.7f, ink);
        break;
    case HomeIcon::output:
        list.bordered_rect({left + 1.0f, cy - 9.0f, 23.0f, 17.0f}, 3.0f,
                           ink.with_alpha(0.0f), 1.7f, ink);
        list.line(left + 5.0f, cy + 12.0f, left + 20.0f, cy + 12.0f, 1.7f, ink);
        list.line(left + 12.5f, cy + 8.0f, left + 12.5f, cy + 12.0f, 1.7f, ink);
        break;
    case HomeIcon::mode:
        list.bordered_rect({left + 2.0f, cy - 8.0f, 21.0f, 16.0f}, 5.0f,
                           ink.with_alpha(0.0f), 1.7f, ink);
        list.circle(left + 7.0f, cy, 1.6f, ink);
        list.circle(left + 18.0f, cy, 1.6f, ink);
        break;
    case HomeIcon::resolution:
        list.bordered_rect({left + 1.0f, cy - 9.0f, 23.0f, 18.0f}, 3.0f,
                           ink.with_alpha(0.0f), 1.7f, ink);
        list.line(left + 5.0f, cy + 5.0f, left + 10.0f, cy, 1.7f, ink);
        list.line(left + 10.0f, cy, left + 14.0f, cy + 4.0f, 1.7f, ink);
        list.line(left + 14.0f, cy + 4.0f, left + 20.0f, cy - 3.0f, 1.7f, ink);
        break;
    case HomeIcon::filter:
        list.line(left + 2.0f, cy - 7.0f, left + 22.0f, cy - 7.0f, 1.7f, ink);
        list.line(left + 5.0f, cy, left + 19.0f, cy, 1.7f, ink);
        list.line(left + 9.0f, cy + 7.0f, left + 15.0f, cy + 7.0f, 1.7f, ink);
        break;
    case HomeIcon::antialias:
        list.line(left + 3.0f, cy + 8.0f, left + 10.0f, cy - 8.0f, 1.8f, ink);
        list.line(left + 10.0f, cy - 8.0f, left + 17.0f, cy + 8.0f, 1.8f, ink);
        list.line(left + 6.0f, cy + 1.0f, left + 14.0f, cy + 1.0f, 1.6f, ink);
        list.line(left + 19.0f, cy - 7.0f, left + 23.0f, cy - 3.0f, 1.4f, ink);
        break;
    case HomeIcon::storage:
        list.bordered_rect({left + 2.0f, cy - 8.0f, 22.0f, 16.0f}, 4.0f,
                           ink.with_alpha(0.0f), 1.7f, ink);
        list.line(left + 5.0f, cy + 3.0f, left + 21.0f, cy + 3.0f, 1.5f, ink);
        list.circle(left + 19.0f, cy - 3.0f, 1.5f, ink);
        break;
    case HomeIcon::cache:
        for (int i = -1; i <= 1; ++i)
            list.bordered_rect({left + 3.0f, cy + 5.0f * i - 5.0f, 20.0f, 6.0f}, 3.0f,
                               ink.with_alpha(0.0f), 1.4f, ink);
        break;
    case HomeIcon::language:
        list.ring(left + 12.0f, cy, 10.0f, 1.6f, ink);
        list.line(left + 2.0f, cy, left + 22.0f, cy, 1.4f, ink);
        list.line(left + 12.0f, cy - 10.0f, left + 12.0f, cy + 10.0f, 1.4f, ink);
        break;
    }
}

// The four controllers, at the right of the hero beside its buttons.
constexpr float kPadsRight = 1768.0f;
Rect pad_rect(int player)
{
    return {kPadsRight - 354.0f + 94.0f * static_cast<float>(player), 506.0f, 72.0f, 50.0f};
}

} // namespace

void Launcher::open_library_at_file(const std::string &file)
{
    open(Screen::library, true);
    enter_library();
    for (int i = 0; i < static_cast<int>(games_.size()); ++i)
    {
        if (games_[static_cast<std::size_t>(i)].file == file)
        {
            library_.reset(library_.count, i);
            refresh_selected_game();
            break;
        }
    }
}

void Launcher::refresh_home_hero()
{
    std::uint64_t title_id = home_.last_title_id;
    if (home_recent_ >= 0 && home_recent_ < static_cast<int>(home_.recents.size()))
        title_id = home_.recents[static_cast<std::size_t>(home_recent_)].title_id;
    home_game_settings_ = title_id != 0 ? services_.game_settings(title_id) : GameSettings{};
    home_game_docked_ = title_id == 0 || services_.docked(title_id);
}

void Launcher::press_home(Key key)
{
    const bool ready = home_.setup_ready;
    const bool recents_shown = home_.status.empty();
    const int recent_count = recents_shown ? std::min<int>(kHomeRecentMax, static_cast<int>(home_.recents.size())) : 0;
    const auto selected_recent = [&]() -> const Recent *
    {
        return home_recent_ >= 0 && home_recent_ < recent_count ?
                   &home_.recents[static_cast<std::size_t>(home_recent_)] : nullptr;
    };
    const auto hero_file = [&]() -> std::string
    {
        const Recent *recent = selected_recent();
        return recent != nullptr ? recent->file : home_.last_file;
    };
    const auto hero_title_id = [&]() -> std::uint64_t
    {
        const Recent *recent = selected_recent();
        return recent != nullptr ? recent->title_id : home_.last_title_id;
    };
    const bool hero_ready = ready && !hero_file().empty();

    const auto change_quick = [&](int row, int step)
    {
        const std::uint64_t title_id = hero_title_id();
        if (!hero_ready || title_id == 0)
        {
            cue(Cue::error);
            return;
        }

        bool saved = false;
        GameSettings next = home_game_settings_;
        if (row == 6)
        {
            next.console_mode = home_game_docked_ ? 0 : 1;
            RefreshVideoProfile(next, prefs_, title_id);
        }
        else
        {
            if (row == 0)
            {
                const int current = next.performance_profile >= 0 ?
                    next.performance_profile : DetectVideoProfile(next, prefs_, title_id);
                ApplyVideoPreset(next, CycleVideoPreset(current, step), title_id);
            }
            else if (row == 1)
            {
                const int current = next.renderer >= 0 ? next.renderer : prefs_.renderer;
                next.renderer = current == 0 ? 1 : 0;
                RefreshVideoProfile(next, prefs_, title_id);
            }
            else if (row == 2)
            {
                const int current = next.output >= 0 ? next.output : prefs_.output;
                next.output = (current + step + 3) % 3;
                RefreshVideoProfile(next, prefs_, title_id);
            }
            else if (row == 3)
            {
                const int count = static_cast<int>(services_.resolution_labels().size());
                if (count <= 0) return;
                const int current = next.resolution >= 0 ? next.resolution : prefs_.resolution;
                next.resolution = (current + step + count) % count;
                RefreshVideoProfile(next, prefs_, title_id);
            }
            else if (row == 4)
            {
                const int count = static_cast<int>(services_.filter_labels().size());
                if (count <= 0) return;
                const int current = next.filter >= 0 ? next.filter : prefs_.filter;
                next.filter = (current + step + count) % count;
                RefreshVideoProfile(next, prefs_, title_id);
            }
            else
            {
                const int count = static_cast<int>(services_.anti_aliasing_labels().size());
                if (count <= 0) return;
                const int current = next.anti_aliasing >= 0 ?
                    next.anti_aliasing : prefs_.anti_aliasing;
                next.anti_aliasing = (current + step + count) % count;
                RefreshVideoProfile(next, prefs_, title_id);
            }
        }
        saved = services_.set_game_settings(title_id, next);
        if (saved) {
            home_game_settings_ = next;
            home_game_docked_ = next.console_mode >= 0 ? next.console_mode == 1 : services_.docked(title_id);
        }

        if (saved)
        {
            refresh_home_hero();
            say(tr("Saved for this game. Applies on next launch."));
            cue(Cue::toggle);
        }
        else
        {
            say(tr("Could not save. Please try again."), true);
            cue(Cue::error);
        }
    };

    const int before = home_focus_;
    int &focus = home_focus_;

    switch (key)
    {
    case Key::up:
        if (focus == kHomeHero || focus == kHomeDetails)
            focus = ready ? kHomeNavLibrary : kHomeNavRecent;
        else if (focus >= kHomeRecentFirst && focus < kHomeRecentFirst + recent_count)
            focus = hero_ready ? kHomeHero : (ready ? kHomeNavLibrary : kHomeNavRecent);
        else if (focus == kHomeQuickPanel)
            focus = kHomeNavSettings;
        else if (focus >= kHomeQuickFirst && focus < kHomeQuickFirst + kHomeQuickCount)
            focus = focus > kHomeQuickFirst ? focus - 1 : kHomeQuickPanel;
        else if (focus == kHomeStorage || focus == kHomeCache)
            focus = kHomeQuickFirst + kHomeQuickCount - 1;
        break;
    case Key::down:
        if (focus >= kHomeNavLibrary && focus <= kHomeNavSettings)
        {
            if (hero_ready)
                focus = focus == kHomeNavSettings ? kHomeQuickPanel : kHomeHero;
        }
        else if ((focus == kHomeHero || focus == kHomeDetails) && recents_shown)
        {
            if (recent_count > 0) focus = kHomeRecentFirst;
        }
        else if (focus == kHomeQuickPanel)
        {
            focus = kHomeCache;
        }
        else if (focus >= kHomeQuickFirst && focus < kHomeQuickFirst + kHomeQuickCount)
        {
            focus = focus < kHomeQuickFirst + kHomeQuickCount - 1 ? focus + 1 : kHomeCache;
        }
        else if (focus == kHomeStorage || focus == kHomeCache)
        {
            if (recents_shown && recent_count > 0) focus = kHomeRecentFirst;
        }
        break;
    case Key::left:
    case Key::right:
    {
        const int delta = key == Key::right ? 1 : -1;
        if (focus >= kHomeNavLibrary && focus <= kHomeNavSettings)
        {
            focus = kHomeNavLibrary + (focus - kHomeNavLibrary + delta + 3) % 3;
            if (focus == kHomeNavLibrary && !ready)
                focus = delta > 0 ? kHomeNavRecent : kHomeNavSettings;
        }
        else if (focus == kHomeHero || focus == kHomeDetails)
        {
            if (hero_ready)
            {
                if (delta > 0)
                    focus = focus == kHomeHero ? kHomeDetails : kHomeQuickPanel;
                else
                    focus = focus == kHomeDetails ? kHomeHero : focus;
            }
        }
        else if (focus == kHomeQuickPanel)
        {
            // Deliberately inert: the user must press Cross to enter the quick-settings block.
            return;
        }
        else if (focus >= kHomeQuickFirst && focus < kHomeQuickFirst + kHomeQuickCount)
        {
            if (home_quick_edit_ == focus - kHomeQuickFirst)
            {
                change_quick(focus - kHomeQuickFirst, delta);
                return;
            }
        }
        else if (focus >= kHomeRecentFirst && focus < kHomeRecentFirst + recent_count && recent_count > 0)
        {
            int position = focus - kHomeRecentFirst;
            position = (position + delta + recent_count) % recent_count;
            focus = position + kHomeRecentFirst;
        }
        else if (focus == kHomeStorage || focus == kHomeCache)
        {
            focus = focus == kHomeStorage ? kHomeCache : kHomeStorage;
        }
        break;
    }
    case Key::circle:
        if (focus >= kHomeQuickFirst && focus < kHomeQuickFirst + kHomeQuickCount)
        {
            if (home_quick_edit_ >= 0)
            {
                home_quick_edit_ = -1;
                cue(Cue::back);
            }
            else
            {
                focus = kHomeQuickPanel;
                cue(Cue::back);
            }
        }
        else if (focus == kHomeQuickPanel)
        {
            focus = kHomeDetails;
            cue(Cue::back);
        }
        else if (focus == kHomeStorage || focus == kHomeCache)
        {
            focus = kHomeQuickFirst + kHomeQuickCount - 1;
            cue(Cue::back);
        }
        return;
    case Key::triangle:
    {
        if (focus >= kHomeRecentFirst && focus < kHomeRecentFirst + recent_count)
        {
            home_recent_ = focus - kHomeRecentFirst;
            refresh_home_hero();
        }
        const std::string file = hero_file();
        if (!file.empty() && ready)
            (void)open_game_settings_at_file(file);
        else
            cue(Cue::error);
        return;
    }
    case Key::cross:
        press_ = 1.0f;
        if (focus == kHomeQuickPanel)
        {
            focus = kHomeQuickFirst;
            home_quick_edit_ = -1;
            cue(Cue::open);
            break;
        }
        if (focus >= kHomeQuickFirst && focus < kHomeQuickFirst + kHomeQuickCount)
        {
            const int row = focus - kHomeQuickFirst;
            home_quick_edit_ = home_quick_edit_ == row ? -1 : row;
            cue(home_quick_edit_ >= 0 ? Cue::toggle : Cue::saved);
            return;
        }
        if (focus == kHomeCache)
        {
            if (!confirm_action(Confirmation::shader_caches)) return;
            std::string result;
            const bool cleared = services_.clear_shader_caches(&result);
            home_diagnostics_ = services_.diagnostics();
            say(result, !cleared);
            cue(cleared ? Cue::saved : Cue::error);
            return;
        }
        if (focus == kHomeStorage)
        {
            open(Screen::files, true);
            enter_files();
            return;
        }
        if (focus == kHomeHero && hero_ready)
        {
            const Recent *recent = selected_recent();
            const std::string file = recent != nullptr ? recent->file : home_.last_file;
            const std::string title = recent != nullptr ? recent->title : home_.last_title;
            const std::string cover = recent != nullptr ? recent->cover : home_.last_cover;
            launch(file, title, cover);
        }
        else if ((focus == kHomeHero || focus == kHomeNavLibrary) && ready)
        {
            open(Screen::library, true);
            enter_library();
        }
        else if (focus == kHomeNavRecent)
        {
            if (recent_count > 0) focus = kHomeRecentFirst;
            if (recent_count > 0)
            {
                home_recent_ = 0;
                refresh_home_hero();
            }
            cue(Cue::focus);
        }
        else if (focus == kHomeNavSettings)
        {
            open(Screen::settings, true);
            prefs_ = services_.preferences();
            section_.snap(1.0f);
        }
        else if (focus == kHomeDetails && hero_ready)
        {
            open_library_at_file(hero_file());
        }
        else if (focus >= kHomeRecentFirst && focus < kHomeRecentFirst + recent_count && ready)
        {
            home_recent_ = focus - kHomeRecentFirst;
            refresh_home_hero();
            focus = kHomeHero;
            cue(Cue::saved);
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
    {
        if (focus < kHomeQuickFirst || focus >= kHomeQuickFirst + kHomeQuickCount ||
            home_quick_edit_ != focus - kHomeQuickFirst)
            home_quick_edit_ = -1;
        if (focus >= kHomeRecentFirst && focus < kHomeRecentFirst + recent_count)
        {
            home_recent_ = focus - kHomeRecentFirst;
            refresh_home_hero();
        }
        cue(Cue::focus);
    }
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
    const Recent *hero_recent =
        home_recent_ >= 0 && home_recent_ < static_cast<int>(home_.recents.size()) ?
            &home_.recents[static_cast<std::size_t>(home_recent_)] : nullptr;
    const std::string &hero_file = hero_recent != nullptr ? hero_recent->file : home_.last_file;
    const std::string &hero_title = hero_recent != nullptr ? hero_recent->title : home_.last_title;
    const std::string &hero_cover = hero_recent != nullptr ? hero_recent->cover : home_.last_cover;
    const std::string &hero_artwork = hero_recent != nullptr ? hero_recent->hero : home_.last_hero;
    const std::string &hero_addons = hero_recent != nullptr ? hero_recent->addons : home_.last_addons;
    const std::string &hero_language = hero_recent != nullptr ? hero_recent->language : home_.last_language;
    const std::string &hero_intro = hero_recent != nullptr ? hero_recent->intro : home_.last_intro;
    const std::uint64_t hero_title_id = hero_recent != nullptr ? hero_recent->title_id : home_.last_title_id;
    int hero_max_players = hero_recent != nullptr ? hero_recent->max_players : home_.last_max_players;
    const bool hero_ready = ready && !hero_file.empty();
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
    const Rect status{1324.0f, 470.0f, 524.0f, 454.0f};

    // ---- brand + TV-first navigation ----
    begin_band(0, -16.0f);
    const int header_focus = home_focus_ >= kHomeNavLibrary && home_focus_ <= kHomeNavSettings ? home_focus_ : -1;
    draw_top_nav(c, 0, header_focus, header_focus >= 0 ? focus(header_focus) : 0.0f);
    end_band();

    // ---- cinematic continue card ----
    begin_band(1, 24.0f);
    list.shadow({hero.x - 12.0f, hero.y - 8.0f, hero.w + 24.0f, hero.h + 24.0f},
                36.0f, 74.0f, theme::kLime.with_alpha(0.13f));
    glass(c, hero, 30.0f, theme::kGlass.with_alpha(0.44f), theme::kLime.with_alpha(0.28f), 1.1f);
    // The selected game owns the whole hero. Nlib's 16:9 banner fills the card edge-to-edge;
    // layered scrims preserve TV readability without reducing the artwork to a thumbnail on the right.
    if (!hero_artwork.empty())
    {
        const Rect hero_art{hero.x + 4.0f, hero.y + 4.0f, hero.w - 8.0f, hero.h - 8.0f};
        cover_crop(c, hero_artwork, hero_art, 28.0f, 0.78f);
        list.hgradient_rect(hero_art, 28.0f,
                            theme::kScrim.with_alpha(0.93f), theme::kScrim.with_alpha(0.08f));
        list.gradient_rect({hero_art.x, hero_art.y + hero_art.h * 0.52f, hero_art.w, hero_art.h * 0.48f},
                           28.0f, theme::kScrim.with_alpha(0.02f),
                           theme::kScrim.with_alpha(0.74f));
        // Redraw the premium glass edge after the artwork so the banner can never cover the focus frame.
        list.bordered_rect(hero, 30.0f, kWhite.with_alpha(0.0f), 1.35f,
                           theme::kPanelEdge.with_alpha(0.76f));
        list.bordered_rect({hero.x + 2.0f, hero.y + 2.0f, hero.w - 4.0f, hero.h - 4.0f},
                           28.0f, kWhite.with_alpha(0.0f), 0.7f, kWhite.with_alpha(0.08f));
    }
    else
    {
        const Rect hero_art{884.0f, 192.0f, 380.0f, 380.0f};
        cover(c, hero_cover, hero_art, 26.0f, 0.75f);
        list.rounded_rect({844.0f, 192.0f, 72.0f, 380.0f}, 20.0f,
                          theme::kGlass.with_alpha(0.34f));
    }

    text(c, hero_recent != nullptr ? tr("SELECTED GAME") : tr("CONTINUE PLAYING"),
         118.0f, baseline(207.0f, 28.0f, theme::kSmall),
         theme::kSmall, theme::kLime, Align::left, 3.5f);
    text_block(c, hero_file.empty() ? tr("Your next adventure") : hero_title,
               118.0f, baseline(252.0f, 64.0f, theme::kDisplay), theme::kDisplay, 62.0f,
               theme::kTitle, 620.0f, 2, kShrink);
    const std::string hero_caption =
        hero_file.empty() ? std::string{tr("Choose a game from your library.")} :
        !hero_intro.empty() ? hero_intro :
        hero_recent != nullptr ? std::string{tr("Recently played")} : home_.last_caption;
    const bool hero_caption_warning = hero_recent == nullptr && home_.last_caption_warning;
    if (hero_caption_warning)
        notice(c, hero_caption, 118.0f, baseline(390.0f, 34.0f, theme::kText24), theme::kText24,
               theme::kWarning, 620.0f, true);
    else
        text_block(c, hero_caption, 118.0f, baseline(380.0f, 28.0f, 21.0f), 21.0f, 30.0f,
                   theme::kBody, 620.0f, 2, kShrink);
    int hero_mods = hero_recent == nullptr ? home_.last_mods : 0;
    int hero_mods_on = hero_recent == nullptr ? home_.last_mods_on : 0;
    for (const Game &game : games_)
        if (game.file == hero_file) {
            hero_mods = game.mods;
            hero_mods_on = game.mods_on;
            if (game.max_players > 0) hero_max_players = game.max_players;
            break;
        }
    if (!hero_language.empty())
        text_shrink(c,
                    fill(tr("Add-ons: {0}  /  Language: {1}"),
                         {addons_line(hero_addons, hero_mods, hero_mods_on), hero_language}),
                    118.0f, baseline(432.0f, 28.0f, theme::kSmall), theme::kSmall,
                    theme::kMeta, 620.0f);

    const char *first = hero_ready ? tr("Launch game") : tr("Open library");
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
    hero_button(continue_rect, first, focus(kHomeHero), ready);
    hero_button(details_rect, second, focus(kHomeDetails), hero_ready);

    // Effective values: authored general tier -> title-specific encore-overrides tier -> manual game override.
    // A Custom global profile has no authored tier, so its raw global values remain the fallback.
    const bool authored_global = prefs_.performance_profile >= 0 &&
                                 prefs_.performance_profile < kAuthoredVideoProfiles;
    const auto& base_profile = VideoPresetForTitle(hero_title_id,
        authored_global ? prefs_.performance_profile : 1);
    const int base_renderer = authored_global ? base_profile.renderer : prefs_.renderer;
    const int base_output = authored_global ? base_profile.output : prefs_.output;
    const int base_resolution = authored_global ? base_profile.resolution : prefs_.resolution;
    const int base_filter = authored_global ? base_profile.filter : prefs_.filter;
    const int base_aa = authored_global ? base_profile.anti_aliasing : prefs_.anti_aliasing;
    const int effective_renderer =
        home_game_settings_.renderer >= 0 ? home_game_settings_.renderer : base_renderer;
    const int effective_output =
        home_game_settings_.output >= 0 ? home_game_settings_.output : base_output;
    const int effective_resolution =
        home_game_settings_.resolution >= 0 ? home_game_settings_.resolution : base_resolution;
    const int effective_filter =
        home_game_settings_.filter >= 0 ? home_game_settings_.filter : base_filter;
    const int effective_aa =
        home_game_settings_.anti_aliasing >= 0 ? home_game_settings_.anti_aliasing : base_aa;
    const int effective_profile =
        home_game_settings_.performance_profile >= 0 ?
            home_game_settings_.performance_profile : prefs_.performance_profile;
    const std::string renderer = effective_renderer == 0 ? "OpenGL" : "Vulkan";
    const char *outputs[] = {"1080p", "1440p", "2160p"};
    const std::string output = outputs[std::clamp(effective_output, 0, 2)];
    std::string resolution = "-";
    const auto &resolutions = services_.resolution_labels();
    if (effective_resolution >= 0 && effective_resolution < static_cast<int>(resolutions.size()))
        resolution = resolutions[static_cast<std::size_t>(effective_resolution)];
    std::string filter = "-";
    const auto &filters = services_.filter_labels();
    if (effective_filter >= 0 && effective_filter < static_cast<int>(filters.size()))
        filter = filters[static_cast<std::size_t>(effective_filter)];
    std::string antialias = "-";
    const auto &aa_labels = services_.anti_aliasing_labels();
    if (effective_aa >= 0 && effective_aa < static_cast<int>(aa_labels.size()))
        antialias = aa_labels[static_cast<std::size_t>(effective_aa)];
    const auto &profiles = services_.performance_profile_labels();
    std::string profile = effective_profile >= 0 &&
                                  effective_profile < static_cast<int>(profiles.size()) ?
                              profiles[static_cast<std::size_t>(effective_profile)] : "-";
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
    if (hero_max_players > 0)
    {
        // Local controller capacity belongs to the same metadata rail as profile / renderer /
        // output / resolution, anchored at the hero's lower-right edge.
        const Rect players_chip{hero.x + hero.w - 192.0f, 606.0f, 156.0f, 34.0f};
        list.bordered_rect(players_chip, 17.0f, theme::kPanel.with_alpha(0.82f), 1.0f,
                           theme::kPanelEdge.with_alpha(0.58f));
        controller_icon(c, {players_chip.x + 10.0f, players_chip.y + 5.0f, 34.0f, 24.0f}, 1.0f);
        const std::string controllers = std::string{tr("DualSense")} + " ×" +
                                        std::to_string(hero_max_players);
        text_shrink(c, controllers, players_chip.x + 51.0f,
                    baseline(players_chip.y, players_chip.h, 15.0f), 15.0f,
                    theme::kTitle, players_chip.w - 61.0f);
    }
    end_band();

    // ---- right column: selected game's effective quick settings ----
    begin_band(2, 22.0f);
    glass(c, quick, 26.0f, theme::kGlass.with_alpha(0.68f), theme::kPanelEdge.with_alpha(0.72f), 0.8f);
    const float quick_panel_focus = focus(kHomeQuickPanel);
    if (quick_panel_focus > 0.001f)
        plate_focus(c, kTilePlate, quick, quick_panel_focus);
    text(c, tr("QUICK SETTINGS"), quick.x + 28.0f, baseline(quick.y + 24.0f, 30.0f, theme::kSmall),
         theme::kSmall, theme::kLimePale, Align::left, 3.0f);
    struct QuickRow { HomeIcon icon; const char *label; std::string value; };
    const QuickRow quick_rows[] = {
        {HomeIcon::performance, tr("Video preset"), profile},
        {HomeIcon::display, tr("Renderer"), renderer},
        {HomeIcon::output, tr("TV output"), output},
        {HomeIcon::resolution, tr("Resolution"), resolution},
        {HomeIcon::filter, tr("Upscaling filter"), filter},
        {HomeIcon::antialias, tr("Anti-aliasing"), antialias},
        {HomeIcon::mode, tr("Console mode"), home_game_docked_ ? tr("Docked") : tr("Handheld")},
    };
    for (int i = 0; i < 7; ++i)
    {
        const float y = quick.y + 64.0f + static_cast<float>(i) * 31.0f;
        const Rect row_box{quick.x + 14.0f, y - 4.0f, quick.w - 28.0f, 28.0f};
        const float f = focus(kHomeQuickFirst + i);
        if (i != 0)
            list.rounded_rect({quick.x + 28.0f, y - 6.0f, quick.w - 56.0f, 1.0f}, 0.0f,
                              theme::kRule.with_alpha(0.40f));
        if (f > 0.01f)
            plate_focus(c, kRowPlate, row_box, f);
        const bool editing = home_quick_edit_ == i;
        if (editing)
            list.bordered_rect(row_box, 14.0f, theme::kPanel.with_alpha(0.18f), 2.0f,
                               theme::kLime.with_alpha(0.92f));
        home_icon(c, quick_rows[i].icon, quick.x + 28.0f, y + 10.0f,
                  gfx::mix(theme::kMeta, theme::kTitle, f));
        text_shrink(c, quick_rows[i].label, quick.x + 66.0f,
                    baseline(y - 1.0f, 24.0f, 16.0f), 16.0f,
                    gfx::mix(theme::kMuted, theme::kTitle, f), 178.0f);
        const Color value_color = gfx::mix(theme::kAccentTeal, theme::kTitle, f);
        text_shrink(c, quick_rows[i].value, quick.x + quick.w - 52.0f,
                    baseline(y - 1.0f, 24.0f, 16.0f), 16.0f,
                    value_color, 178.0f, Align::right);
        const float cx = quick.x + quick.w - 30.0f;
        const float cy = y + 10.0f;
        const Color arrow = editing ? theme::kLimePale : gfx::mix(theme::kFaint, theme::kLimePale, f);
        if (editing)
        {
            const float lx = quick.x + 18.0f;
            list.line(lx + 3.0f, cy - 4.0f, lx - 2.0f, cy, 1.7f, arrow);
            list.line(lx - 2.0f, cy, lx + 3.0f, cy + 4.0f, 1.7f, arrow);
        }
        list.line(cx - 3.0f, cy - 4.0f, cx + 2.0f, cy, 1.5f, arrow);
        list.line(cx + 2.0f, cy, cx - 3.0f, cy + 4.0f, 1.5f, arrow);
    }

    // ---- right column: system state ----
    glass(c, status, 26.0f, theme::kGlass.with_alpha(0.70f),
          theme::kPanelEdge.with_alpha(0.68f), 0.95f);
    text(c, tr("SYSTEM STATUS"), status.x + 28.0f,
         baseline(status.y + 22.0f, 30.0f, theme::kSmall), theme::kSmall,
         theme::kTitle, Align::left, 2.0f);
    text_fit(c, home_.system_status, status.x + 28.0f,
             baseline(status.y + 58.0f, 26.0f, 17.0f), 17.0f,
             theme::kMeta, status.w - 56.0f);
    list.rounded_rect({status.x + 28.0f, status.y + 96.0f, status.w - 56.0f, 1.0f},
                      0.0f, theme::kRule.with_alpha(0.56f));

    const Rect cache_row{status.x + 22.0f, status.y + 116.0f, status.w - 44.0f, 76.0f};
    const Rect storage_row{status.x + 22.0f, status.y + 202.0f, status.w - 44.0f, 88.0f};
    const float cache_focus = focus(kHomeCache);
    const float storage_focus = focus(kHomeStorage);
    for (const auto& row : {cache_row, storage_row})
        list.bordered_rect(row, 18.0f, theme::kPanel.with_alpha(0.46f), 1.0f,
                           theme::kPanelEdgeSoft.with_alpha(0.52f));
    if (cache_focus > 0.001f) plate_focus(c, kRowPlate, cache_row, cache_focus);
    if (storage_focus > 0.001f) plate_focus(c, kRowPlate, storage_row, storage_focus);

    home_icon(c, HomeIcon::cache, cache_row.x + 18.0f, cache_row.y + 38.0f,
              gfx::mix(theme::kMeta, theme::kTitle, cache_focus));
    text(c, tr("SHADER/JIT CACHES"), cache_row.x + 58.0f,
         baseline(cache_row.y + 11.0f, 22.0f, 15.0f), 15.0f,
         gfx::mix(theme::kMuted, theme::kLimePale, cache_focus));
    text_shrink(c, home_diagnostics_.shader_caches, cache_row.x + 58.0f,
                baseline(cache_row.y + 35.0f, 27.0f, 20.0f), 20.0f,
                theme::kTitle, 250.0f);
    if (cache_focus > 0.02f)
        text_shrink(c, tr("Cross to clear"), cache_row.x + cache_row.w - 18.0f,
                    baseline(cache_row.y + 35.0f, 27.0f, 15.0f), 15.0f,
                    theme::kLimePale, 150.0f, Align::right);

    home_icon(c, HomeIcon::storage, storage_row.x + 18.0f, storage_row.y + 38.0f,
              gfx::mix(theme::kMeta, theme::kTitle, storage_focus));
    text(c, tr("STORAGE"), storage_row.x + 58.0f,
         baseline(storage_row.y + 10.0f, 22.0f, 15.0f), 15.0f,
         gfx::mix(theme::kMuted, theme::kLimePale, storage_focus));
    const std::string storage_value =
        home_diagnostics_.total_space.empty() ? home_diagnostics_.free_space :
        home_diagnostics_.free_space + " / " + home_diagnostics_.total_space;
    text_shrink(c, storage_value, storage_row.x + 58.0f,
                baseline(storage_row.y + 34.0f, 26.0f, 19.0f), 19.0f,
                theme::kTitle, storage_row.w - 86.0f);
    if (home_diagnostics_.total_bytes > 0)
    {
        const float used = std::clamp(
            1.0f - static_cast<float>(home_diagnostics_.free_bytes) /
                       static_cast<float>(home_diagnostics_.total_bytes),
            0.0f, 1.0f);
        const Rect bar{storage_row.x + 58.0f, storage_row.y + 69.0f,
                       storage_row.w - 86.0f, 5.0f};
        list.rounded_rect(bar, 2.5f, theme::kRule.with_alpha(0.76f));
        if (used > 0.002f)
        {
            list.rounded_rect({bar.x, bar.y, bar.w * used, bar.h}, 2.5f,
                              theme::kBlue.with_alpha(0.94f));
            list.shadow({bar.x, bar.y - 2.0f, bar.w * used, bar.h + 4.0f}, 3.0f, 9.0f,
                        theme::kBlue.with_alpha(0.20f));
        }
    }

    list.rounded_rect({status.x + 28.0f, status.y + 310.0f, status.w - 56.0f, 1.0f},
                      0.0f, theme::kRule.with_alpha(0.46f));
    home_icon(c, HomeIcon::language, status.x + 28.0f, status.y + 348.0f, theme::kMeta);
    text(c, tr("Language"), status.x + 66.0f,
         baseline(status.y + 332.0f, 32.0f, 18.0f), 18.0f, theme::kMuted);
    const auto& language_labels = services_.language_labels();
    const std::string language_label =
        prefs_.language >= 0 && prefs_.language < static_cast<int>(language_labels.size()) ?
            language_labels[static_cast<std::size_t>(prefs_.language)] : tr("Unknown");
    text_shrink(c, language_label, status.x + status.w - 28.0f,
                baseline(status.y + 332.0f, 32.0f, 18.0f), 18.0f,
                theme::kValue, 220.0f, Align::right);

    list.rounded_rect({status.x + 28.0f, status.y + 378.0f, status.w - 56.0f, 1.0f},
                      0.0f, theme::kRule.with_alpha(0.38f));
    text(c, tr("Version"), status.x + 28.0f,
         baseline(status.y + 394.0f, 30.0f, 17.0f), 17.0f, theme::kMuted);
    text_shrink(c, version_, status.x + status.w - 28.0f,
                baseline(status.y + 394.0f, 30.0f, 17.0f), 17.0f,
                theme::kValue, 220.0f, Align::right);
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
        if (home_.recents.empty())
            text(c, tr("Games you launch will appear here."), 72.0f,
                 baseline(786.0f, 36.0f, theme::kText24), theme::kText24, theme::kMuted);

        const int shown = std::min<int>(6, static_cast<int>(home_.recents.size()));
        constexpr float available = 1228.0f;
        constexpr float gap = 14.0f;
        constexpr float card_h = 174.0f;
        constexpr float card_w = (available - gap * 5.0f) / 6.0f;
        // Keep the console-card proportions even with only one or two installed/recent games.
        // Stretching a pair of cards across the full TV made the Home look like a debug dashboard.
        const float row_x = 72.0f;
        for (int i = 0; i < shown; ++i)
        {
            const Recent &recent = home_.recents[static_cast<std::size_t>(i)];
            const Rect r{row_x + (card_w + gap) * static_cast<float>(i), 750.0f, card_w, card_h};
            const float f = focus(kHomeRecentFirst + i);
            begin_lift(r, f, 0.030f);

            // Artwork first, then overlays, then focus. This keeps the hover border visible instead
            // of letting a late texture draw hide it.
            plate_rest(c, kTilePlate, r);
            const std::string& art = !recent.screenshot.empty() ? recent.screenshot :
                                     (!recent.hero.empty() ? recent.hero : recent.cover);
            cover_crop(c, art, {r.x + 4.0f, r.y + 4.0f, r.w - 8.0f, r.h - 8.0f}, 20.0f, 0.28f);
            list.gradient_rect({r.x + 4.0f, r.y + r.h * 0.40f, r.w - 8.0f, r.h * 0.56f}, 20.0f,
                               theme::kScrim.with_alpha(0.0f), theme::kScrim.with_alpha(0.92f));

            const float title_size = shown <= 2 ? 22.0f : 18.0f;
            const float title_y = r.y + r.h - 34.0f;
            // Soft text shadow like the approved mock-up's caption treatment.
            text_shrink(c, recent.title, r.x + 22.0f + 1.5f,
                        baseline(title_y + 1.5f, 28.0f, title_size), title_size,
                        Color::rgb(0x000000, 0.72f), r.w - 44.0f);
            text_shrink(c, recent.title, r.x + 22.0f,
                        baseline(title_y, 28.0f, title_size), title_size,
                        theme::kTitle, r.w - 44.0f);

            if (recent.max_players > 0)
            {
                const Rect icon{r.x + r.w - 79.0f, r.y + r.h - 33.0f, 34.0f, 23.0f};
                controller_icon(c, icon, 1.0f);
                text(c, "×" + std::to_string(recent.max_players), r.x + r.w - 18.0f,
                     baseline(r.y + r.h - 31.0f, 20.0f, 15.0f), 15.0f,
                     theme::kTitle, Align::right);
            }

            if (f > 0.01f)
                list.shadow({r.x - 5.0f, r.y - 5.0f, r.w + 10.0f, r.h + 10.0f},
                            24.0f, 34.0f,
                            gfx::mix(theme::kBlue, theme::kSun, 0.45f).with_alpha(0.18f * f));
            plate_focus(c, kTilePlate, r, f);
            list.pop_transform();
        }
    }
    end_band();

    // ---- footer ----
    begin_band(4, 0.0f);
    list.rounded_rect({72.0f, 970.0f, 1776.0f, 1.0f}, 0.0f, theme::kText.with_alpha(0.11f));
    if (home_focus_ == kHomeQuickPanel)
    {
        static constexpr Hint kQuickPanelHints[] = {
            {Pad::cross, TR("Open quick settings")}, {Pad::dpad, TR("Navigate")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kQuickPanelHints, 3, 72.0f, 1000.0f, theme::kMuted, 1200.0f);
    }
    else if (home_focus_ >= kHomeQuickFirst && home_focus_ < kHomeQuickFirst + kHomeQuickCount)
    {
        if (home_quick_edit_ == home_focus_ - kHomeQuickFirst)
        {
            static constexpr Hint kQuickEditHints[] = {
                {Pad::leftright, TR("Change")}, {Pad::cross, TR("Done")}, {Pad::circle, TR("Done")}};
            draw_hints(c, kQuickEditHints, 3, 72.0f, 1000.0f, theme::kMuted, 1200.0f);
        }
        else
        {
            static constexpr Hint kQuickBrowseHints[] = {
                {Pad::cross, TR("Edit")}, {Pad::dpad, TR("Navigate")}, {Pad::circle, TR("Back")}};
            draw_hints(c, kQuickBrowseHints, 3, 72.0f, 1000.0f, theme::kMuted, 1200.0f);
        }
    }
    else if (home_focus_ == kHomeCache)
    {
        static constexpr Hint kCacheHints[] = {
            {Pad::cross, TR("Clear caches")}, {Pad::leftright, TR("Switch card")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kCacheHints, 3, 72.0f, 1000.0f, theme::kMuted, 1200.0f);
    }
    else if (home_focus_ == kHomeStorage)
    {
        static constexpr Hint kStorageHints[] = {
            {Pad::cross, TR("Open storage")}, {Pad::leftright, TR("Switch card")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kStorageHints, 3, 72.0f, 1000.0f, theme::kMuted, 1200.0f);
    }
    else
    {
        static constexpr Hint kHints[] = {
            {Pad::cross, TR("Select")}, {Pad::triangle, TR("Game settings")}, {Pad::dpad, TR("Navigate")}};
        draw_hints(c, kHints, 3, 72.0f, 1000.0f, theme::kMuted, 1200.0f);
    }
    text(c, home_.system_status, 1848.0f, 1007.0f, theme::kSmall, theme::kMeta, Align::right);
    end_band();
}

} // namespace pe::ui
