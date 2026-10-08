// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <algorithm>
#include <filesystem>
#include <string>
#include <sys/stat.h>
#include <vector>

namespace Eden {
// Call only between sessions. Files are retained while the disk has usable
// free space: shader recompilation after a blind 64 MiB LRU purge was avoidable.
// The reserve is a *minimum free-storage threshold*, never a shader-cache cap.
// Sandbox installations receive a smaller reserve than full /data installations.
inline size_t TrimShaderCache(const std::vector<std::filesystem::directory_entry>& entries,
                              std::uintmax_t available, std::uintmax_t capacity) {
    constexpr std::uintmax_t mib = 1024ull * 1024ull;
    if (capacity == 0 || capacity == static_cast<std::uintmax_t>(-1) ||
        available == static_cast<std::uintmax_t>(-1)) return 0;
    const auto reserve = std::min<std::uintmax_t>(1024 * mib,
                        std::max<std::uintmax_t>(32 * mib, capacity / 20));
    if (available >= reserve) return 0;
    const auto deficit = reserve - available;
    struct Record { std::filesystem::path path; uint64_t bytes; time_t modified; };
    std::vector<Record> records;
    for (const auto& entry : entries) {
        const auto name = entry.path().filename().string();
        const auto dot = name.find('.');
        if ((dot != 3 && dot != 4) || name.substr(dot) != ".bin" ||
            name.find_first_not_of("0123456789abcdef") != dot) continue;
        struct stat info{};
        if (::stat(entry.path().c_str(), &info) || !S_ISREG(info.st_mode) ||
            info.st_blocks < 0 || info.st_size < 0) continue;
        const auto bytes = std::max(uint64_t(info.st_size), uint64_t(info.st_blocks) * 512);
        records.push_back({entry.path(), bytes, info.st_mtime});
    }
    std::sort(records.begin(), records.end(), [](const Record& a, const Record& b) {
        return a.modified < b.modified;
    });
    size_t removed = 0;
    std::uintmax_t reclaimed = 0;
    for (const auto& record : records) {
        if (reclaimed >= deficit) break;
        std::error_code error;
        if (std::filesystem::remove(record.path, error) && !error) {
            reclaimed += record.bytes;
            ++removed;
        }
    }
    return removed;
}
}
