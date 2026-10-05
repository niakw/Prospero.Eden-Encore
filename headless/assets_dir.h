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

inline bool LegacyAppAssetsPath(std::string_view path) {
    return path == kLegacyInstallAssetsDir ||
           path == "/app0/assets" ||
           path == "/system_ex/app/PPSA99008/assets" ||
           path == "/mnt/sandbox/PPSA99008_000/app0/assets";
}

inline bool SelfContainedModeRequested() {
    // Explicit opt-in. The marker is checked through the running title's own sandbox mount before
    // any elevation request. When present, Encore never asks for broader filesystem access.
    return FileExists("/app0/self-contained.txt");
}

// Encore's canonical game-files root is fixed. Legacy/custom locations are migration inputs
// only; normal elevated operation always resolves to /data/prosperoeden. Without filesystem
// access, the app can still read a self-contained assets/ folder from its own mount.
inline std::string ResolveAssetsDir() {
    return FilesystemAccess() ? std::string{kDefaultAssetsDir} : AppFile("assets");
}

inline const std::string& AssetsDir() {
    static const std::string directory = ResolveAssetsDir();
    return directory;
}
inline std::string AssetsPath(std::string_view child) { return AssetsDir() + "/" + std::string(child); }
} // namespace Eden
