// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <fcntl.h>
#include <string>
#include <unistd.h>

extern "C" int sceKernelDebugOutText(int, const char*);
extern "C" int sysctlbyname(const char*, void*, size_t*, const void*, size_t);

namespace Eden::BootTrace {
namespace detail {
inline std::string& memory() {
    static std::string text;
    return text;
}
inline int& fd() {
    static int value = -1;
    return value;
}
inline timespec& start() {
    static timespec value = [] {
        timespec now{};
        clock_gettime(CLOCK_MONOTONIC, &now);
        return now;
    }();
    return value;
}
inline long milliseconds() {
    timespec now{};
    clock_gettime(CLOCK_MONOTONIC, &now);
    const timespec& begin = start();
    return (now.tv_sec - begin.tv_sec) * 1000L + (now.tv_nsec - begin.tv_nsec) / 1000000L;
}
inline void write_all(int out, const char* data, size_t size) {
    while (out >= 0 && size) {
        const ssize_t wrote = write(out, data, size);
        if (wrote < 0 && errno == EINTR) continue;
        if (wrote <= 0) break;
        data += wrote;
        size -= static_cast<size_t>(wrote);
    }
}
} // namespace detail

inline void Line(const char* format, ...) {
    char body[640];
    va_list args;
    va_start(args, format);
    std::vsnprintf(body, sizeof(body), format, args);
    va_end(args);

    char line[768];
    const int length = std::snprintf(line, sizeof(line), "[Eden 0.40 Improved] +%ldms %s\n",
                                     detail::milliseconds(), body);
    if (length <= 0) return;
    const size_t size = static_cast<size_t>(length) < sizeof(line) ?
        static_cast<size_t>(length) : sizeof(line) - 1;
    (void)sceKernelDebugOutText(0, line);
    detail::memory().append(line, size);
    if (detail::fd() >= 0) {
        detail::write_all(detail::fd(), line, size);
        (void)fsync(detail::fd());
    }
}

inline void Begin(const char* version, const char* build) {
    (void)detail::start();
    (void)std::rename("/download0/boot-trace.txt", "/download0/boot-trace.prev.txt");
    detail::fd() = open("/download0/boot-trace.txt", O_WRONLY | O_CREAT | O_TRUNC, 0666);

    unsigned int sdk = 0;
    size_t size = sizeof(sdk);
    const bool known = sysctlbyname("kern.sdk_version", &sdk, &size, nullptr, 0) == 0;
    Line("start version=%s build=%s firmware=%s0x%08x pid=%d uid=%d/%d gid=%d/%d",
         version, build, known ? "" : "unknown ", sdk, static_cast<int>(getpid()),
         static_cast<int>(getuid()), static_cast<int>(geteuid()),
         static_cast<int>(getgid()), static_cast<int>(getegid()));
}

// Once normal data paths exist, keep the trace beside the other logs.
inline void Ready(const std::string& logs_dir, bool full_filesystem) {
    if (!full_filesystem) {
        Line("filesystem unavailable; trace remains in /download0");
        return;
    }
    const std::string path = logs_dir + "/boot-trace.txt";
    (void)std::rename(path.c_str(), (logs_dir + "/boot-trace.prev.txt").c_str());
    const int out = open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (out < 0) {
        Line("cannot open %s: %s", path.c_str(), std::strerror(errno));
        return;
    }
    detail::write_all(out, detail::memory().data(), detail::memory().size());
    if (detail::fd() >= 0) close(detail::fd());
    detail::fd() = out;
    (void)fsync(out);
    Line("trace moved to %s", path.c_str());
}
} // namespace Eden::BootTrace
