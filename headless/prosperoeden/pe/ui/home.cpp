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
constexpr int kHomeRecentMax = 7;
constexpr int kHomeQuickPanel = kHomeRecentFirst + kHomeRecentMax; // 12
constexpr int kHomeQuickFirst = kHomeQuickPanel + 1;               // 13
constexpr int kHomeQuickCount = 7;
constexpr int kHomeStorage = kHomeQuickFirst + kHomeQuickCount;    // 20
constexpr int kHomeControllers = kHomeStorage + 1;                 // 21
constexpr int kHomeFullSettings = kHomeControllers + 1;            // 22

enum class HomeIcon { performance, display, output, mode, resolution, filter, antialias, storage, cache, language, controller, settings };

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
    case HomeIcon::controller:
        // Larger white DualSense; keep the utility-card's label untouched.
        // The icon is inside a 1.65x transform, so its actual visible size
        // becomes about 73x50 in the 96px-high home card.
        dualsense_icon(c, {left - 10.0f, cy - 15.0f, 44.0f, 30.0f}, theme::kTitle, 1.0f);
        break;
    case HomeIcon::settings:
        settings_gear(c, left + 12.0f, cy, 10.0f, ink);
        break;
    }
}

// The four controllers, at the right of the hero beside its buttons.
constexpr float kPadsRight = 1768.0f;
Rect pad_rect(int player)
{
    return {kPadsRight - 354.0f + 94.0f * static_cast<float>(player), 410.0f, 72.0f, 50.0f};
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
    if (title_id == 0) {
        home_game_settings_ = GameSettings{};
        home_game_docked_ = true;
    } else {
        const auto cached = home_settings_cache_.find(title_id);
        if (cached != home_settings_cache_.end()) {
            home_game_settings_ = cached->second.first;
            home_game_docked_ = cached->second.second;
        } else {
            home_game_settings_ = services_.game_settings(title_id);
            home_game_docked_ = services_.docked(title_id);
            home_settings_cache_.emplace(title_id,
                                         std::make_pair(home_game_settings_, home_game_docked_));
        }
    }
    start_home_media();
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
        // Match the actual effective per-title preset displayed by the
        // Home chips. Falling back to raw global values here made the first
        // quick-setting arrow appear to do nothing on authored profiles.
        const bool authored_global = prefs_.performance_profile >= 0 &&
                                     prefs_.performance_profile < kAuthoredVideoProfiles;
        const auto base = VideoPresetForTitle(title_id,
            authored_global ? prefs_.performance_profile : 1);
        const int base_renderer = authored_global ? base.renderer : prefs_.renderer;
        const int base_output = authored_global ? base.output : prefs_.output;
        const int base_resolution = authored_global ? base.resolution : prefs_.resolution;
        const int base_filter = authored_global ? base.filter : prefs_.filter;
        const int base_aa = authored_global ? base.anti_aliasing : prefs_.anti_aliasing;
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
                    next.performance_profile : prefs_.performance_profile;
                ApplyVideoPreset(next, CycleVideoPreset(current, step), title_id);
            }
            else if (row == 1)
            {
                const int current = next.renderer >= 0 ? next.renderer : base_renderer;
                next.renderer = current == 0 ? 1 : 0;
                RefreshVideoProfile(next, prefs_, title_id);
            }
            else if (row == 2)
            {
                const int current = next.output >= 0 ? next.output : base_output;
                next.output = (current + step + 3) % 3;
                RefreshVideoProfile(next, prefs_, title_id);
            }
            else if (row == 3)
            {
                const int count = static_cast<int>(services_.resolution_labels().size());
                if (count <= 0) return;
                const int current = next.resolution >= 0 ? next.resolution : base_resolution;
                next.resolution = (current + step + count) % count;
                RefreshVideoProfile(next, prefs_, title_id);
            }
            else if (row == 4)
            {
                const int count = static_cast<int>(services_.filter_labels().size());
                if (count <= 0) return;
                const int current = next.filter >= 0 ? next.filter : base_filter;
                next.filter = (current + step + count) % count;
                RefreshVideoProfile(next, prefs_, title_id);
            }
            else
            {
                const int count = static_cast<int>(services_.anti_aliasing_labels().size());
                if (count <= 0) return;
                const int current = next.anti_aliasing >= 0 ?
                    next.anti_aliasing : base_aa;
                next.anti_aliasing = (current + step + count) % count;
                RefreshVideoProfile(next, prefs_, title_id);
            }
        }
        saved = services_.set_game_settings(title_id, next);
        if (saved) {
            home_game_settings_ = next;
            home_game_docked_ = next.console_mode >= 0 ? next.console_mode == 1 : services_.docked(title_id);
            // refresh_home_hero() immediately follows this save. Keep the
            // cached per-title record coherent to avoid a second disk read.
            home_settings_cache_[title_id] = {home_game_settings_, home_game_docked_};
            // Same title may also be in the Library. Keep its worker-owned
            // display snapshot consistent with the explicit Home edit.
            for (Game& installed : games_)
                if (installed.title_id == title_id)
                    installed.docked = home_game_docked_;
            // An older in-flight library scan may otherwise overwrite this
            // freshly saved mode after it finishes.
            if (scan_.valid()) docked_refresh_after_scan_ = true;
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
        else if (focus >= kHomeQuickFirst && focus < kHomeQuickFirst + kHomeQuickCount)
            focus = focus > kHomeQuickFirst ? focus - 1 : kHomeQuickPanel;
        else if (focus == kHomeQuickPanel || focus == kHomeStorage ||
                 focus == kHomeControllers || focus == kHomeFullSettings)
            focus = recent_count > 0 ? kHomeRecentFirst : (hero_ready ? kHomeHero : kHomeNavRecent);
        break;
    case Key::down:
        if (focus >= kHomeNavLibrary && focus <= kHomeNavSettings)
        {
            if (hero_ready)
                focus = kHomeHero;
        }
        else if (focus == kHomeHero || focus == kHomeDetails)
        {
            focus = recent_count > 0 ? kHomeRecentFirst : kHomeQuickPanel;
        }
        else if (focus >= kHomeRecentFirst && focus < kHomeRecentFirst + recent_count)
        {
            focus = kHomeQuickPanel;
        }
        else if (focus >= kHomeQuickFirst && focus < kHomeQuickFirst + kHomeQuickCount)
        {
            if (focus < kHomeQuickFirst + kHomeQuickCount - 1)
                ++focus;
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
                focus = focus == kHomeHero ? kHomeDetails : kHomeHero;
        }
        else if (focus == kHomeQuickPanel || focus == kHomeStorage ||
                 focus == kHomeControllers || focus == kHomeFullSettings)
        {
            constexpr std::array utility{kHomeQuickPanel, kHomeStorage, kHomeControllers, kHomeFullSettings};
            const auto it = std::find(utility.begin(), utility.end(), focus);
            const int position = it == utility.end() ? 0 : static_cast<int>(it - utility.begin());
            // The first utility is not a navigation trap: Left returns to the
            // hero actions, even when quick settings have not been opened.
            focus = position == 0 && delta < 0 ?
                (hero_ready ? kHomeDetails : (recent_count > 0 ? kHomeRecentFirst : kHomeNavRecent)) :
                utility[static_cast<std::size_t>((position + delta + 4) % 4)];
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
        else if (focus == kHomeQuickPanel || focus == kHomeStorage ||
                 focus == kHomeControllers || focus == kHomeFullSettings)
        {
            focus = recent_count > 0 ? kHomeRecentFirst : (hero_ready ? kHomeHero : kHomeNavRecent);
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
        if (focus == kHomeControllers)
        {
            prefs_ = services_.preferences();
            open_mapping(false);
            cue(Cue::open);
            return;
        }
        if (focus == kHomeStorage)
        {
            open(Screen::files, true);
            enter_files();
            return;
        }
        if (focus == kHomeFullSettings)
        {
            open(Screen::settings, true);
            prefs_ = services_.preferences();
            section_.snap(1.0f);
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
    // Controller join/leave status is informational, not a game input
    // sample. Poll its native service at 10 Hz, while all icon springs
    // and actual controller button input continue at the display rate.
    // This removes repeated native status calls from most UI frames.
    controller_poll_elapsed_ += dt;
    const bool poll = !controllers_known_ || controller_poll_elapsed_ >= 0.10f;
    const unsigned now = poll ? (services_.controllers() & 0xfu) : controllers_;
    if (poll)
        controller_poll_elapsed_ = 0.0f;
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
    text(c, tr("CONTROLLERS"), kPadsRight, baseline(376.0f, 30.0f, theme::kSmall), theme::kSmall,
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
        text(c, number, r.x + r.w * 0.5f, baseline(463.0f, 26.0f, theme::kSmall), theme::kSmall,
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
    const std::string &hero_banner = hero_recent != nullptr ? hero_recent->hero : home_.last_hero;
    const std::string &hero_screenshot = hero_recent != nullptr ? hero_recent->screenshot : home_.last_screenshot;
    const std::string hero_artwork = !hero_banner.empty() ? hero_banner : hero_screenshot;
    const std::string &hero_addons = hero_recent != nullptr ? hero_recent->addons : home_.last_addons;
    const std::string &hero_language = hero_recent != nullptr ? hero_recent->language : home_.last_language;
    const std::string &hero_intro = hero_recent != nullptr ? hero_recent->intro : home_.last_intro;
    const std::string &hero_description =
        hero_recent != nullptr ? hero_recent->description : home_.last_description;
    const std::uint64_t hero_title_id = hero_recent != nullptr ? hero_recent->title_id : home_.last_title_id;
    int hero_max_players = hero_recent != nullptr ? hero_recent->max_players : home_.last_max_players;
    const bool hero_ready = ready && !hero_file.empty();
    const auto focus = [&](int index) { return home_springs_[static_cast<std::size_t>(index)].value; };
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

    // Pixel-layout reference: "Accueil Eden _ Zelda et bibliothèque Switch.png".
    // Full-bleed game scene behind navigation; actions float on the artwork.
    // Below it: real recent game artwork, four utilities, concise system footer.
    // No always-visible diagnostic/sidebar cards and no bordered game hero.
    const Rect hero{0.0f, 0.0f, 1920.0f, 1080.0f};

    // ---- full-bleed cinematic game hero (no giant rounded panel) ----
    begin_band(1, 18.0f);
    // Non-blocking background: if an Nlib banner has not yet loaded, show
    // the actual Eden wallpaper already drawn underneath, NOT a solid
    // placeholder covering the entire TV. The normal texture cache retries
    // asynchronously when Nlib finishes its atomic file write.
    if (!hero_artwork.empty()) {
        const Cover hero_picture = c.textures.cover(hero_artwork, 1920.0f);
        if (hero_picture.texture != 0) {
            const float source = std::max(0.01f, hero_picture.aspect);
            constexpr float target = 1920.0f / 1080.0f;
            Rect uv{0.0f, 0.0f, 1.0f, 1.0f};
            if (source > target) {
                uv.w = target / source;
                uv.x = (1.0f - uv.w) * 0.5f;
            } else if (source < target) {
                uv.h = source / target;
                uv.y = (1.0f - uv.h) * 0.5f;
            }
            list.image(hero_picture.texture, hero, uv,
                       kWhite.with_alpha(tween::cubic_out(hero_picture.age / 0.30f)));
        }
    }
    // Full-screen object-fit: cover above: image keeps its original ratio and
    // is centre-cropped, never stretched or confined to a hero "block".
    // The approved mock-up needs a dark dispersion on BOTH the left and bottom.
    // Two long translucent fades preserve the full hero scene in the centre.
    list.hgradient_rect(hero, 0.0f,
                        theme::kScrim.with_alpha(0.91f),
                        theme::kScrim.with_alpha(0.025f));
    list.hgradient_rect({0.0f, 0.0f, 1000.0f, 1080.0f}, 0.0f,
                        theme::kBase.with_alpha(0.31f),
                        theme::kBase.with_alpha(0.0f));
    // A subtle dark lower half keeps recent covers, utilities and status
    // readable without adding a hard-edged opaque rectangle to the wallpaper.
    list.gradient_rect({0.0f, 325.0f, 1920.0f, 755.0f}, 0.0f,
                       theme::kScrim.with_alpha(0.0f),
                       theme::kBase.with_alpha(0.96f));
    // The header must survive bright Nlib skies: fade, never an opaque
    // navigation bar or a game-specific darkness adjustment.
    list.gradient_rect({0.0f, 0.0f, 1920.0f, 175.0f}, 0.0f,
                       theme::kBase.with_alpha(0.73f),
                       theme::kBase.with_alpha(0.0f));

    text(c, hero_recent != nullptr ? tr("SELECTED GAME") : tr("CONTINUE PLAYING"),
         90.0f, baseline(133.0f, 30.0f, theme::kSmall),
         theme::kSmall, theme::kLimePale, Align::left, 3.0f);
    // One shared left-aligned content span for title, description and
    // action/chip rail. Never wrap a title at 1030px when the hero has
    // enough horizontal room for an intact one-line title (e.g. BOTW).
    // Keep 150px for the TV safe area at the right edge.
    constexpr float kHeroContentWidth = 1680.0f; // x=90 .. 1770
    const std::string title_label =
        hero_file.empty() ? std::string{tr("Your next adventure")} : hero_title;
    constexpr float kTitleSize = 76.0f;
    constexpr float kMinOneLineScale = 0.72f;
    if (text_width(c, title_label, kTitleSize) <= kHeroContentWidth / kMinOneLineScale)
        text_shrink(c, title_label, 90.0f, baseline(175.0f, 96.0f, kTitleSize),
                    kTitleSize, theme::kTitle, kHeroContentWidth, Align::left,
                    0.0f, kMinOneLineScale);
    else
        text_block(c, title_label, 90.0f, baseline(166.0f, 54.0f, 51.0f),
                   51.0f, 53.0f, theme::kTitle, kHeroContentWidth, 2, 0.87f);
    const bool hero_caption_warning = hero_recent == nullptr && home_.last_caption_warning;
    // A game-return screen must not silently swap a full Nlib description
    // for a short English marketing slogan ("The world's game...") merely
    // because `intro` exists. Prefer the actual localized title description,
    // but always show a genuine missing-language/ROM warning first.
    const std::string hero_caption =
        hero_file.empty() ? std::string{tr("Choose a game from your library.")} :
        hero_caption_warning ? home_.last_caption :
        !hero_description.empty() ? hero_description :
        !hero_intro.empty() ? hero_intro :
        hero_recent != nullptr ? std::string{tr("Recently played")} : home_.last_caption;
    if (hero_caption_warning)
        notice_block(c, hero_caption, 90.0f, baseline(280.0f, 27.0f, 21.0f),
                     21.0f, 25.0f, theme::kWarning, kHeroContentWidth, 2, true);
    else
        text_block(c, hero_caption, 90.0f, baseline(280.0f, 27.0f, 21.0f),
                   21.0f, 25.0f, theme::kBody, kHeroContentWidth, 2, 0.86f);
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
                    90.0f, baseline(341.0f, 25.0f, theme::kSmall), theme::kSmall,
                    theme::kMeta, kHeroContentWidth);

    const char *first = hero_ready ? tr("Play") : tr("Open library");
    const Rect continue_rect{90.0f, 390.0f, 348.0f, 70.0f};
    const Rect details_rect{454.0f, 390.0f, 78.0f, 70.0f};
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
    hero_button(details_rect, "...", focus(kHomeDetails), hero_ready);

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
    // Keep real local-player capacity beside Play/details, then the graphical
    // profile chips in the same horizontal metadata rail. If Nlib has no
    // verified capacity, do not reserve space or invent a count.
    float chip_x = hero_max_players > 0 ? 774.0f : 570.0f;
    for (const auto &chip : chips)
    {
        const float w = std::clamp(text_width(c, chip, 18.0f) + 30.0f, 92.0f, 210.0f);
        list.rounded_rect({chip_x, 405.0f, w, 38.0f}, 19.0f, theme::kPanel.with_alpha(0.78f));
        text_shrink(c, chip, chip_x + w * 0.5f, baseline(405.0f, 38.0f, 18.0f), 18.0f,
                    theme::kLimePale, w - 18.0f, Align::center, 0.0f, 0.72f);
        chip_x += w + 10.0f;
    }
    if (hero_max_players > 0)
    {
        // Same row as Play/details, BEFORE the profile/renderer/output chips;
        // never float this datum alone over the right-hand game illustration.
        const Rect players_chip{552.0f, 406.0f, 210.0f, 36.0f};
        list.bordered_rect(players_chip, 17.0f, theme::kPanel.with_alpha(0.82f), 1.0f,
                           theme::kPanelEdge.with_alpha(0.58f));
        dualsense_icon(c, {players_chip.x + 8.0f, players_chip.y + 3.0f, 45.0f, 30.0f},
                       theme::kTitle, 1.0f);
        const std::string local_players =
            fill(tr("Max. players: {0}"), {std::to_string(hero_max_players)});
        // Centre the label within the space *after* its gamepad glyph, not
        // left-aligned against the badge edge.
        const Rect label_area{players_chip.x + 56.0f, players_chip.y,
                              players_chip.w - 64.0f, players_chip.h};
        text_shrink(c, local_players, label_area.x + label_area.w * 0.5f,
                    baseline(players_chip.y, players_chip.h, 15.0f), 15.0f,
                    theme::kTitle, label_area.w - 4.0f, Align::center);
    }
    end_band();

    // ---- quick settings overlay: opened from the utility card, never permanent ----
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
    const bool quick_open =
        home_focus_ >= kHomeQuickFirst && home_focus_ < kHomeQuickFirst + kHomeQuickCount;
    if (quick_open)
    {
        begin_band(2, 18.0f);
        const Rect quick_sheet{1110.0f, 100.0f, 710.0f, 396.0f};
        list.shadow({quick_sheet.x - 10.0f, quick_sheet.y - 8.0f,
                     quick_sheet.w + 20.0f, quick_sheet.h + 20.0f},
                    32.0f, 60.0f, theme::kLime.with_alpha(0.18f));
        glass(c, quick_sheet, 28.0f, theme::kGlass.with_alpha(0.92f),
              theme::kPanelEdge.with_alpha(0.82f), 1.2f);
        text(c, tr("QUICK SETTINGS"), quick_sheet.x + 30.0f,
             baseline(quick_sheet.y + 22.0f, 32.0f, theme::kSmall),
             theme::kSmall, theme::kLimePale, Align::left, 3.0f);
        text_shrink(c, hero_title, quick_sheet.x + quick_sheet.w - 30.0f,
                    baseline(quick_sheet.y + 22.0f, 32.0f, 16.0f), 16.0f,
                    theme::kMeta, 300.0f, Align::right);
        for (int i = 0; i < kHomeQuickCount; ++i)
        {
            const float y = quick_sheet.y + 76.0f + static_cast<float>(i) * 42.0f;
            const Rect row_box{quick_sheet.x + 18.0f, y - 7.0f, quick_sheet.w - 36.0f, 36.0f};
            const float f = focus(kHomeQuickFirst + i);
            if (i != 0)
                list.rounded_rect({quick_sheet.x + 32.0f, y - 9.0f,
                                   quick_sheet.w - 64.0f, 1.0f},
                                  0.0f, theme::kRule.with_alpha(0.38f));
            if (f > 0.01f)
                plate_focus(c, kRowPlate, row_box, f);
            const bool editing = home_quick_edit_ == i;
            if (editing)
                list.bordered_rect(row_box, 16.0f, theme::kPanel.with_alpha(0.16f), 2.0f,
                                   theme::kLime.with_alpha(0.94f));
            home_icon(c, quick_rows[i].icon, quick_sheet.x + 34.0f, y + 10.0f,
                      gfx::mix(theme::kMeta, theme::kTitle, f));
            text_shrink(c, quick_rows[i].label, quick_sheet.x + 74.0f,
                        baseline(y - 2.0f, 28.0f, 17.0f), 17.0f,
                        gfx::mix(theme::kMuted, theme::kTitle, f), 240.0f);
            text_shrink(c, quick_rows[i].value, quick_sheet.x + quick_sheet.w - 50.0f,
                        baseline(y - 2.0f, 28.0f, 17.0f), 17.0f,
                        gfx::mix(theme::kAccentTeal, theme::kTitle, f), 250.0f, Align::right);
        }
        end_band();
    }

    // ---- recently played: seven-ish large artwork tiles, titles BELOW the covers ----
    begin_band(3, 18.0f);
    if (!home_.status.empty())
    {
        const Rect panel{60.0f, 606.0f, 1800.0f, 182.0f};
        const Color accent = home_.launch_failed ? theme::kWarning : theme::kLime;
        glass(c, panel, 24.0f, theme::kPanel.with_alpha(0.84f), accent.with_alpha(0.32f), 0.7f);
        list.rounded_rect({panel.x + 18.0f, panel.y + 24.0f, 5.0f, panel.h - 48.0f}, 2.0f, accent);
        notice_block(c, home_.status, panel.x + 48.0f,
                     baseline(panel.y + 38.0f, 38.0f, theme::kText24),
                     theme::kText24, 36.0f, theme::kText, panel.w - 86.0f, 3,
                     home_.launch_failed);
    }
    else
    {
        text(c, tr("RECENTLY PLAYED"), 76.0f, baseline(514.0f, 28.0f, theme::kSmall),
             theme::kSmall, theme::kTitle, Align::left, 3.0f);
        if (home_.recents.empty())
            text(c, tr("Games you launch will appear here."), 76.0f,
                 baseline(620.0f, 34.0f, theme::kText24), theme::kText24, theme::kMuted);

        const int shown = std::min<int>(kHomeRecentMax, static_cast<int>(home_.recents.size()));
        constexpr float available = 1770.0f;
        constexpr float gap = 16.0f;
        constexpr float card_h = 214.0f;
        // Real games only; keep cards at console-cover scale even with 1-3 titles.
        constexpr float card_w = (available - gap * 6.0f) / 7.0f;
        const float row_x = 76.0f;
        for (int i = 0; i < shown; ++i)
        {
            const Recent &recent = home_.recents[static_cast<std::size_t>(i)];
            const Rect r{row_x + (card_w + gap) * static_cast<float>(i), 551.0f, card_w, card_h};
            const float f = focus(kHomeRecentFirst + i);
            begin_lift(r, f, 0.030f);
            // Paint bloom BEFORE the opaque cover, not over its pixels.
            if (f > 0.01f) {
                list.shadow({r.x - 8.0f, r.y - 8.0f, r.w + 16.0f, r.h + 16.0f},
                            26.0f, 33.0f, theme::kSun.with_alpha(0.33f * f));
                list.shadow({r.x - 14.0f, r.y - 14.0f, r.w + 28.0f, r.h + 28.0f},
                            29.0f, 39.0f, theme::kLime.with_alpha(0.27f * f));
            }
            plate_rest(c, kTilePlate, r);
            // Reference uses recognisable game-key art, not a random gameplay
            // screenshot or a cropped panoramic banner on the small tile.
            const std::string& art = !recent.cover.empty() ? recent.cover :
                                     (!recent.hero.empty() ? recent.hero : recent.screenshot);
            cover_crop(c, art, {r.x + 4.0f, r.y + 4.0f, r.w - 8.0f, r.h - 8.0f}, 20.0f, 0.32f);
            const Cover picture = c.textures.cover(art, std::max(card_w - 8.0f, card_h - 8.0f));
            if (picture.texture == 0) {
                const bool fetching = recent.title_id != 0 &&
                    (home_media_scan_title_id_ == recent.title_id ||
                     media_scan_title_id_ == recent.title_id);
                text_shrink(c, tr(fetching || !picture.missing ?
                                      "Loading artwork" : "Artwork unavailable"),
                            r.x + card_w * 0.5f,
                            baseline(r.y + 65.0f, 34.0f, 16.0f), 16.0f,
                            theme::kMuted, card_w - 22.0f, Align::center);
            }
            // Never bury a game's title inside a dark overlay on its artwork.
            text_shrink(c, recent.title, r.x + card_w * 0.5f,
                        baseline(r.y + r.h + 6.0f, 32.0f, 20.0f), 20.0f,
                        theme::kTitle, card_w - 8.0f, Align::center);
            // Local-player capacity is shown in the hero metadata, not on this tile.

            // Only the luminous outline is above the game cover.
            plate_focus(c, kTilePlate, r, f);
            list.pop_transform();
        }
    }
    end_band();

    // ---- utility cards: the four Home actions from the approved console-style mock-up ----
    begin_band(4, 14.0f);
    constexpr float utility_x = 60.0f;
    constexpr float utility_y = 825.0f;
    constexpr float utility_gap = 16.0f;
    constexpr float utility_w = (1800.0f - utility_gap * 3.0f) / 4.0f;
    constexpr float utility_h = 96.0f;
    const auto utility_card = [&](int position, int index, HomeIcon icon,
                                  std::string_view label, const std::string& value)
    {
        const Rect r{utility_x + (utility_w + utility_gap) * static_cast<float>(position),
                     utility_y, utility_w, utility_h};
        const float f = focus(index);
        begin_lift(r, f, 0.020f);
        plate_rest(c, kTilePlate, r);
        if (f > 0.01f)
            plate_focus(c, kTilePlate, r, f);
        // The approved TV mock-up uses full-size utility symbols, not the
        // 24 px diagnostic glyphs that previously looked almost invisible.
        // Scale only the vector icon (never the text or hit target).
        list.push_transform(1.65f, r.x + 41.0f, r.y + r.h * 0.5f, 0.0f, 0.0f);
        home_icon(c, icon, r.x + 29.0f, r.y + r.h * 0.5f,
                  icon == HomeIcon::controller ? theme::kTitle :
                  gfx::mix(theme::kMeta, theme::kLimePale, f));
        list.pop_transform();
        text_shrink(c, label, r.x + 108.0f, baseline(r.y + 20.0f, 30.0f, 20.0f),
                    20.0f, theme::kTitle, r.w - 131.0f);
        text_shrink(c, value, r.x + 108.0f, baseline(r.y + 52.0f, 30.0f, 16.0f),
                    16.0f, gfx::mix(theme::kMuted, theme::kAccentTeal, f), r.w - 131.0f);
        list.pop_transform();
    };

    unsigned connected = 0;
    for (unsigned player = 0; player < 4; ++player)
        connected += (controllers_ >> player) & 1u;
    const std::string quick_value = profile + " · " + renderer + " · " + resolution;
    const std::string storage_value = home_diagnostics_.storage_root.empty() ?
        std::string{tr("Storage not configured")} :
        std::string{tr("Games and cache")};
    const std::string controller_value =
        connected > 0 ? "DualSense ×" + std::to_string(connected) : std::string{"DualSense"};
    const std::string settings_value = std::string{tr("Video")} + " · " + tr("Audio") + " · " + tr("System");

    utility_card(0, kHomeQuickPanel, HomeIcon::performance, tr("Quick settings"), quick_value);
    utility_card(1, kHomeStorage, HomeIcon::storage, tr("Storage"), storage_value);
    utility_card(2, kHomeControllers, HomeIcon::controller, tr("Controllers"), controller_value);
    utility_card(3, kHomeFullSettings, HomeIcon::settings, tr("Settings"), settings_value);
    end_band();

    // ---- compact system strip; never invent CPU/GPU/RAM/60FPS metrics ----
    begin_band(5, 0.0f);
    list.rounded_rect({60.0f, 940.0f, 1800.0f, 1.0f},
                      0.0f, theme::kText.with_alpha(0.24f));
    text_shrink(c, home_.system_status, 80.0f,
                baseline(950.0f, 30.0f, 18.0f), 18.0f,
                theme::kTitle, 420.0f);
    text_shrink(c, std::string{tr("CACHE")} + ": " +
                  (home_diagnostics_.shader_caches.empty() ?
                   std::string{tr("Unknown")} : home_diagnostics_.shader_caches),
                520.0f, baseline(950.0f, 30.0f, 16.0f),
                16.0f, theme::kMeta, 470.0f);
    const std::string storage_display =
        !home_diagnostics_.used_space.empty() &&
        !home_diagnostics_.total_space.empty() ?
            home_diagnostics_.used_space + " / " + home_diagnostics_.total_space :
            (home_diagnostics_.storage_root.empty() ?
                std::string{tr("Unknown")} : std::string{tr("Storage ready")});
    text_shrink(c, std::string{tr("Storage")} + ": " + storage_display,
                1020.0f, baseline(950.0f, 30.0f, 16.0f), 16.0f,
                theme::kMeta, 550.0f);
    if (home_focus_ == kHomeQuickPanel)
    {
        static constexpr Hint kQuickPanelHints[] = {
            {Pad::cross, TR("Open quick settings")}, {Pad::dpad, TR("Navigate")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kQuickPanelHints, 3, 60.0f, 1020.0f, theme::kMuted, 1200.0f);
    }
    else if (home_focus_ >= kHomeQuickFirst && home_focus_ < kHomeQuickFirst + kHomeQuickCount)
    {
        if (home_quick_edit_ == home_focus_ - kHomeQuickFirst)
        {
            static constexpr Hint kQuickEditHints[] = {
                {Pad::leftright, TR("Change")}, {Pad::cross, TR("Done")}, {Pad::circle, TR("Done")}};
            draw_hints(c, kQuickEditHints, 3, 60.0f, 1020.0f, theme::kMuted, 1200.0f);
        }
        else
        {
            static constexpr Hint kQuickBrowseHints[] = {
                {Pad::cross, TR("Edit")}, {Pad::dpad, TR("Navigate")}, {Pad::circle, TR("Back")}};
            draw_hints(c, kQuickBrowseHints, 3, 60.0f, 1020.0f, theme::kMuted, 1200.0f);
        }
    }
    else if (home_focus_ == kHomeControllers)
    {
        static constexpr Hint kControllerHints[] = {
            {Pad::cross, TR("Controller mapping")}, {Pad::leftright, TR("Switch card")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kControllerHints, 3, 60.0f, 1020.0f, theme::kMuted, 1200.0f);
    }
    else if (home_focus_ == kHomeStorage)
    {
        static constexpr Hint kStorageHints[] = {
            {Pad::cross, TR("Open storage")}, {Pad::leftright, TR("Switch card")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kStorageHints, 3, 60.0f, 1020.0f, theme::kMuted, 1200.0f);
    }
    else if (home_focus_ == kHomeFullSettings)
    {
        static constexpr Hint kSettingsHints[] = {
            {Pad::cross, TR("Open settings")}, {Pad::leftright, TR("Switch card")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kSettingsHints, 3, 60.0f, 1020.0f, theme::kMuted, 1200.0f);
    }
    else
    {
        static constexpr Hint kHints[] = {
            {Pad::cross, TR("Select")}, {Pad::triangle, TR("Game settings")}, {Pad::dpad, TR("Navigate")}};
        draw_hints(c, kHints, 3, 60.0f, 1020.0f, theme::kMuted, 1200.0f);
    }
    text(c, version_, 1860.0f, 1026.0f,
         theme::kSmall, theme::kMeta, Align::right);
    end_band();

    // Header must be composited AFTER the full-bleed hero image, otherwise
    // the artwork paints over the navigation, brand and focus ring.
    begin_band(0, -16.0f);
    const int header_focus =
        home_focus_ >= kHomeNavLibrary && home_focus_ <= kHomeNavSettings ? home_focus_ : -1;
    draw_top_nav(c, 0, header_focus,
                 header_focus >= 0 ? focus(header_focus) : 0.0f);
    end_band();
}

} // namespace pe::ui
