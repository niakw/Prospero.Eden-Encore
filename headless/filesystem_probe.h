// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cerrno>
#include <fcntl.h>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

namespace Eden {

// Prove the capability Encore actually needs instead of inferring it from uid/gid values.
// The probe also creates the persistent root on a clean install. It never follows a root symlink.
inline bool ProbeWritableRoot(const std::string& root) noexcept {
    struct stat info {};
    if (lstat(root.c_str(), &info) != 0) {
        if (errno != ENOENT)
            return false;
        if (mkdir(root.c_str(), 0777) != 0 && errno != EEXIST)
            return false;
        if (lstat(root.c_str(), &info) != 0)
            return false;
    }
    if (!S_ISDIR(info.st_mode) || S_ISLNK(info.st_mode))
        return false;

    const std::string probe = root + "/.encore-access-probe-" + std::to_string(static_cast<long long>(getpid()));
    const int fd = open(probe.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0)
        return false;

    static constexpr char token[] = "ENCORE_FS_OK\n";
    std::size_t done = 0;
    while (done < sizeof(token) - 1) {
        const ssize_t wrote = write(fd, token + done, sizeof(token) - 1 - done);
        if (wrote < 0 && errno == EINTR)
            continue;
        if (wrote <= 0)
            break;
        done += static_cast<std::size_t>(wrote);
    }
    const bool wrote_all = done == sizeof(token) - 1;
    const bool synced = !wrote_all || fsync(fd) == 0;
    const bool closed = close(fd) == 0;
    const bool removed = unlink(probe.c_str()) == 0;
    return wrote_all && synced && closed && removed;
}

} // namespace Eden
