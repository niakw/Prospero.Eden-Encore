// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Bounded low-contention HLE command telemetry for the all-on diagnostic build.
// The guest hot path performs no heap allocation and takes no global mutex
// once a service/command pair has been registered.
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <mutex>

namespace Eden::Performance {
class HleCounters {
public:
    static constexpr std::size_t kCapacity = 4096;
    static constexpr std::size_t kNameBytes = 80;

    void Record(const char* service, unsigned command, long long elapsed_ns) noexcept {
        if (!service) service = "?";
        const std::uint64_t key = Hash(service, command);
        const std::uint64_t elapsed = elapsed_ns > 0 ? static_cast<std::uint64_t>(elapsed_ns) : 0;
        for (std::size_t probe = 0; probe < kCapacity; ++probe) {
            Counter& entry = counters_[(key + probe) & (kCapacity - 1)];
            const std::uint64_t published = entry.key.load(std::memory_order_acquire);
            if (published == key && entry.command == command &&
                std::strncmp(entry.name, service, kNameBytes - 1) == 0) {
                entry.calls.fetch_add(1, std::memory_order_relaxed);
                entry.nanoseconds.fetch_add(elapsed, std::memory_order_relaxed);
                return;
            }
            if (published == 0) {
                // Unseen commands are infrequent. Serialize registration only;
                // all already-published entries remain lock-free for readers.
                const std::lock_guard lock(register_mutex_);
                const std::uint64_t registered =
                    entry.key.load(std::memory_order_acquire);
                if (registered != 0) {
                    // Another thread can publish THIS VERY SAME command
                    // while we wait for registration. Reuse that counter,
                    // not a duplicate slot later in the probe sequence.
                    if (registered == key && entry.command == command &&
                        std::strncmp(entry.name, service, kNameBytes - 1) == 0) {
                        entry.calls.fetch_add(1, std::memory_order_relaxed);
                        entry.nanoseconds.fetch_add(elapsed, std::memory_order_relaxed);
                        return;
                    }
                    continue;
                }
                entry.command = command;
                std::strncpy(entry.name, service, kNameBytes - 1);
                entry.name[kNameBytes - 1] = '\0';
                // Immutable name and command become visible before the key.
                entry.key.store(key, std::memory_order_release);
                entry.calls.fetch_add(1, std::memory_order_relaxed);
                entry.nanoseconds.fetch_add(elapsed, std::memory_order_relaxed);
                return;
            }
        }
        // If unusual software floods the diagnostic table, accounting is
        // bounded: gameplay is never blocked or made to allocate new entries.
        overflow_calls_.fetch_add(1, std::memory_order_relaxed);
        overflow_ns_.fetch_add(elapsed, std::memory_order_relaxed);
    }

    template<class Visit>
    void ForEach(Visit&& visit) const {
        for (const Counter& entry : counters_)
            if (entry.key.load(std::memory_order_acquire) != 0)
                visit(entry.name, entry.command,
                      entry.calls.load(std::memory_order_relaxed),
                      entry.nanoseconds.load(std::memory_order_relaxed));
    }

    std::uint64_t OverflowCalls() const noexcept {
        return overflow_calls_.load(std::memory_order_relaxed);
    }
    std::uint64_t OverflowNs() const noexcept {
        return overflow_ns_.load(std::memory_order_relaxed);
    }

private:
    struct Counter {
        std::atomic<std::uint64_t> key{0}; // zero is empty; published last
        unsigned command = 0;             // immutable after key publication
        char name[kNameBytes]{};           // owned copy, survives service teardown
        std::atomic<std::uint64_t> calls{0};
        std::atomic<std::uint64_t> nanoseconds{0};
    };

    static std::uint64_t Hash(const char* name, unsigned command) noexcept {
        // Stable key by CONTENT, not a potentially reused service-name
        // pointer from an earlier guest session.
        std::uint64_t hash = 14695981039346656037ull;
        constexpr std::uint64_t prime = 1099511628211ull;
        for (const unsigned char* ch = reinterpret_cast<const unsigned char*>(name); *ch; ++ch)
            hash = (hash ^ *ch) * prime;
        for (unsigned shift = 0; shift < 32; shift += 8)
            hash = (hash ^ ((command >> shift) & 0xffu)) * prime;
        return hash ? hash : 1;
    }

    std::array<Counter, kCapacity> counters_{};
    std::mutex register_mutex_;
    std::atomic<std::uint64_t> overflow_calls_{0};
    std::atomic<std::uint64_t> overflow_ns_{0};
};
} // namespace Eden::Performance
