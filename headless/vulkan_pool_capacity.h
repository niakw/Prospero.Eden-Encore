// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <atomic>
#include <cstdint>

namespace Eden::VulkanMemory {
// Process-global GPU capacity estimate, reset when a new VkDevice is built.
// Startup's first Sony free-direct-memory query may transiently fail and
// report zero. Latch the first later nonzero observation, not permanent zero.
// Sampling is performed by the EXISTING throttled graphics_memory_free
// callback; this helper issues no new kernel probes and allocates nothing.
class PoolCapacityLatch {
public:
    void Reset(std::uint64_t initial_confirmed_free) noexcept {
        capacity_.store(initial_confirmed_free, std::memory_order_release);
    }
    std::uint64_t Observe(std::uint64_t confirmed_free_now) noexcept {
        std::uint64_t capacity = capacity_.load(std::memory_order_acquire);
        if (capacity != 0 || confirmed_free_now == 0)
            return capacity;
        std::uint64_t absent = 0;
        if (capacity_.compare_exchange_strong(absent, confirmed_free_now,
                                               std::memory_order_acq_rel,
                                               std::memory_order_acquire))
            return confirmed_free_now;
        return absent;
    }
    std::uint64_t Value() const noexcept {
        return capacity_.load(std::memory_order_acquire);
    }
private:
    std::atomic<std::uint64_t> capacity_{0};
};
} // namespace Eden::VulkanMemory
