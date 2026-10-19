// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

// Native DEV-only bookkeeping: distinct guest titles must not share JIT locations.
#include <cstdint>
#include <mutex>
#include <unordered_map>

namespace Eden::Performance {

class JitDuplicateHistory final {
public:
    // The first call alone reserves diagnostic storage; a non-opted-in
    // session never allocates the large block-location map.
    unsigned Record(unsigned core, std::uint64_t location, long long now_ns) {
        std::lock_guard lock{mutex_};
        if (!reserved_) {
            compiled_.reserve(1u << 21);
            reserved_ = true;
        }
        auto [it, inserted] = compiled_.try_emplace(location, First{1u << core, now_ns});
        if (inserted) {
            return 0;
        }
        if (it->second.cores & (1u << core)) {
            return 1;
        }
        it->second.cores |= 1u << core;
        const long long lead = now_ns - it->second.ns;
        unsigned index = 2;
        for (long long bound = 1'000'000; index < 7 && lead >= bound; bound *= 10) {
            ++index;
        }
        return index;
    }

    // Call only at the launch boundary after the previous guest CPU/JIT
    // workers have joined. The lock also serializes any diagnostic call.
    void Reset() noexcept {
        std::lock_guard lock{mutex_};
        compiled_.clear();
    }

private:
    struct First {
        unsigned cores;
        long long ns;
    };
    std::mutex mutex_;
    std::unordered_map<std::uint64_t, First> compiled_;
    bool reserved_ = false;
};
} // namespace Eden::Performance
