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
inline constexpr int kFilesystemSelfContained = -2;

// Filesystem status: -1 not decided yet, -2 deliberately self-contained in the app sandbox,
// 0 elevated filesystem access granted, otherwise the elevation::Status that refused it.
inline int& FilesystemAccessStatus() {
    static int status = -1;
    return status;
}
inline bool FilesystemAccess() { return FilesystemAccessStatus() == 0; }
inline bool SelfContainedMode() { return FilesystemAccessStatus() == kFilesystemSelfContained; }

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

// Settings, logs, covers and Eden's user folder.
inline std::string ConfigDir() { return FilesystemAccess() ? std::string{kDataDir} + "/config" : "/download0/prosperoeden"; }
inline std::string LogsDir() { return FilesystemAccess() ? std::string{kDataDir} + "/logs" : "/download0/eden-headless-g7"; }
inline std::string CoversDir() { return FilesystemAccess() ? std::string{kDataDir} + "/covers" : "/download0/prosperoeden/covers"; }
inline std::string UserDir() { return FilesystemAccess() ? std::string{kDataDir} + "/user" : "/download0/eden-headless-g7/user"; }
inline std::string ConfigFile(std::string_view name) { return ConfigDir() + "/" + std::string(name); }
inline std::string LogFile(std::string_view name) { return LogsDir() + "/" + std::string(name); }
inline std::string BackupDir() { return FilesystemAccess() ? std::string{kDataDir} + "/backup" :
                                                           ConfigDir() + "/backup"; }
inline std::string ExportDir() { return FilesystemAccess() ? kDefaultAssetsDir :
                                                           ConfigDir() + "/save-export"; }

inline bool ValidAssetsDir(std::string_view path) {
    // "/" would make library/setup scans walk the console root and can expose unrelated system
    // folders in the browser. Game files must live in an explicit directory.
    if (path.empty() || path == "/" || path.size() > 240 || path.front() != '/') return false;
    if (path.size() > 1 && path.back() == '/') return false;
    for (unsigned char c : path)
        if (c < 32 || c == 127 || c == '\\') return false;
    for (std::size_t start = 1; start <= path.size();) {
        const std::size_t end = path.find('/', start);
        const std::string_view part = path.substr(start, end == std::string_view::npos ? path.npos : end - start);
        if (part.empty() || part == "." || part == "..") return path == "/";
        if (end == std::string_view::npos) break;
        start = end + 1;
    }
    return true;
}

} // namespace Eden
