// SPDX-License-Identifier: GPL-3.0-or-later
// The game files folder: keys/, firmware/ and roms/ in the folder chosen in Settings > Game
// files (/data/prosperoeden by default), or the app folder's assets/ without filesystem access.
// Resolved once per process; a new choice applies when ProsperoEden is reopened. Where the rest
// lives: storage_paths.h; what is saved: settings_store.h.
#pragma once
#include <string>
#include <string_view>

#include "settings_store.h"
#include "storage_paths.h"

namespace Eden {
inline constexpr const char* kLegacyInstallAssetsDir = "/data/homebrew/PPSA99008/assets";

// Without filesystem access only the app folder's assets/ is readable. With it: the saved
// folder, else /data/prosperoeden, except that an install from before the setting keeps the
// app folder's assets/ while /data/prosperoeden has no keys.
inline std::string ResolveAssetsDir() {
    const std::string legacy = AppFile("assets");
    if (!FilesystemAccess()) return legacy;
    if (std::string saved = LoadSavedAssetsDir(); !saved.empty()) {
        // ProsperoEden <= 1.000.040 could explicitly keep the pre-1.000.020 game-files folder
        // inside the installed app. If that app was removed before Encore started, do not keep
        // resolving a dead path forever: the migration path is /data/prosperoeden.
        if (saved == kLegacyInstallAssetsDir && !DirectoryExists(saved))
            return kDefaultAssetsDir;
        return saved;
    }
    const std::string keys = "/keys/prod.keys";
    if (!FileExists(kDefaultAssetsDir + keys) && FileExists(legacy + keys)) return legacy;
    return kDefaultAssetsDir;
}

// The game files folder in use by this process.
inline const std::string& AssetsDir() {
    static const std::string directory = ResolveAssetsDir();
    return directory;
}
inline std::string AssetsPath(std::string_view child) { return AssetsDir() + "/" + std::string(child); }
} // namespace Eden
