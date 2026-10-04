// SPDX-License-Identifier: GPL-3.0-or-later
#include "stop_limit.h"

#include <condition_variable>
#include <fcntl.h>
#include <mutex>
#include <thread>
#include <unistd.h>
#include <utility>

extern "C" int eden_restart_app(void);
extern "C" int sceKernelDebugOutText(int, const char*);

namespace Eden::StopLimit {
namespace {
struct State {
    std::mutex mutex;
    std::condition_variable wake;
    bool watching = false;
    bool armed = false;
    std::chrono::steady_clock::time_point deadline{};
    std::string note;
};

State& state() {
    // The watcher lives until the process is replaced. Intentionally never destroyed: this avoids
    // shutdown-order races with a detached watchdog when another thread is already stuck.
    static State* const instance = new State;
    return *instance;
}

void restart_now() noexcept {
    sceKernelDebugOutText(0, "[Eden 0.40 Improved] game stop exceeded 10s; restarting launcher\n");
    const std::string& note = state().note;
    if (!note.empty()) {
        const int fd = open(note.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666);
        if (fd >= 0) {
            (void)!write(fd, "1\n", 2);
            close(fd);
        }
    }
    (void)eden_restart_app();
}

void watch() {
    State& s = state();
    std::unique_lock lock(s.mutex);
    for (;;) {
        s.wake.wait(lock, [&] { return s.armed; });
        const auto deadline = s.deadline;
        if (s.wake.wait_until(lock, deadline, [&] { return !s.armed || s.deadline != deadline; }))
            continue;
        if (!s.armed || s.deadline != deadline)
            continue;
        s.armed = false;
        lock.unlock();
        restart_now();
        lock.lock();
    }
}
} // namespace

void Start(std::string note) noexcept {
    State& s = state();
    std::lock_guard lock(s.mutex);
    s.note = std::move(note);
    if (s.watching)
        return;
    try {
        std::thread(watch).detach();
        s.watching = true;
    } catch (...) {
        // Failure only restores the old behaviour: shutdown can take as long as it needs.
    }
}

void Begin() noexcept {
    State& s = state();
    std::lock_guard lock(s.mutex);
    if (s.armed)
        return;
    s.armed = true;
    s.deadline = std::chrono::steady_clock::now() + kLimit;
    s.wake.notify_all();
}

void End() noexcept {
    State& s = state();
    std::lock_guard lock(s.mutex);
    s.armed = false;
    s.wake.notify_all();
}
} // namespace Eden::StopLimit
