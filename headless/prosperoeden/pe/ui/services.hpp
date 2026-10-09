// ProsperoEden - What the launcher screens ask of the application.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#pragma once

#include "pe/gfx/image.hpp"
#include "button_mapping.h"

#include <array>
#include <atomic>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace pe::ui
{

// One pressed button (a first press, or a repeat of a held direction or shoulder button).
enum class Key : std::uint8_t
{
    cross,
    circle,
    square,
    triangle,
    options,
    l1,
    r1,
    up,
    down,
    left,
    right,
};

// Button mapping shared with the runtime: guest button -> physical DualSense button.
using ButtonMapping = Eden::ButtonMapping;
inline constexpr int kGameButtons = Eden::kGameButtons;
inline constexpr int kPadButtons = Eden::kPadButtons;
inline constexpr ButtonMapping kDefaultMapping = Eden::kDefaultMapping;
inline constexpr ButtonMapping kPlayStationMapping = Eden::kPlayStationMapping;
inline constexpr ButtonMapping kSwitchMapping = Eden::kSwitchMapping;
inline const ButtonMapping& base_mapping_for_layout(int layout) { return Eden::BaseMappingForLayout(layout); }
inline bool mapping_is_custom(const ButtonMapping& mapping, int layout) { return Eden::MappingIsCustom(mapping, layout); }
inline ButtonMapping assign_button(ButtonMapping mapping, int game, int pad) {
    return Eden::Assign(mapping, game, pad);
}
inline constexpr const char* kGameButtonNames[kGameButtons] = {
    "A", "B", "X", "Y", "L", "R", "ZL", "ZR", "+", "-", "Left stick", "Right stick"};
inline constexpr const char* kPadButtonNames[kPadButtons] = {
    "Cross", "Circle", "Square", "Triangle", "L1", "R1", "L2", "R2", "L3", "R3",
    "Options", "Create", "Touchpad"};

// A game file in the games folder.
struct Game
{
    std::string name;
    std::string format; // "NSP" or "XCI"
    std::string size;   // "1.2 GB"
    std::string file;   // its name in the games folder
    std::string cover;  // square icon path; empty without cover art
    std::string hero;   // cached 16:9 Nlib banner; empty => use first screenshot/cover
    std::vector<std::string> screenshots; // up to three cached Nlib gameplay screenshots
    int max_players = 0; // Nlib maximum local players; 0 when unknown/offline
    bool artwork_changed = false; // async refresh replaced one or more files
    bool docked = true; // effective mode precomputed on library worker; no settings I/O on D-pad
    std::string intro;
    std::string description;
    std::string publisher;
    std::string developer;
    std::string release_date;
    std::string categories;
    std::uint64_t title_id = 0;
    std::string addons;        // "Update 1.2.0, 2 DLC"; empty without either
    std::string addons_short;  // the same where there is little room: "v1.2.0, 2 DLC"
    std::string language;      // the language the game will use
    std::string language_note; // set when that is not the chosen one
    // Its mods, and how many of them are switched on. The launcher counts them (Services::mods)
    // when it takes the list and whenever they change. With the game's Mods switch off
    // (Services::mods_enabled) none is on.
    int mods = 0;
    int mods_on = 0;
    bool mods_enabled = true;
    // Nlib artwork is complete per title (icon, banner, all advertised screens).
    // No title-specific source or performance override is attached to Game.
};

struct Recent
{
    std::string file;
    std::string title;
    std::string cover;
    std::string hero; // cached Nlib banner; empty => screenshot/cover fallback
    std::string screenshot; // first cached Nlib screenshot
    int max_players = 0; // Nlib maximum local players; 0 when unknown/offline
    std::string intro;
    std::string description; // detailed, title-keyed Nlib text for the Hero
    std::uint64_t title_id = 0;
    std::string addons;
    std::string language;
};

// The home screen's content.
struct Home
{
    bool setup_ready = false;
    std::string status;    // a setup or launch problem; empty when there is none
    bool launch_failed = false; // the status is about the game that just failed to start
    std::string last_file; // the last game played; empty before the first one
    bool last_exists = false;
    std::string last_title;
    std::string last_caption;
    bool last_caption_warning = false; // the caption says what is wrong with the game
    std::string last_cover;
    std::string last_hero; // cached Nlib banner; empty => last_screenshot/last_cover
    std::string last_screenshot;
    int last_max_players = 0; // Nlib maximum local players; 0 when unknown/offline
    std::string last_intro;
    std::string last_description;
    // What the last game comes with, when it can be started: its title ID, its update and DLC
    // (as Game::addons) and the language it will use. Its mods are counted by the launcher.
    std::uint64_t last_title_id = 0;
    std::string last_addons;
    std::string last_language;
    int last_mods = 0;
    int last_mods_on = 0;
    std::vector<Recent> recents; // at most seven
    std::string system_status;
};

struct Preferences
{
    bool hud = false;
    int volume = 100; // game volume, 0-100
    bool mute = false;
    bool detailed_logging = false;
    int renderer = 1; // 0 OpenGL, 1 Vulkan
    int resolution = 4; // Recommended: 1.25x
    int filter = 0;
    int fsr_sharpness = 50;
    int anti_aliasing = 1; // 0 none, 1 FXAA, 2 SMAA
    int refresh = 0; // the output while a game runs: 0 60 Hz, 1 120 Hz
    int output = 1;  // Recommended: 1440p
    int performance_profile = 1; // 0 Minimum, 1 Recommended, 2 High, 3 Ultra, 4 Custom
    int controller_layout = 0; // 0 PlayStation, 1 Switch; custom status derives from mapping
    ButtonMapping mapping = kPlayStationMapping;
    bool vibration = true;
    int vibration_strength = 100;
    int stick_deadzone = 8;
    int language = 0;
    int menu_volume = 70; // launcher sounds, 0-100
    // Accessibility: how the launcher itself is shown (theme.hpp, Look).
    bool large_text = false;
    bool high_contrast = false;
    bool reduce_motion = false;
};

// One game's overrides; -1 uses Settings > Video.
struct GameSettings
{
    int console_mode = -1; // -1 follows authored profile/default, 0 Handheld, 1 Docked
    int renderer = -1;
    int output = -1;
    int resolution = -1;
    int filter = -1;
    int fsr_sharpness = -1;
    int anti_aliasing = -1;
    int refresh = -1;
    int performance_profile = -1;
    int controller_layout = -1; // -1 follows global, 0 PlayStation, 1 Switch
    bool own_mapping = false;
    ButtonMapping mapping = kPlayStationMapping;
};

// A mod of one game, from the game files folder's mods/<title ID>/.
struct Mod
{
    std::string name;    // its folder's name
    std::string kind;    // what it is made of: "Patch", "Files", "Cheats"
    bool enabled = true; // used when the game starts
};

// Where a save to import was found, in the game files folder.
enum class SaveSource : std::uint8_t
{
    none,
    folder,  // save-import/<title ID>/, copied by hand
    ryujinx, // ryujinx/, a Ryujinx data folder
};

// What a folder holds, for Settings > Game files. Counts are -1 without the subfolder.
struct FolderInfo
{
    bool keys = false;
    int firmware = -1;
    int games = -1;
};

struct DiagnosticsInfo
{
    std::string filesystem;
    std::string free_space;
    std::string used_space;
    std::string total_space;
    std::string shader_caches;
    std::string logs;
    std::string data_path;
    std::string storage_root; // actual selected Encore root; not a claim about physical SSD capacity
    std::uint64_t free_bytes = 0;
    std::uint64_t total_bytes = 0;
    std::uint64_t shader_cache_bytes = 0;
};

class Services
{
  public:
    virtual ~Services() = default;

    // ---- home ----
    virtual Home home() = 0;
    // A native recent-game metadata walk can be long; prevent teardown
    // from waiting for entries that have not yet been inspected.
    virtual Home home(const std::atomic<bool>* cancel) {
        if (cancel && cancel->load(std::memory_order_acquire)) return {};
        return home();
    }
    virtual std::string clock() = 0;   // "14:05"
    // The players (bit 0 is player 1) whose controller is connected right now.
    virtual unsigned controllers()
    {
        return 1u;
    }
    virtual std::string version() = 0; // "R1"

    // ---- library ----
    virtual std::vector<Game> games() = 0; // reads every game file: slow
    // Optional cooperative cancellation of native metadata enumeration when a
    // game launches. Other providers keep the original API and behavior.
    virtual std::vector<Game> games(const std::atomic<bool>* cancel) {
        if (cancel && cancel->load(std::memory_order_acquire)) return {};
        return games();
    }
    // Enrich one already-scanned game lazily (Nlib on native builds). The default is a no-op so
    // host/preview services stay deterministic and offline.
    virtual Game enrich_game_media(Game game) { return game; }
    // Cancel Nlib work that has not started by the time a title launches;
    // in-flight HTTPS requests still complete naturally before teardown.
    virtual Game enrich_game_media(Game game, const std::atomic<bool>* cancel) {
        if (cancel && cancel->load(std::memory_order_acquire)) return game;
        return enrich_game_media(std::move(game));
    }
    // The value the launcher hands back to start a game.
    virtual std::string game_path(const std::string &file) = 0;
    // Cheap presence check used while the launcher is open.
    virtual bool game_exists(const std::string &) { return true; }
    // Keep cached titles when the ROM storage root itself is unavailable.
    virtual bool game_storage_available() { return true; }
    // Arms a one-shot conservative launch profile. Native builds override this; host/preview
    // services may safely leave it as a no-op.
    virtual void arm_safe_launch() {}
    virtual bool docked(std::uint64_t title_id) = 0;
    virtual bool set_docked(std::uint64_t title_id, bool docked) = 0;
    virtual GameSettings game_settings(std::uint64_t title_id) = 0;
    virtual bool set_game_settings(std::uint64_t title_id, const GameSettings &settings) = 0;

    // ---- settings ----
    virtual Preferences preferences() = 0;
    virtual bool set_preferences(const Preferences &preferences) = 0;
    virtual const std::vector<std::string> &resolution_labels() = 0; // "1x (native)"
    virtual const std::vector<std::string> &resolution_keys() = 0;   // "1x"
    virtual const std::vector<std::string> &filter_labels() = 0;
    virtual const std::vector<std::string> &anti_aliasing_labels() = 0;
    virtual const std::vector<std::string> &performance_profile_labels() = 0;
    virtual const std::vector<std::string> &language_labels() = 0;
    virtual std::string language_region(int language) = 0;
    virtual std::string setup_details() = 0;
    virtual DiagnosticsInfo diagnostics() { return {}; }
    // Optional cooperative cancellation for lengthy native cache/log walks.
    // Host/preview implementations retain their original behavior.
    virtual DiagnosticsInfo diagnostics(const std::atomic<bool>* cancel) {
        if (cancel && cancel->load(std::memory_order_acquire)) return {};
        return diagnostics();
    }
    virtual bool clear_shader_caches(std::string *message)
    {
        if (message) *message = "Unavailable";
        return false;
    }

    // ---- game files ----
    // The subfolder names of a folder; false when it cannot be opened.
    virtual bool folders(const std::string &directory, std::vector<std::string> *names) = 0;
    virtual FolderInfo folder_info(const std::string &directory) = 0;
    virtual std::string files_folder() = 0;       // in use by this process
    virtual std::string saved_files_folder() = 0; // used from the next start; empty when none
    virtual std::string default_files_folder() = 0;
    virtual bool set_files_folder(const std::string &directory) = 0;
    virtual int filesystem_access() = 0; // 0: the whole filesystem

    // ---- save transfer: a game's save in from, or out to, a folder (not in every build) ----
    virtual bool save_transfer_available()
    {
        return false;
    }
    // What there is to import for the game.
    virtual SaveSource save_import_source(std::uint64_t)
    {
        return SaveSource::none;
    }
    // Each returns whether it was done, with what to tell the player in message.
    virtual bool save_import(std::uint64_t, std::string *)
    {
        return false;
    }
    virtual bool save_export(std::uint64_t, std::string *)
    {
        return false;
    }

    // ---- mods: patches, replacement files and cheats the player added for a game ----
    virtual std::vector<Mod> mods(std::uint64_t)
    {
        return {};
    }
    virtual bool set_mod_enabled(std::uint64_t, const std::string &, bool)
    {
        return false;
    }
    // One switch for all of a game's mods (the Library's Mods switch), on unless turned off. The
    // mods keep their own switches behind it.
    virtual bool mods_enabled(std::uint64_t)
    {
        return true;
    }
    virtual bool set_mods_enabled(std::uint64_t, bool)
    {
        return false;
    }
    // Where a game's mods go, as the player would write it: "mods/0100.../".
    virtual std::string mods_folder(std::uint64_t)
    {
        return {};
    }
    // Makes that folder; false when it cannot be made.
    virtual bool make_mods_folder(std::uint64_t)
    {
        return false;
    }

    // ---- images ----
    virtual bool load_image(const std::string &path, gfx::Image *image) = 0;
};

} // namespace pe::ui
