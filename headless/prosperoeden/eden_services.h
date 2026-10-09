// SPDX-License-Identifier: GPL-3.0-or-later
// What the launcher screens ask of the app, answered from the console: the games folder,
// the settings file, Eden's metadata reader.
#pragma once

#include "pe/ui/services.hpp"

#include <mutex>
#include <string>
#include <vector>

class EdenServices final : public pe::ui::Services {
public:
    // launch_error: why the game chosen last time did not start (empty: nothing to report).
    explicit EdenServices(std::string launch_error);

    pe::ui::Home home() override;
    pe::ui::Home home(const std::atomic<bool>* cancel) override;
    std::string clock() override;
    unsigned controllers() override;
    std::string version() override;

    std::vector<pe::ui::Game> games() override;
    std::vector<pe::ui::Game> games(const std::atomic<bool>* cancel) override;
    pe::ui::Game enrich_game_media(pe::ui::Game game) override;
    pe::ui::Game enrich_game_media(pe::ui::Game game, const std::atomic<bool>* cancel) override;
    std::string game_path(const std::string& file) override;
    bool game_exists(const std::string& file) override;
    bool game_storage_available() override;
    void arm_safe_launch() override;
    bool docked(std::uint64_t title_id) override;
    bool set_docked(std::uint64_t title_id, bool docked) override;
    pe::ui::GameSettings game_settings(std::uint64_t title_id) override;
    bool set_game_settings(std::uint64_t title_id, const pe::ui::GameSettings& settings) override;

    pe::ui::Preferences preferences() override;
    bool set_preferences(const pe::ui::Preferences& preferences) override;
    const std::vector<std::string>& resolution_labels() override;
    const std::vector<std::string>& resolution_keys() override;
    const std::vector<std::string>& filter_labels() override;
    const std::vector<std::string>& anti_aliasing_labels() override;
    const std::vector<std::string>& performance_profile_labels() override;
    const std::vector<std::string>& language_labels() override;
    std::string language_region(int language) override;
    std::string setup_details() override;
    pe::ui::DiagnosticsInfo diagnostics() override;
    pe::ui::DiagnosticsInfo diagnostics(const std::atomic<bool>* cancel) override;
    bool clear_shader_caches(std::string* message) override;

    bool folders(const std::string& directory, std::vector<std::string>* names) override;
    pe::ui::FolderInfo folder_info(const std::string& directory) override;
    std::string files_folder() override;
    std::string saved_files_folder() override;
    std::string default_files_folder() override;
    bool set_files_folder(const std::string& directory) override;
    int filesystem_access() override;

    bool save_transfer_available() override;
    pe::ui::SaveSource save_import_source(std::uint64_t title_id) override;
    bool save_import(std::uint64_t title_id, std::string* message) override;
    bool save_export(std::uint64_t title_id, std::string* message) override;

    std::vector<pe::ui::Mod> mods(std::uint64_t title_id) override;
    bool set_mod_enabled(std::uint64_t title_id, const std::string& name, bool enabled) override;
    bool mods_enabled(std::uint64_t title_id) override;
    bool set_mods_enabled(std::uint64_t title_id, bool enabled) override;
    std::string mods_folder(std::uint64_t title_id) override;
    bool make_mods_folder(std::uint64_t title_id) override;

    bool load_image(const std::string& path, pe::gfx::Image* image) override;

private:
    std::string launch_error_;
    std::string setup_; // what is missing from keys and firmware; empty when ready
    // These depend on the active launcher catalog. They belong to this service instance rather
    // than process-global statics so an in-process language restart rebuilds every translated label.
    std::vector<std::string> resolution_labels_;
    std::vector<std::string> resolution_keys_;
    std::vector<std::string> filter_labels_;
    std::vector<std::string> anti_aliasing_labels_;
    std::vector<std::string> performance_profile_labels_;
    std::vector<std::string> language_labels_;
    std::mutex bridge_; // Eden's metadata reader keeps state between calls: one caller at a time
};
