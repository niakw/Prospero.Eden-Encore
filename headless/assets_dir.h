// SPDX-License-Identifier: GPL-3.0-or-later
// The storage root for game/user-supplied files. Internal storage is /data/prosperoeden by
// default; an external selection changes only this root, never the required subfolder layout.
// Resolved once per process; a new root applies after Encore is reopened.
#pragma once
#include <string>
#include <string_view>

#include "settings_store.h"
#include "storage_paths.h"

namespace Eden {
// One storage root, one schema. Internal storage defaults to /data/prosperoeden; an optional
// external root is saved as a single path and must contain the same keys/, firmware/, roms/,
// updates/, mods/, save-import/, save-export/ and ryujinx/ layout. Without filesystem access the
// app can only see its packaged/sandbox assets/ fallback.
inline std::string ResolveAssetsDir() {
    if (!FilesystemAccess()) return AppFile("assets");
    if (std::string saved = LoadSavedAssetsDir(); !saved.empty())
        return saved;
    return kDefaultAssetsDir;
}

inline const std::string& AssetsDir() {
    static const std::string directory = ResolveAssetsDir();
    return directory;
}
inline std::string AssetsPath(std::string_view child) { return AssetsDir() + "/" + std::string(child); }
} // namespace Eden
