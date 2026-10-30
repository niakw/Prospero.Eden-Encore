// SPDX-License-Identifier: GPL-3.0-or-later
// Optional read-only cooperation with NiakPS5's foreground-account avatar.
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace pe::ps5 {
inline bool avatar_owner_marker_matches(const char* marker,
                                        std::uint32_t foreground_user,
                                        const char* format) {
    if (!marker || !format) return false;
    char expected[32]{};
    const int n = std::snprintf(expected, sizeof(expected), "0x%08X %s\n",
                                foreground_user, format);
    if (n <= 0 || n >= static_cast<int>(sizeof(expected))) return false;
    const int fd = ::open(marker, O_RDONLY | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) return false;
    struct stat st{};
    const bool regular = ::fstat(fd, &st) == 0 && S_ISREG(st.st_mode) &&
                         st.st_size == n;
    char actual[32]{};
    ssize_t got = regular ? ::read(fd, actual, static_cast<std::size_t>(n)) : -1;
    const int closed = ::close(fd);
    return regular && got == n && closed == 0 &&
           std::memcmp(actual, expected, static_cast<std::size_t>(n)) == 0;
}
} // namespace pe::ps5
