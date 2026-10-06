// SPDX-License-Identifier: GPL-3.0-or-later
// Where ProsperoEden keeps things. With filesystem access (elevation/elevation.hpp, requested
// first thing in main) the app uses real console paths:
//   app folder     the install location, normally /data/homebrew/PPSA99008
//   data           /data/prosperoeden: config/ (prosperoeden.json), logs/, covers/, user/
// Without it (no elfldr, or the request failed) the sandbox paths stay: /app0 and /download0.
#pragma once
#include <cstdio>
#include <string>
#include <string_view>
#include <sys/stat.h>

namespace Eden {
inline constexpr const char* kDataDir = "/data/prosperoeden";
inline constexpr const char* kDefaultAssetsDir = "/data/prosperoeden";
inline constexpr const char* kInstallDir = "/data/homebrew/PPSA99008";
inline constexpr const char* kMountedAppDir = "/system_ex/app/PPSA99008";
inline constexpr const char* kLegacyInstallAssetsDir = "/data/homebrew/PPSA99008/assets";

inline bool LegacyAppAssetsPath(std::string_view path) {
    return path == kLegacyInstallAssetsDir ||
           path == "/app0/assets" ||
           path == "/system_ex/app/PPSA99008/assets" ||
           path == "/mnt/sandbox/PPSA99008_000/app0/assets";
}

// Filesystem status: -1 not decided yet, 0 elevated filesystem access granted, otherwise the
// elevation::Status that refused it.
inline int& FilesystemAccessStatus() {
    static int status = -1;
    return status;
}
inline bool FilesystemAccess() { return FilesystemAccessStatus() == 0; }

inline bool FileExists(const std::string& path) {
    struct stat info {};
    return stat(path.c_str(), &info) == 0 && S_ISREG(info.st_mode);
}
inline bool DirectoryExists(const std::string& path) {
    struct stat info {};
    return stat(path.c_str(), &info) == 0 && S_ISDIR(info.st_mode);
}

// The app's own files. ShadowMountPlus may mount a folder from USB/extended storage at
// /system_ex/app/PPSA99008; prefer the path of the running app instead of assuming /data/homebrew.
inline const std::string& AppDir() {
    static const std::string directory = [] {
        if (!FilesystemAccess()) return std::string{"/app0"};
        for (const char* candidate : {"/app0", kMountedAppDir, kInstallDir,
                                      "/mnt/sandbox/PPSA99008_000/app0"})
            if (FileExists(std::string{candidate} + "/eboot.bin")) return std::string{candidate};
        return std::string{kInstallDir};
    }();
    return directory;
}
inline std::string AppFile(std::string_view name) { return AppDir() + "/" + std::string(name); }

// Auxiliary files can be absent from a ShadowMount/system app projection even when the backing
// installation contains them. Prefer the running app path, then fall back to the known backing
// locations. This keeps launcher translations/art/resources available without changing where the
// executable itself was loaded from.
inline std::string AppResourceFile(std::string_view name) {
    const std::string primary = AppFile(name);
    if (FileExists(primary) || !FilesystemAccess()) return primary;
    for (const char* candidate : {kInstallDir, kMountedAppDir,
                                  "/mnt/sandbox/PPSA99008_000/app0", "/app0"}) {
        const std::string path = std::string{candidate} + "/" + std::string{name};
        if (path != primary && FileExists(path)) return path;
    }
    return primary;
}

// Settings, logs, covers and Eden's user folder.
inline std::string ConfigDir() { return FilesystemAccess() ? std::string{kDataDir} + "/config" : "/download0/prosperoeden"; }
inline std::string LogsDir() { return FilesystemAccess() ? std::string{kDataDir} + "/logs" : "/download0/eden-headless-g7"; }
inline std::string CoversDir() { return FilesystemAccess() ? std::string{kDataDir} + "/covers" : "/download0/prosperoeden/covers"; }
inline std::string UserDir() { return FilesystemAccess() ? std::string{kDataDir} + "/user" : "/download0/eden-headless-g7/user"; }
inline std::string ConfigFile(std::string_view name) { return ConfigDir() + "/" + std::string(name); }
inline std::string LogFile(std::string_view name) { return LogsDir() + "/" + std::string(name); }
inline std::string BackupDir() { return FilesystemAccess() ? std::string{kDataDir} + "/backup" :
                                                           ConfigDir() + "/backup"; }

inline bool ValidAssetsDir(std::string_view path) {
    // Storage roots are user-data locations only. "/" and system/application mounts must never
    // become recursive library roots while Encore has filesystem access.
    if (path.empty() || path == "/" || path.size() > 240 || path.front() != '/') return false;
    if (path.size() > 1 && path.back() == '/') return false;
    if (!(path.starts_with("/data/") || path.starts_with("/mnt/"))) return false;
    if (path.starts_with("/mnt/sandbox/")) return false;
    for (unsigned char c : path)
        if (c < 32 || c == 127 || c == '\\') return false;
    for (std::size_t start = 1; start <= path.size();) {
        const std::size_t end = path.find('/', start);
        const std::string_view part = path.substr(start, end == std::string_view::npos ? path.npos : end - start);
        if (part.empty() || part == "." || part == "..") return false;
        if (end == std::string_view::npos) break;
        start = end + 1;
    }
    return true;
}

} // namespace Eden
