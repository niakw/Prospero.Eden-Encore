// ProsperoEden - Launcher library: the game list, its details and per-game settings.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include "pe/ui/launcher.hpp"
#include "pe/ui/video_presets.hpp"

#include "pe/core/log.hpp"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <exception>
#include <iterator>
#include <new>
#include <string>

namespace pe::ui
{

using audio::Cue;

namespace
{

constexpr Rect kDialog{550.0f, 180.0f, 820.0f, 720.0f};

// The game settings dialog's rows, and the window that shows five of them (also the Mods list's).
enum GameRow : int
{
    row_mode,
    row_renderer,
    row_performance,
    row_output,
    row_resolution,
    row_filter,
    row_fsr_sharpness,
    row_anti_aliasing,
    row_refresh,
    row_controls,
    row_mods,
    row_save, // in builds that move saves
};
constexpr float kDialogRowsTop = 334.0f;
constexpr float kDialogRowPitch = 96.0f;
constexpr float kDialogRowHeight = 94.0f;
constexpr int kDialogRowsShown = 5;
constexpr Rect kDialogWindow{592.0f, kDialogRowsTop, 736.0f,
                             kDialogRowPitch * (kDialogRowsShown - 1) + kDialogRowHeight};
constexpr float kDialogHints = 848.0f;

std::string controller_profile_name(int layout, const ButtonMapping& mapping)
{
    const bool custom = mapping_is_custom(mapping, layout);
    if (layout == 1)
        return custom ? tr("Custom Switch") : tr("Switch");
    return custom ? tr("Custom PS5") : tr("PlayStation");
}

} // namespace

void Launcher::start_scan()
{
    if (!scan_cancel_.load(std::memory_order_acquire) &&
        !scan_.valid() && home_.setup_ready)
        scan_ = std::async(std::launch::async, [this] {
            std::vector<Game> games = services_.games();
            if (scan_cancel_.load(std::memory_order_acquire))
                return std::vector<Game>{};
            // Reading mod folders / disabled-mod settings for each installed
            // title used to happen inside apply_games() on the UI update
            // thread, potentially scanning hundreds of directories at once.
            // Populate the immutable game-list snapshot on this worker instead.
            unsigned mod_scan_errors = 0;
            for (Game &game : games) {
                if (scan_cancel_.load(std::memory_order_acquire)) break;
                if (game.title_id == 0) continue;
                try {
                    const std::vector<Mod> mods = services_.mods(game.title_id);
                    game.mods = static_cast<int>(mods.size());
                    game.mods_enabled = mods.empty() || services_.mods_enabled(game.title_id);
                    game.mods_on = !game.mods_enabled ? 0 : static_cast<int>(
                        std::count_if(mods.begin(), mods.end(),
                                      [](const Mod &mod) { return mod.enabled; }));
                } catch (const std::bad_alloc&) {
                    throw; // never disguise memory exhaustion as an absent mod
                } catch (const std::exception& error) {
                    // One damaged/inaccessible mod folder must not discard the
                    // entire game list. Keep defaults for that title only.
                    if (mod_scan_errors++ < 3)
                        sys::log("mod scan title=%llx: %s",
                                 static_cast<unsigned long long>(game.title_id), error.what());
                }
            }
            return games;
        });
}

void Launcher::finish_scan(bool wait)
{
    if (!scan_.valid())
        return;
    if (!wait && scan_.wait_for(std::chrono::seconds(0)) != std::future_status::ready)
        return;
    try
    {
        auto games = scan_.get();
        // A completed worker is still joined, but never apply its stale
        // results after a game launch has begun.
        if (!scan_cancel_.load(std::memory_order_acquire))
            apply_games(std::move(games));
    }
    catch (const std::exception &error)
    {
        sys::log("game list: %s", error.what());
        games_loaded_ = true; // the list stays as it was
    }
}

void Launcher::start_home_media()
{
    if (home_media_scan_.valid()) return;

    const Recent* recent =
        home_recent_ >= 0 && home_recent_ < static_cast<int>(home_.recents.size()) ?
            &home_.recents[static_cast<std::size_t>(home_recent_)] : nullptr;
    const std::uint64_t title_id = recent != nullptr ? recent->title_id : home_.last_title_id;
    if (title_id == 0) return;
    const auto now = std::chrono::steady_clock::now();
    const auto due = home_media_next_retry_.find(title_id);
    if (due != home_media_next_retry_.end() && now < due->second)
        return;

    // Do not infer the full Nlib media set from a banner/intro: an otherwise
    // rich-looking cached title can still be missing all three screenshots.
    Game request;
    request.title_id = title_id;
    if (recent != nullptr) {
        request.file = recent->file;
        request.name = recent->title;
        request.cover = recent->cover;
        request.hero = recent->hero;
        if (!recent->screenshot.empty()) request.screenshots.push_back(recent->screenshot);
        request.max_players = recent->max_players;
        request.intro = recent->intro;
    } else {
        request.file = home_.last_file;
        request.name = home_.last_title;
        request.cover = home_.last_cover;
        request.hero = home_.last_hero;
        if (!home_.last_screenshot.empty()) request.screenshots.push_back(home_.last_screenshot);
        request.max_players = home_.last_max_players;
        request.intro = home_.last_intro;
    }

    // An incomplete response must never blacklist this game until restart.
    // A short cooldown keeps the UI responsive without retrying every frame.
    home_media_next_retry_[title_id] = now + std::chrono::minutes(2);
    home_media_scan_title_id_ = title_id;
    home_media_scan_ = std::async(std::launch::async, [this, request = std::move(request)]() mutable {
        return services_.enrich_game_media(std::move(request));
    });
}

void Launcher::finish_home_media()
{
    if (!home_media_scan_.valid() ||
        home_media_scan_.wait_for(std::chrono::seconds(0)) != std::future_status::ready)
        return;

    try {
        Game enriched = home_media_scan_.get();
        if (enriched.artwork_changed) {
            textures_.invalidate(enriched.cover);
            textures_.invalidate(enriched.hero);
            for (const auto& path : enriched.screenshots) textures_.invalidate(path);
        }
        if (enriched.title_id == home_.last_title_id) {
            if (!enriched.cover.empty()) home_.last_cover = enriched.cover;
            if (!enriched.hero.empty()) home_.last_hero = enriched.hero;
            if (!enriched.screenshots.empty()) home_.last_screenshot = enriched.screenshots.front();
            if (enriched.max_players > 0) home_.last_max_players = enriched.max_players;
            if (!enriched.name.empty()) home_.last_title = enriched.name;
            if (!enriched.intro.empty()) home_.last_intro = enriched.intro;
            if (!enriched.description.empty()) home_.last_description = enriched.description;
        }
        for (Recent& recent : home_.recents) {
            if (recent.title_id != enriched.title_id) continue;
            if (!enriched.cover.empty()) recent.cover = enriched.cover;
            if (!enriched.hero.empty()) recent.hero = enriched.hero;
            if (!enriched.screenshots.empty()) recent.screenshot = enriched.screenshots.front();
            if (enriched.max_players > 0) recent.max_players = enriched.max_players;
            if (!enriched.name.empty()) recent.title = enriched.name;
            if (!enriched.intro.empty()) recent.intro = enriched.intro;
            if (!enriched.description.empty()) recent.description = enriched.description;
        }
        // If the library scan completed while the Home request was in flight, keep both views
        // on the same cache result without another network request.
        for (Game& game : games_) {
            if (game.title_id != enriched.title_id) continue;
            if (!enriched.cover.empty()) game.cover = enriched.cover;
            if (!enriched.hero.empty()) game.hero = enriched.hero;
            if (!enriched.screenshots.empty()) game.screenshots = enriched.screenshots;
            if (enriched.max_players > 0) game.max_players = enriched.max_players;
            if (!enriched.name.empty()) game.name = enriched.name;
            if (!enriched.intro.empty()) game.intro = enriched.intro;
            if (!enriched.description.empty()) game.description = enriched.description;
            if (!enriched.publisher.empty()) game.publisher = enriched.publisher;
            if (!enriched.developer.empty()) game.developer = enriched.developer;
            if (!enriched.release_date.empty()) game.release_date = enriched.release_date;
            if (!enriched.categories.empty()) game.categories = enriched.categories;
            break;
        }
    }
    catch (const std::exception& error)
    {
        sys::log("Nlib home media: %s", error.what());
    }
    home_media_scan_title_id_ = 0;
    // If the user selected another Recent card while this request ran, start that title now.
    start_home_media();
}

void Launcher::start_selected_media()
{
    if (media_scan_.valid() || games_.empty()) return;
    // Prefer the highlighted title but then cover ALL installed titles, even
    // those never selected. Download the complete Nlib media set per title
    // without blocking input, drawing or ROM enumeration.
    const int selected = std::clamp(library_.selected, 0, static_cast<int>(games_.size()) - 1);
    for (std::size_t offset = 0; offset < games_.size(); ++offset) {
        const auto index = (static_cast<std::size_t>(selected) + offset) % games_.size();
        const Game& game = games_[index];
        if (game.title_id == 0) continue;
        const auto now = std::chrono::steady_clock::now();
        const auto due = media_next_retry_.find(game.title_id);
        if (due != media_next_retry_.end() && now < due->second) continue;
        // Retry missing/corrupt cached artwork after a bounded cooldown rather
        // than treating the first failed HTTPS request as permanent.
        media_next_retry_[game.title_id] = now + std::chrono::minutes(5);
        media_scan_title_id_ = game.title_id;
        Game copy = game;
        media_scan_ = std::async(std::launch::async, [this, copy = std::move(copy)]() mutable {
            return services_.enrich_game_media(std::move(copy));
        });
        return;
    }
}

void Launcher::finish_selected_media()
{
    if (!media_scan_.valid() || media_scan_.wait_for(std::chrono::seconds(0)) != std::future_status::ready)
        return;
    try {
        Game enriched = media_scan_.get();
        if (enriched.artwork_changed) {
            textures_.invalidate(enriched.cover);
            textures_.invalidate(enriched.hero);
            for (const auto& path : enriched.screenshots) textures_.invalidate(path);
        }
        for (Game& game : games_) {
            if (game.title_id != enriched.title_id) continue;
            if (!enriched.cover.empty()) game.cover = std::move(enriched.cover);
            if (!enriched.hero.empty()) game.hero = std::move(enriched.hero);
            if (!enriched.screenshots.empty()) game.screenshots = std::move(enriched.screenshots);
            if (enriched.max_players > 0) game.max_players = enriched.max_players;
            if (!enriched.name.empty()) game.name = std::move(enriched.name);
            if (!enriched.intro.empty()) game.intro = std::move(enriched.intro);
            if (!enriched.description.empty()) game.description = std::move(enriched.description);
            if (!enriched.publisher.empty()) game.publisher = std::move(enriched.publisher);
            if (!enriched.developer.empty()) game.developer = std::move(enriched.developer);
            if (!enriched.release_date.empty()) game.release_date = std::move(enriched.release_date);
            if (!enriched.categories.empty()) game.categories = std::move(enriched.categories);
            break;
        }
        name_home_games();
    }
    catch (const std::exception& error)
    {
        sys::log("Nlib selected media: %s", error.what());
    }
    media_scan_title_id_ = 0;
    // If the player moved while that request was running, enrich the title highlighted now.
    start_selected_media();
}

void Launcher::apply_games(std::vector<Game> games)
{
    // The same games in the same order (the usual case) keep the list where it is; otherwise
    // the selection follows its game.
    bool same = games_loaded_ && games.size() == games_.size();
    for (std::size_t i = 0; same && i < games.size(); ++i)
        same = games[i].file == games_[i].file;
    const std::string selected = library_.selected >= 0 &&
                                 library_.selected < static_cast<int>(games_.size()) ?
                                     games_[static_cast<std::size_t>(library_.selected)].file :
                                     std::string{};
    games_ = std::move(games);
    games_loaded_ = true;
    // Mod counts were resolved by the background scan; never perform a
    // second synchronous per-title disk walk while applying the list.
    if (!same)
    {
        int index = 0;
        for (int i = 0; i < static_cast<int>(games_.size()); ++i)
            if (games_[static_cast<std::size_t>(i)].file == selected)
                index = i;
        library_.reset(static_cast<int>(games_.size()), index);
        refresh_selected_game();
        mode_.snap(selected_docked_ ? 0.0f : 1.0f);
    }
    name_home_games();
    // Start the global artwork queue as soon as game enumeration completes.
    start_selected_media();
}

void Launcher::name_home_games()
{
    // Games carry their own names; until one has been read the home screen names it by its file.
    for (const Game &game : games_)
    {
        if (game.file == home_.last_file)
        {
            home_.last_mods = game.mods;
            home_.last_mods_on = game.mods_on;
            home_.last_title = game.name;
            if (!game.hero.empty()) home_.last_hero = game.hero;
            if (!game.screenshots.empty()) home_.last_screenshot = game.screenshots.front();
            if (!game.intro.empty()) home_.last_intro = game.intro;
            if (!game.description.empty()) home_.last_description = game.description;
            if (game.max_players > 0) home_.last_max_players = game.max_players;
        }
        for (Recent &recent : home_.recents)
            if (recent.file == game.file)
            {
                recent.title = game.name;
                if (!game.hero.empty()) recent.hero = game.hero;
                if (!game.screenshots.empty()) recent.screenshot = game.screenshots.front();
                if (!game.intro.empty()) recent.intro = game.intro;
                if (!game.description.empty()) recent.description = game.description;
                if (game.max_players > 0) recent.max_players = game.max_players;
            }
    }
}

void Launcher::read_home()
{
    home_ = services_.home();
    home_diagnostics_ = services_.diagnostics();
    if (home_.last_title_id == 0)
        return;
    const std::vector<Mod> mods = services_.mods(home_.last_title_id);
    home_.last_mods = static_cast<int>(mods.size());
    // With the game's Mods switch off none of them is on.
    const bool enabled = mods.empty() || services_.mods_enabled(home_.last_title_id);
    home_.last_mods_on = !enabled ? 0 : static_cast<int>(
        std::count_if(mods.begin(), mods.end(), [](const Mod &mod) { return mod.enabled; }));
}

void Launcher::check_games_present()
{
    // The old two-second poll stat'ed every Home/Library path on the UI
    // update thread. A slow PS5 filesystem response stalled menu navigation.
    // Collect an immutable filename snapshot on the owner thread and query
    // existence in a single worker. Only UI-thread code mutates game state.
    if (presence_scan_.valid()) {
        if (presence_scan_.wait_for(std::chrono::seconds(0)) != std::future_status::ready)
            return;
        try {
            const std::vector<std::string> observed_missing = presence_scan_.get();
            // Results can be stale after a ROM folder refresh or atomic file
            // replacement. Require the same missing path in two independent
            // scans before removing UI items. Worker paths are sorted, so
            // this confirmation needs no filesystem I/O on the UI thread.
            std::vector<std::string> missing;
            std::set_intersection(observed_missing.begin(), observed_missing.end(),
                                  previous_missing_.begin(), previous_missing_.end(),
                                  std::back_inserter(missing));
            previous_missing_ = observed_missing;
            if (missing.empty())
                return;
            const bool home_affected = (home_.last_exists &&
                std::find(missing.begin(), missing.end(), home_.last_file) != missing.end()) ||
                std::any_of(home_.recents.begin(), home_.recents.end(), [&](const Recent &recent) {
                    return std::find(missing.begin(), missing.end(), recent.file) != missing.end();
                });
            if (screen_ == Screen::home && modal_ == Modal::none && home_affected) {
                read_home();
                const int recents = std::min<int>(7, static_cast<int>(home_.recents.size()));
                if (home_focus_ >= 5 && home_focus_ < 11 && home_focus_ - 5 >= recents)
                    home_focus_ = home_.last_exists ? 0 : (home_.setup_ready ? 1 : 2);
                if (home_focus_ == 4 && !home_.last_exists)
                    home_focus_ = 0;
            }
            if (modal_ == Modal::none)
                drop_missing_games(&missing);
        } catch (const std::exception &error) {
            previous_missing_.clear();
            sys::log("presence scan: %s", error.what());
        } catch (...) {
            previous_missing_.clear();
            sys::log("presence scan failed");
        }
        return;
    }

    std::vector<std::string> paths;
    if (screen_ == Screen::home && modal_ == Modal::none) {
        if (home_.last_exists && !home_.last_file.empty())
            paths.push_back(home_.last_file);
        for (const Recent &recent : home_.recents)
            if (!recent.file.empty())
                paths.push_back(recent.file);
    }
    if (modal_ == Modal::none && games_loaded_)
        for (const Game &game : games_)
            if (!game.file.empty())
                paths.push_back(game.file);
    if (paths.empty()) {
        previous_missing_.clear();
        return;
    }
    std::sort(paths.begin(), paths.end());
    paths.erase(std::unique(paths.begin(), paths.end()), paths.end());
    presence_scan_ = std::async(std::launch::async,
        [this, paths = std::move(paths)] {
            std::vector<std::string> missing;
            for (const std::string &path : paths)
                if (!services_.game_exists(path))
                    missing.push_back(path);
            return missing;
        });
}

bool Launcher::drop_missing_games(const std::vector<std::string>* known_missing)
{
    if (!games_loaded_)
        return false;
    const std::string selected =
        library_.selected >= 0 && library_.selected < static_cast<int>(games_.size()) ?
            games_[static_cast<std::size_t>(library_.selected)].file : std::string{};
    const auto gone = std::remove_if(games_.begin(), games_.end(),
        [this, known_missing](const Game &game) {
            // Periodic background poll has already checked these paths.
            // Avoid repeating hundreds of filesystem calls on the UI thread.
            if (known_missing)
                return std::find(known_missing->begin(), known_missing->end(), game.file) != known_missing->end();
            return !services_.game_exists(game.file);
        });
    if (gone == games_.end())
        return false;
    games_.erase(gone, games_.end());

    int index = std::min(library_.selected, std::max(0, static_cast<int>(games_.size()) - 1));
    for (int i = 0; i < static_cast<int>(games_.size()); ++i)
        if (games_[static_cast<std::size_t>(i)].file == selected)
            index = i;
    library_.reset(static_cast<int>(games_.size()), index);
    refresh_selected_game();
    name_home_games();
    return true;
}

void Launcher::count_mods(Game &game, const std::vector<Mod> &mods)
{
    game.mods = static_cast<int>(mods.size());
    // The game's Mods switch (the Library's) comes first: off, none of its mods is used, whatever
    // their own switches say.
    game.mods_enabled = mods.empty() || services_.mods_enabled(game.title_id);
    game.mods_on = !game.mods_enabled ? 0 : static_cast<int>(
        std::count_if(mods.begin(), mods.end(), [](const Mod &mod) { return mod.enabled; }));
    // The home screen says the same of its game.
    if (game.file == home_.last_file && home_.last_title_id != 0)
    {
        home_.last_mods = game.mods;
        home_.last_mods_on = game.mods_on;
    }
}

std::string Launcher::addons_line(const std::string &addons, int mods, int mods_on, bool brief)
{
    std::string line = addons;
    if (mods > 0)
    {
        // Mods that are switched off are still there: "1 of 2 mods on", or "1/2 mods" where there
        // is little room.
        const std::string count = std::to_string(mods);
        const char *counted = mods == 1 ? tr("{0} mod") : tr("{0} mods");
        line += (line.empty() ? "" : ", ") +
                (mods_on == mods ? fill(counted, {count}) :
                 brief ? fill(counted, {std::to_string(mods_on) + "/" + count}) :
                         fill(tr("{0} of {1} mods on"), {std::to_string(mods_on), count}));
    }
    return line.empty() ? std::string{tr("None")} : line;
}

std::string Launcher::hertz(int refresh)
{
    return fill(tr("{0} Hz"), {refresh == 1 ? "120" : "60"});
}

void Launcher::enter_library()
{
    // Library navigation must never block on game enumeration or a full
    // synchronous stat() sweep. The launcher constructor already starts the
    // initial scan; poll its completion here and let update() apply the result.
    // The normal periodic presence worker handles removals in the background.
    finish_scan(false);
    start_scan();
    library_.visible = 5;
    library_.pitch = 1.0f;
    library_.reset(static_cast<int>(games_.size()), 0);
    refresh_selected_game();
    detail_.snap(1.0f);
    mode_.snap(selected_docked_ ? 0.0f : 1.0f);
}

bool Launcher::open_game_settings_at_file(const std::string &file)
{
    if (!games_loaded_) {
        start_scan();
        finish_scan(false);
        if (!games_loaded_ && !scan_.valid()) {
            // A setup-disabled library cannot start a worker; avoid leaving
            // an impossible pending request that never resolves.
            say(tr("ROM missing from the game files folder"), true);
            cue(Cue::error);
            return false;
        }
        if (!games_loaded_) {
            // Home Triangle can arrive while first-time game enumeration is
            // still running. Never block a PS5 UI frame waiting for NACP,
            // updates, DLC or the mods scan; complete the request in update().
            pending_settings_file_ = file;
            return true;
        }
    }
    for (int i = 0; i < static_cast<int>(games_.size()); ++i)
    {
        Game &game = games_[static_cast<std::size_t>(i)];
        if (game.file != file) continue;
        if (game.title_id == 0)
        {
            say(tr("This game's settings cannot be saved (no title ID)."), true);
            cue(Cue::error);
            return false;
        }
        library_.reset(static_cast<int>(games_.size()), i);
        refresh_selected_game();
        game_settings_ = services_.game_settings(game.title_id);
        game_docked_ = selected_docked_;
        import_source_ = services_.save_transfer_available() ?
                             services_.save_import_source(game.title_id) : SaveSource::none;
        import_armed_ = false;
        mods_ = services_.mods(game.title_id);
        count_mods(game, mods_);
        open_modal(Modal::game);
        game_rows_.visible = kDialogRowsShown;
        game_rows_.pitch = kDialogRowPitch;
        game_rows_.reset(dialog_rows(Modal::game), 0);
        return true;
    }
    say(tr("ROM missing from the game files folder"), true);
    cue(Cue::error);
    return false;
}

void Launcher::refresh_selected_game()
{
    const std::uint64_t id =
        games_.empty() ? 0 : games_[static_cast<std::size_t>(library_.selected)].title_id;
    selected_docked_ = id == 0 || services_.docked(id);
    // Its Mods switch shows its state at once; it only animates when changed.
    mods_switch_.snap(!games_.empty() && games_[static_cast<std::size_t>(library_.selected)].mods_enabled ?
                          1.0f : 0.0f);
    detail_.value = 0.0f;
    detail_.velocity = 0.0f;
    start_selected_media();
}

void Launcher::press_library(Key key)
{
    if (key != Key::left && key != Key::right && key != Key::cross && key != Key::options)
        clear_confirmation();
    const int count = static_cast<int>(games_.size());
    const Game *game = count > 0 ? &games_[static_cast<std::size_t>(library_.selected)] : nullptr;
    switch (key)
    {
    case Key::circle:
        open(Screen::home, false);
        return;
    case Key::up:
        top_nav_focus_ = 1;
        cue(Cue::focus);
        return;
    case Key::down:
        // The Library is a horizontal console rail. Down is intentionally reserved for future
        // shelves/actions instead of silently changing game settings.
        return;
    case Key::l1:
    case Key::r1:
        if (library_.page(key == Key::r1 ? 1 : -1))
        {
            message_.clear();
            refresh_selected_game();
            mode_.snap(selected_docked_ ? 0.0f : 1.0f);
            cue(Cue::page);
        }
        return;
    case Key::left:
    case Key::right:
        if (library_.move(key == Key::right ? 1 : -1))
        {
            message_.clear();
            refresh_selected_game();
            mode_.snap(selected_docked_ ? 0.0f : 1.0f);
            cue(Cue::focus);
        }
        return;
    case Key::square:
    {
        // The Mods switch: all of the game's mods on or off at once. Their own switches (Game
        // settings > Mods) keep their state behind it.
        if (game == nullptr || game->title_id == 0 || game->mods == 0)
        {
            if (game != nullptr)
                cue(Cue::error);
            return;
        }
        Game &chosen = games_[static_cast<std::size_t>(library_.selected)];
        const bool saved = services_.set_mods_enabled(chosen.title_id, !chosen.mods_enabled);
        if (saved)
            count_mods(chosen, services_.mods(chosen.title_id));
        say(saved ? tr("Saved for this game. Applies on next launch.") :
                    tr("Could not save. Please try again."),
            !saved);
        cue(saved ? Cue::toggle : Cue::error);
        return;
    }
    case Key::triangle:
        if (game == nullptr)
            return;
        if (game->title_id == 0)
        {
            say(tr("This game's settings cannot be saved (no title ID)."), true);
            cue(Cue::error);
            return;
        }
        game_settings_ = services_.game_settings(game->title_id);
        game_docked_ = selected_docked_;
        import_source_ = services_.save_transfer_available() ?
                             services_.save_import_source(game->title_id) : SaveSource::none;
        import_armed_ = false;
        mods_ = services_.mods(game->title_id);
        count_mods(games_[static_cast<std::size_t>(library_.selected)], mods_);
        open_modal(Modal::game);
        game_rows_.visible = kDialogRowsShown;
        game_rows_.pitch = kDialogRowPitch;
        game_rows_.reset(dialog_rows(Modal::game), 0);
        return;
    case Key::options:
        if (game == nullptr || !home_.setup_ready)
        {
            cue(Cue::error);
            return;
        }
        services_.arm_safe_launch();
        say(tr("Safe launch: OpenGL, Handheld, 1x, 60 Hz, 1080p and mods off for this launch only."));
        launch(game->file, game->name, game->cover);
        return;
    case Key::cross:
        if (game == nullptr || !home_.setup_ready)
        {
            cue(Cue::error);
            return;
        }
        launch(game->file, game->name, game->cover);
        return;
    default:
        return;
    }
}

void Launcher::draw_library(Canvas &c)
{
    gfx::DrawList &list = c.list;
    const int count = static_cast<int>(games_.size());
    draw_top_nav(c, 1, top_nav_focus_, top_nav_focus_ >= 0 ? 1.0f : 0.0f);
    text_shrink(c, tr("Your games"), 72.0f, baseline(142.0f, 38.0f, theme::kHeading),
                theme::kHeading, theme::kTitle, 980.0f);
    text_shrink(c, tr("Select a game to begin"), 72.0f, baseline(176.0f, 24.0f, 18.0f),
                18.0f, theme::kMeta, 1200.0f);
    text(c, list_position(count > 0 ? library_.selected + 1 : 0, count), 1848.0f,
         baseline(150.0f, 32.0f, theme::kSmall), theme::kSmall, theme::kLimePale, Align::right);

    // ---- horizontal TV-first game rail ----
    constexpr float rail_x = 72.0f;
    constexpr float rail_y = 220.0f;
    constexpr float rail_w = 1776.0f;
    constexpr float gap = 20.0f;
    constexpr int slots = 5;
    constexpr float card_h = 286.0f;
    constexpr float card_w = (rail_w - gap * float(slots - 1)) / float(slots);

    if (count == 0)
    {
        const Rect empty{rail_x, rail_y, rail_w, card_h};
        glass(c, empty, 28.0f, theme::kGlass.with_alpha(0.58f), theme::kPanelEdge.with_alpha(0.48f));
        text(c, tr("No ROM files found."), empty.x + empty.w * 0.5f,
             baseline(empty.y, empty.h, theme::kText24), theme::kText24, theme::kCopy, Align::center);
    }
    else
    {
        const int first = std::clamp(library_.selected - slots / 2, 0, std::max(0, count - slots));
        const int last = std::min(count, first + slots);
        for (int index = first; index < last; ++index)
        {
            const int slot = index - first;
            const Game& game = games_[static_cast<std::size_t>(index)];
            const Rect card{rail_x + float(slot) * (card_w + gap), rail_y, card_w, card_h};
            const bool selected = index == library_.selected;
            const float lift = selected ? 1.0f : 0.0f;
            list.push_transform(selected ? 1.025f : 1.0f, card.x + card.w * 0.5f,
                                card.y + card.h * 0.5f, 0.0f, selected ? -5.0f : 0.0f);
            if (selected)
                list.shadow({card.x - 7.0f, card.y - 5.0f, card.w + 14.0f, card.h + 16.0f},
                            28.0f, 42.0f, theme::kLime.with_alpha(0.20f));
            plate_rest(c, kTilePlate, card);
            // A square Nlib/ROM icon belongs on a square game tile; the
            // panoramic banner is only a fallback, never the first choice.
            const std::string& artwork = !game.cover.empty() ? game.cover : game.hero;
            const Rect tile_art{card.x + 4.0f, card.y + 4.0f,
                                card.w - 8.0f, card.h - 8.0f};
            cover_crop(c, artwork, tile_art, 20.0f, selected ? 0.42f : 0.28f);
            const Cover image = c.textures.cover(artwork, std::max(tile_art.w, tile_art.h));
            if (image.texture == 0) {
                const bool fetching = game.title_id != 0 &&
                    (media_scan_title_id_ == game.title_id ||
                     home_media_scan_title_id_ == game.title_id);
                text_shrink(c, tr(fetching || !image.missing ?
                                      "Loading artwork" : "Artwork unavailable"),
                            card.x + card.w * 0.5f,
                            baseline(card.y + 78.0f, 35.0f, 16.0f), 16.0f,
                            theme::kMuted, card.w - 22.0f, Align::center);
            }
            list.gradient_rect({card.x + 4.0f, card.y + card.h * 0.43f, card.w - 8.0f,
                                card.h * 0.53f}, 20.0f,
                               theme::kScrim.with_alpha(0.0f), theme::kScrim.with_alpha(0.94f));
            if (selected)
                plate_focus(c, kTilePlate, card, lift);

            text_shrink(c, game.name, card.x + 20.0f,
                        baseline(card.y + card.h - 66.0f, 32.0f, 22.0f), 22.0f,
                        theme::kTitle, card.w - 40.0f);
            text_shrink(c, game.format, card.x + 20.0f,
                        baseline(card.y + card.h - 31.0f, 22.0f, 15.0f), 15.0f,
                        theme::kMeta, 90.0f);
            if (game.max_players > 0)
            {
                controller_icon(c, {card.x + card.w - 74.0f, card.y + card.h - 37.0f, 30.0f, 21.0f}, 0.9f);
                text(c, "×" + std::to_string(game.max_players), card.x + card.w - 16.0f,
                     baseline(card.y + card.h - 36.0f, 22.0f, 15.0f), 15.0f,
                     theme::kTitle, Align::right);
            }
            list.pop_transform();
        }
    }

    // ---- selected game: one clean detail surface, no hidden left/right setting changes ----
    const Game* game = count > 0 ? &games_[static_cast<std::size_t>(library_.selected)] : nullptr;
    const Rect detail{72.0f, 546.0f, 1776.0f, 350.0f};
    glass(c, detail, 28.0f, theme::kGlass.with_alpha(0.66f),
          theme::kPanelEdge.with_alpha(0.58f), 0.9f);
    const float shown = tween::clamp01(detail_.value);
    list.push_opacity(shown);
    list.push_transform(1.0f, 0.0f, 0.0f, 0.0f, (1.0f - shown) * 10.0f * motion());

    if (game != nullptr)
    {
        const Rect art{96.0f, 572.0f, 420.0f, 298.0f};
        const std::string& artwork = !game->screenshots.empty() ? game->screenshots.front() :
            (!game->hero.empty() ? game->hero : game->cover);
        if (game->screenshots.empty() && game->hero.empty() && !game->cover.empty())
            cover(c, artwork, art, 22.0f, 0.70f);
        else
            cover_crop(c, artwork, art, 22.0f, 0.70f);
        const Cover art_state = c.textures.cover(artwork, std::max(art.w, art.h));
        if (art_state.texture == 0) {
            const bool fetching = game->title_id != 0 &&
                (media_scan_title_id_ == game->title_id ||
                 home_media_scan_title_id_ == game->title_id);
            text_shrink(c, tr(fetching || !art_state.missing ?
                                  "Loading artwork" : "Artwork unavailable"),
                        art.x + art.w * 0.5f, baseline(art.y + 115.0f, 36.0f, 19.0f),
                        19.0f, theme::kMuted, art.w - 28.0f, Align::center);
        }
        // A two-line title previously overlapped the publisher/date and intro
        // (e.g. Breath of the Wild in French). Keep one readable, scaled line.
        text_shrink(c, game->name, 558.0f, baseline(574.0f, 52.0f, 40.0f),
                    40.0f, theme::kTitle, 1160.0f);

        std::string identity;
        if (!game->publisher.empty()) identity = game->publisher;
        else if (!game->developer.empty()) identity = game->developer;
        if (!game->release_date.empty()) {
            if (!identity.empty()) identity += "  ·  ";
            identity += game->release_date;
        }
        if (!game->categories.empty()) {
            if (!identity.empty()) identity += "  ·  ";
            identity += game->categories;
        }
        if (!identity.empty())
            text_shrink(c, identity, 558.0f, baseline(632.0f, 24.0f, 17.0f), 17.0f,
                        theme::kLimePale, 1180.0f);

        if (!game->intro.empty())
            text_block(c, game->intro, 558.0f, baseline(662.0f, 24.0f, 18.0f), 18.0f, 25.0f,
                       theme::kCopy, 1180.0f, 2, kShrink);

        const std::string addons = addons_line(game->addons, game->mods, game->mods_on, true);
        const std::string mode = selected_docked_ ? tr("Docked") : tr("Handheld");
        const std::array<std::string, 5> chips{
            game->format,
            game->size,
            mode,
            game->language.empty() ? std::string{tr("Unknown")} : game->language,
            addons,
        };
        float chip_x = 558.0f;
        for (const auto& chip : chips)
        {
            const float w = std::clamp(text_width(c, chip, 15.0f) + 26.0f, 82.0f, 220.0f);
            list.bordered_rect({chip_x, 722.0f, w, 34.0f}, 17.0f,
                               theme::kPanel.with_alpha(0.54f), 1.0f,
                               theme::kPanelEdge.with_alpha(0.45f));
            text_shrink(c, chip, chip_x + w * 0.5f, baseline(722.0f, 34.0f, 15.0f), 15.0f,
                        theme::kLimePale, w - 18.0f, Align::center);
            chip_x += w + 9.0f;
            if (chip_x > 1760.0f) break;
        }

        // Nlib gameplay strip: three real screenshots at most; loaded lazily by Textures.
        constexpr float shot_y = 778.0f;
        constexpr float shot_h = 86.0f;
        constexpr float shot_w = 154.0f;
        constexpr float shot_gap = 12.0f;
        const int shot_count = std::min<int>(3, static_cast<int>(game->screenshots.size()));
        int shown_screens = 0;
        for (int i = 0; i < shot_count; ++i) {
            const std::string& path = game->screenshots[static_cast<std::size_t>(i)];
            const Cover image = c.textures.cover(path, shot_w);
            // Never reserve a blank, bordered thumbnail for an unreadable file.
            if (image.missing) continue;
            const Rect shot{558.0f + float(shown_screens) * (shot_w + shot_gap),
                            shot_y, shot_w, shot_h};
            cover_crop(c, path, shot, 12.0f, 0.18f);
            if (image.texture == 0)
                text_shrink(c, tr("Loading artwork"), shot.x + shot.w * 0.5f,
                            baseline(shot.y + 29.0f, 25.0f, 13.0f), 13.0f,
                            theme::kMuted, shot.w - 12.0f, Align::center);
            list.bordered_rect(shot, 12.0f, theme::kPanel.with_alpha(0.0f), 1.0f,
                               shown_screens == 0 ? theme::kLime.with_alpha(0.72f) :
                                                    theme::kPanelEdge.with_alpha(0.46f));
            ++shown_screens;
        }
        if (shown_screens == 0)
            text_shrink(c, tr("No screenshots available"), 558.0f,
                        baseline(shot_y + 20.0f, 32.0f, 16.0f), 16.0f,
                        theme::kMuted, 480.0f);

        if (game->mods > 0)
        {
            const float on = tween::clamp01(mods_switch_.value);
            toggle(c, 1792.0f, 742.0f, on);
            text_shrink(c, tr("Mods"), 1668.0f, baseline(722.0f, 40.0f, 18.0f),
                        18.0f, gfx::mix(theme::kMeta, theme::kLimePale, on), 100.0f, Align::right);
        }
    }
    else
    {
        text(c, tr("Select a game"), detail.x + detail.w * 0.5f,
             baseline(detail.y, detail.h, theme::kText24), theme::kText24, theme::kMeta, Align::center);
    }
    list.pop_transform();
    list.pop_opacity();

    static constexpr Hint kHints[] = {
        {Pad::leftright, TR("Browse games")}, {Pad::cross, TR("Launch game")},
        {Pad::triangle, TR("Game settings")}, {Pad::square, TR("Mods")},
        {Pad::options, TR("Safe launch")}, {Pad::circle, TR("Back")}};
    draw_footer(c, kHints, 6);
}

void Launcher::press_game(Key key)
{
    Game &game = games_[static_cast<std::size_t>(library_.selected)];
    const bool mode_confirmation =
        option_ == row_mode && (key == Key::left || key == Key::right || key == Key::cross);
    if (key != Key::triangle && !mode_confirmation)
        clear_confirmation();
    if (key == Key::triangle && option_ >= row_renderer && option_ <= row_controls)
    {
        if (!confirm_action(Confirmation::game_overrides))
            return;
        const GameSettings reset{};
        const bool saved = services_.set_game_settings(game.title_id, reset);
        if (saved) game_settings_ = reset;
        say(saved ? tr("Game overrides reset to global defaults.") :
                    tr("Could not save. Please try again."),
            !saved);
        cue(saved ? Cue::saved : Cue::error);
        return;
    }
    switch (key)
    {
    case Key::circle:
        close_modal();
        selected_docked_ = game_docked_;
        return;
    case Key::up:
    case Key::down:
        if (game_rows_.move(key == Key::down ? 1 : -1))
        {
            option_ = game_rows_.selected;
            message_.clear();
            import_armed_ = false;
            cue(Cue::focus);
        }
        return;
    case Key::square:
        if (option_ != row_save)
            return;
        break;
    case Key::left:
    case Key::right:
    case Key::cross:
        break;
    default:
        return;
    }
    if (option_ == row_controls)
    {
        if (key == Key::cross)
            open_mapping(true);
        return;
    }
    if (option_ == row_mods)
    {
        // The game's mods have their own list. It is read again: mods may have been copied in
        // since this dialog opened.
        if (key != Key::cross)
            return;
        mods_ = services_.mods(game.title_id);
        count_mods(game, mods_);
        mod_rows_.visible = kDialogRowsShown;
        mod_rows_.pitch = kDialogRowPitch;
        mod_rows_.reset(static_cast<int>(mods_.size()), 0);
        modal_ = modal_shown_ = Modal::mods;
        message_.clear();
        cue(Cue::open);
        return;
    }
    if (option_ == row_save)
    {
        // Save data: Square copies the game's save out, Cross (twice) copies one in.
        std::string result;
        if (key == Key::square)
        {
            import_armed_ = false;
            const bool exported = services_.save_export(game.title_id, &result);
            say(result, !exported);
            cue(exported ? Cue::saved : Cue::error);
        }
        else if (key != Key::cross)
        {
            cue(Cue::error);
        }
        else if (import_source_ != SaveSource::none && !import_armed_)
        {
            // Importing replaces the save in use, so it asks first.
            import_armed_ = true;
            say(tr("Press again to replace this game's save. The current one is backed up."), true);
            cue(Cue::notify);
        }
        else
        {
            // With nothing to import the answer says where a save has to be put.
            import_armed_ = false;
            const bool imported = services_.save_import(game.title_id, &result);
            say(result, !imported && import_source_ != SaveSource::none);
            cue(imported ? Cue::saved : import_source_ != SaveSource::none ? Cue::error : Cue::notify);
        }
        return;
    }
    const int step = key == Key::left ? -1 : 1;
    bool saved = false;
    if (option_ == row_mode)
    {
        if (!confirm_action(Confirmation::console_mode))
            return;
        GameSettings next = game_settings_;
        next.console_mode = game_docked_ ? 0 : 1;
        RefreshVideoProfile(next, prefs_, game.title_id);
        saved = services_.set_game_settings(game.title_id, next);
        if (saved) {
            game_settings_ = next;
            game_docked_ = next.console_mode == 1;
        }
    }
    else
    {
        // Default (-1), then each value.
        const auto cycle = [step](int value, int count)
        { return (value + 1 + step + count + 1) % (count + 1) - 1; };
        GameSettings next = game_settings_;
        if (option_ == row_renderer)
        {
            next.renderer = cycle(next.renderer, 2);
            RefreshVideoProfile(next, prefs_, game.title_id);
        }
        if (option_ == row_performance)
        {
            int preset = -1;
            if (next.performance_profile == kCustomVideoProfile)
                preset = step > 0 ? -1 : 3;
            else
                preset = cycle(next.performance_profile, 4);
            if (preset >= 0) {
                ApplyVideoPreset(next, preset, game.title_id);
            } else {
                // Returning the preset to Default also returns the settings the preset owns to
                // the global values; otherwise "Default" would silently keep old overrides.
                next.performance_profile = -1;
                next.console_mode = -1;
                next.renderer = -1;
                next.output = -1;
                next.resolution = -1;
                next.filter = -1;
                next.fsr_sharpness = -1;
                next.anti_aliasing = -1;
                next.refresh = -1;
            }
        }
        if (option_ == row_output)
        {
            next.output = cycle(next.output, 3);
            RefreshVideoProfile(next, prefs_, game.title_id);
        }
        if (option_ == row_resolution)
        {
            next.resolution =
                cycle(next.resolution, static_cast<int>(services_.resolution_labels().size()));
            RefreshVideoProfile(next, prefs_, game.title_id);
        }
        if (option_ == row_filter)
        {
            next.filter = cycle(next.filter, static_cast<int>(services_.filter_labels().size()));
            RefreshVideoProfile(next, prefs_, game.title_id);
        }
        if (option_ == row_fsr_sharpness) {
            const int current = next.fsr_sharpness >= 0 ? next.fsr_sharpness : prefs_.fsr_sharpness;
            next.fsr_sharpness = std::clamp(current + 5 * step, 0, 100);
            RefreshVideoProfile(next, prefs_, game.title_id);
        }
        if (option_ == row_anti_aliasing)
        {
            next.anti_aliasing = cycle(next.anti_aliasing, static_cast<int>(services_.anti_aliasing_labels().size()));
            RefreshVideoProfile(next, prefs_, game.title_id);
        }
        if (option_ == row_refresh)
        {
            next.refresh = cycle(next.refresh, 2);
            RefreshVideoProfile(next, prefs_, game.title_id);
        }
        saved = services_.set_game_settings(game.title_id, next);
        if (saved) {
            game_settings_ = next;
            game_docked_ = next.console_mode >= 0 ? next.console_mode == 1 : services_.docked(game.title_id);
        }
    }
    // 120 Hz is a request: the display has the last word.
    const bool fast = saved && option_ == row_refresh &&
                      (game_settings_.refresh >= 0 ? game_settings_.refresh : prefs_.refresh) == 1;
    say(fast ? tr("Saved. A display that cannot show 120 Hz stays at 60 Hz.") :
        saved ? tr("Saved for this game. Applies on next launch.") : tr("Could not save. Please try again."),
        !saved);
    cue(saved ? Cue::toggle : Cue::error);
}

void Launcher::draw_game(Canvas &c, float open)
{
    gfx::DrawList &list = c.list;
    list.push_opacity(open);
    list.push_transform(1.0f - 0.03f * (1.0f - open) * motion(), 960.0f, 540.0f, 0.0f,
                        (1.0f - open) * 26.0f * motion());
    glass(c, kDialog, 26.0f, theme::kPanel.with_alpha(0.97f), theme::kPanelEdge.with_alpha(0.66f),
          1.6f);
    text_shrink(c, tr("Game settings"), 592.0f, baseline(218.0f, 62.0f, theme::kDisplay),
                theme::kDisplay, theme::kTitle, 736.0f);
    const Game *game = games_.empty() ? nullptr : &games_[static_cast<std::size_t>(library_.selected)];
    text_fit(c, game != nullptr ? game->name : std::string{}, 592.0f,
             baseline(291.0f, 32.0f, theme::kSmall), theme::kSmall, Color::rgb(0xc5c1d2), 736.0f);

    static constexpr const char *kRenderers[] = {"OpenGL", "Vulkan"};
    const auto &resolutions = services_.resolution_labels();
    // A resolution's short name is how its label starts: "0.5x (faster, softer)" is "0.5x".
    const auto short_resolution = [](const std::string &label)
    { return label.substr(0, label.find(' ')); };
    const auto &filters = services_.filter_labels();
    const auto &anti_aliasing = services_.anti_aliasing_labels();
    static constexpr const char *kOutputs[] = {"1080p", "1440p", "2160p"};
    const auto pick = [](const std::vector<std::string> &values, int index) -> std::string
    {
        return index >= 0 && index < static_cast<int>(values.size()) ?
                   values[static_cast<std::size_t>(index)] : std::string{"-"};
    };
    const auto percentage = [](int value) {
        return fill(tr("{0}%"), {std::to_string(value)});
    };
    const std::uint64_t title_id = game != nullptr ? game->title_id : 0;
    const bool authored_global = prefs_.performance_profile >= 0 &&
                                 prefs_.performance_profile < kAuthoredVideoProfiles;
    const auto& base_profile = VideoPresetForTitle(title_id,
        authored_global ? prefs_.performance_profile : 1);
    const int base_renderer = authored_global ? base_profile.renderer : prefs_.renderer;
    const int base_output = authored_global ? base_profile.output : prefs_.output;
    const int base_resolution = authored_global ? base_profile.resolution : prefs_.resolution;
    const int base_filter = authored_global ? base_profile.filter : prefs_.filter;
    const int base_fsr = authored_global ? base_profile.fsr_sharpness : prefs_.fsr_sharpness;
    const int base_aa = authored_global ? base_profile.anti_aliasing : prefs_.anti_aliasing;
    const int base_refresh = authored_global ? base_profile.refresh : prefs_.refresh;
    const std::string values[] = {
        game_docked_ ? tr("Docked") : tr("Handheld"),
        game_settings_.renderer >= 0 ? kRenderers[game_settings_.renderer] :
            fill(tr("Default ({0})"), {kRenderers[base_renderer != 0 ? 1 : 0]}),
        game_settings_.performance_profile >= 0 ?
            services_.performance_profile_labels()[static_cast<std::size_t>(game_settings_.performance_profile)] :
            fill(tr("Default ({0})"), {services_.performance_profile_labels()[static_cast<std::size_t>(std::clamp(prefs_.performance_profile, 0, kCustomVideoProfile))]}),
        game_settings_.output >= 0 ? kOutputs[game_settings_.output] :
            fill(tr("Default ({0})"), {kOutputs[std::clamp(base_output, 0, 2)]}),
        game_settings_.resolution >= 0 ? pick(resolutions, game_settings_.resolution) :
            fill(tr("Default ({0})"), {short_resolution(pick(resolutions, base_resolution))}),
        game_settings_.filter >= 0 ? pick(filters, game_settings_.filter) :
            fill(tr("Default ({0})"), {pick(filters, base_filter)}),
        game_settings_.fsr_sharpness >= 0 ? percentage(game_settings_.fsr_sharpness) :
            fill(tr("Default ({0})"), {percentage(base_fsr)}),
        game_settings_.anti_aliasing >= 0 ? pick(anti_aliasing, game_settings_.anti_aliasing) :
            fill(tr("Default ({0})"), {pick(anti_aliasing, base_aa)}),
        game_settings_.refresh >= 0 ? hertz(game_settings_.refresh) :
            fill(tr("Default ({0})"), {hertz(base_refresh)}),
        game_settings_.own_mapping ?
            controller_profile_name(game_settings_.controller_layout >= 0 ?
                                        game_settings_.controller_layout : prefs_.controller_layout,
                                    game_settings_.mapping) :
            fill(tr("Global ({0})"),
                 {controller_profile_name(prefs_.controller_layout, prefs_.mapping)}),
        // With the game's Mods switch off (the Library's), none of them is on.
        mods_.empty() ? std::string{tr("No mods")} :
        game != nullptr && !game->mods_enabled ? std::string{tr("Off")} :
            fill(tr("{0} of {1} on"),
                 {std::to_string(std::count_if(mods_.begin(), mods_.end(),
                                               [](const Mod &mod) { return mod.enabled; })),
                  std::to_string(mods_.size())}),
        import_source_ == SaveSource::ryujinx ? tr("Ryujinx save found") :
        import_source_ == SaveSource::folder ? tr("Save folder found") : tr("Nothing to import"),
    };
    static constexpr const char *kLabels[] = {
        TR("Console mode"), TR("Renderer"), TR("Video preset"), TR("TV output"),
        TR("Resolution"), TR("Upscaling filter"), TR("FSR sharpness"), TR("Anti-aliasing"),
        TR("Refresh rate"), TR("Button mapping"), TR("Mods"), TR("Save data")};
    // Five rows show; the list scrolls to the others.
    list.push_clip({kDialogWindow.x - 24.0f, kDialogWindow.y - 6.0f, kDialogWindow.w + 48.0f,
                    kDialogWindow.h + 12.0f});
    const auto row_top = [&](int row)
    { return kDialogRowsTop + static_cast<float>(row) * kDialogRowPitch - game_rows_.scroll(); };
    for (int row = game_rows_.first_row(); row <= game_rows_.last_row(); ++row)
    {
        list.push_opacity(game_rows_.row_alpha(row, kDialogRowHeight));
        plate_rest(c, kRowPlate, {592.0f, row_top(row), 736.0f, kDialogRowHeight});
        list.pop_opacity();
    }
    plate_focus(c, kRowPlate,
                {592.0f, kDialogRowsTop + game_rows_.cursor() - game_rows_.scroll(), 736.0f,
                 kDialogRowHeight},
                1.0f);
    for (int row = game_rows_.first_row(); row <= game_rows_.last_row(); ++row)
    {
        const float top = row_top(row);
        const float focus = row == option_ ? 1.0f : 0.0f;
        list.push_opacity(game_rows_.row_alpha(row, kDialogRowHeight));
        // The value first: the row's name takes what it leaves. Mods and Save data say what is
        // there; the others are choices.
        const bool there = row == row_mods ? !mods_.empty() && (game == nullptr || game->mods_enabled) :
                                             import_source_ != SaveSource::none;
        const float taken =
            row >= row_mods ?
                text_shrink(c, values[row], 1292.0f, baseline(top, kDialogRowHeight, theme::kSmall),
                            theme::kSmall, there ? theme::kLimePale : theme::kMeta, 320.0f,
                            Align::right) :
                chooser(c, values[row], 1296.0f, baseline(top, kDialogRowHeight, theme::kText24),
                        focus, theme::kLimePale);
        text_shrink(c, tr(kLabels[row]), 628.0f, baseline(top, kDialogRowHeight, theme::kText24),
                    theme::kText24, theme::kValue, 664.0f - taken - 28.0f);
        list.pop_opacity();
    }
    list.pop_clip();
    scrollbar(c, game_rows_, 1340.0f, kDialogWindow.y, kDialogWindow.h);

    if (!message_.empty())
    {
        // Up to two lines: what Save data answers is longer than a "Saved".
        notice_block(c, message_, 592.0f, kDialogHints - 6.0f, theme::kSmall, 26.0f,
                     message_warning_ ? theme::kWarning : theme::kLimePale, 736.0f, 2,
                     message_warning_);
    }
    else if (option_ == row_save)
    {
        static constexpr Hint kTransfer[] = {{Pad::cross, TR("Import")},
                                             {Pad::square, TR("Export a copy")},
                                             {Pad::circle, TR("Back")}};
        draw_hints(c, kTransfer, 3, 592.0f, kDialogHints, theme::kCopy, 736.0f);
    }
    else if (option_ == row_mods || option_ == row_controls)
    {
        static constexpr Hint kOpen[] = {{Pad::cross, TR("Open")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kOpen, 2, 592.0f, kDialogHints, theme::kCopy, 736.0f);
    }
    else
    {
        static constexpr const char *kGameAbout[] = {
            TR("Docked can improve graphics but may cost performance; Handheld is lighter for demanding games."),
            TR("Vulkan is recommended on PS5. Use OpenGL only as a fallback for a title with Vulkan issues."),
            TR("Minimum, Recommended, High and Ultra apply the title-aware Encore profile. Manual changes become Custom for this game."),
            TR("Resolution follows the selected title-aware profile. Lower it for performance or memory; raise it only when the title has headroom."),
            TR("Bilinear is the lightest default. AMD FSR is useful when rendering below the TV output size."),
            TR("60 Hz is the safe default. Use 120 Hz only with a compatible display or high-FPS patch."),
            TR("Open the per-game DualSense mapping. Global uses Settings > Controls; Custom overrides it only for this game."),
        };
        if (option_ >= row_mode && option_ <= row_controls)
            text_shrink(c, tr(kGameAbout[option_]), 592.0f,
                        baseline(kDialogHints - 34.0f, 24.0f, 18.0f), 18.0f,
                        theme::kMeta, 736.0f);
        static constexpr Hint kHints[] = {
            {Pad::updown, TR("Select")}, {Pad::leftright, TR("Change")},
            {Pad::triangle, TR("Reset overrides")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kHints, 4, 592.0f, kDialogHints + 12.0f, theme::kCopy, 736.0f);
    }
    list.pop_transform();
    list.pop_opacity();
}

// ---------------------------------------------------------------- a game's mods

void Launcher::press_mods(Key key)
{
    Game &game = games_[static_cast<std::size_t>(library_.selected)];
    switch (key)
    {
    case Key::circle:
        // Back to the game's settings, on its Mods row.
        modal_ = modal_shown_ = Modal::game;
        message_.clear();
        cue(Cue::back);
        return;
    case Key::up:
    case Key::down:
        if (mod_rows_.move(key == Key::down ? 1 : -1))
        {
            message_.clear();
            cue(Cue::focus);
        }
        return;
    case Key::square:
    {
        // With no mods yet: the folder they go in, named after the game's ID, is made on request.
        if (!mods_.empty())
            return;
        const bool made = services_.make_mods_folder(game.title_id);
        say(made ? fill(tr("Created {0}. Copy each mod's folder into it."),
                        {services_.mods_folder(game.title_id)}) :
                   tr("Could not create the folder. Check that the game files folder can be written."),
            !made);
        cue(made ? Cue::saved : Cue::error);
        return;
    }
    case Key::cross:
    case Key::left:
    case Key::right:
    {
        if (mods_.empty())
            return;
        Mod &mod = mods_[static_cast<std::size_t>(mod_rows_.selected)];
        // With the game's Mods switch off (the Library's), choosing a mod turns the switch on and
        // that mod with it: nobody switches a mod in a list that is switched off.
        const bool revive = !game.mods_enabled;
        const bool enabled = revive || !mod.enabled;
        const bool saved = (!revive || services_.set_mods_enabled(game.title_id, true)) &&
                           services_.set_mod_enabled(game.title_id, mod.name, enabled);
        if (saved)
            mod.enabled = enabled;
        count_mods(game, mods_);
        say(saved ? tr("Saved for this game. Applies on next launch.") :
                    tr("Could not save. Please try again."),
            !saved);
        cue(saved ? Cue::toggle : Cue::error);
        return;
    }
    default:
        return;
    }
}

void Launcher::draw_mods(Canvas &c, float open)
{
    gfx::DrawList &list = c.list;
    list.push_opacity(open);
    list.push_transform(1.0f - 0.03f * (1.0f - open) * motion(), 960.0f, 540.0f, 0.0f,
                        (1.0f - open) * 26.0f * motion());
    glass(c, kDialog, 26.0f, theme::kPanel.with_alpha(0.97f), theme::kPanelEdge.with_alpha(0.66f),
          1.6f);
    text_shrink(c, tr("Mods"), 592.0f, baseline(218.0f, 62.0f, theme::kDisplay), theme::kDisplay,
                theme::kTitle, 736.0f);
    const Game *game = games_.empty() ? nullptr : &games_[static_cast<std::size_t>(library_.selected)];
    text_fit(c, game != nullptr ? game->name : std::string{}, 592.0f,
             baseline(291.0f, 32.0f, theme::kSmall), theme::kSmall, Color::rgb(0xc5c1d2), 736.0f);

    if (mods_.empty())
    {
        text_block(c,
                   fill(tr("No mods for this game yet. Copy each mod's folder to {0}, next to roms/."),
                        {game != nullptr ? services_.mods_folder(game->title_id) : std::string{}}),
                   592.0f, baseline(364.0f, 40.0f, theme::kText24), theme::kText24, 40.0f,
                   theme::kBody, 736.0f, 5, kShrink);
    }
    else
    {
        list.push_clip({kDialogWindow.x - 24.0f, kDialogWindow.y - 6.0f, kDialogWindow.w + 48.0f,
                        kDialogWindow.h + 12.0f});
        const auto row_top = [&](int row)
        { return kDialogRowsTop + static_cast<float>(row) * kDialogRowPitch - mod_rows_.scroll(); };
        for (int row = mod_rows_.first_row(); row <= mod_rows_.last_row(); ++row)
        {
            list.push_opacity(mod_rows_.row_alpha(row, kDialogRowHeight));
            plate_rest(c, kRowPlate, {592.0f, row_top(row), 736.0f, kDialogRowHeight});
            list.pop_opacity();
        }
        plate_focus(c, kRowPlate,
                    {592.0f, kDialogRowsTop + mod_rows_.cursor() - mod_rows_.scroll(), 736.0f,
                     kDialogRowHeight},
                    1.0f);
        // With the game's Mods switch off (the Library's) no mod is used: their own switches keep
        // their state, drawn faint.
        const bool live = game == nullptr || game->mods_enabled;
        for (int row = mod_rows_.first_row(); row <= mod_rows_.last_row(); ++row)
        {
            const Mod &mod = mods_[static_cast<std::size_t>(row)];
            const float top = row_top(row);
            list.push_opacity(mod_rows_.row_alpha(row, kDialogRowHeight));
            // Its name as the player's folder has it, what it changes under it, its switch.
            text_fit(c, mod.name, 628.0f, baseline(top + 14.0f, 38.0f, theme::kText24),
                     theme::kText24, mod.enabled && live ? theme::kValue : theme::kMeta, 560.0f);
            text_shrink(c, mod.kind, 628.0f, baseline(top + 52.0f, 28.0f, theme::kSmall),
                        theme::kSmall, theme::kMeta, 560.0f);
            list.push_opacity(live ? 1.0f : 0.4f);
            toggle(c, 1292.0f, top + kDialogRowHeight * 0.5f, mod.enabled ? 1.0f : 0.0f);
            list.pop_opacity();
            list.pop_opacity();
        }
        list.pop_clip();
        scrollbar(c, mod_rows_, 1340.0f, kDialogWindow.y, kDialogWindow.h);
    }

    if (!message_.empty())
    {
        notice_block(c, message_, 592.0f, kDialogHints - 6.0f, theme::kSmall, 26.0f,
                     message_warning_ ? theme::kWarning : theme::kLimePale, 736.0f, 2,
                     message_warning_);
    }
    else if (mods_.empty())
    {
        static constexpr Hint kEmpty[] = {{Pad::square, TR("Create the folder")},
                                          {Pad::circle, TR("Back")}};
        draw_hints(c, kEmpty, 2, 592.0f, kDialogHints, theme::kCopy, 736.0f);
    }
    else
    {
        static constexpr Hint kHints[] = {{Pad::updown, TR("Select")},
                                          {Pad::cross, TR("Turn on or off")},
                                          {Pad::circle, TR("Back")}};
        draw_hints(c, kHints, 3, 592.0f, kDialogHints, theme::kCopy, 736.0f);
    }
    list.pop_transform();
    list.pop_opacity();
}

} // namespace pe::ui
