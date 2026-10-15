// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Source-only candidate: session-owned FIFO for deferred guest cache writes.
// This header does not activate deferred writes in the native renderer.
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <limits>
#include <mutex>
#include <utility>
#include <vector>

namespace Eden::GpuDeferredWrite {
struct Range {
    std::uint64_t begin{}, end{}; // half-open
};
struct Write {
    unsigned core{};
    Range range{};
};

class Queue {
public:
    static constexpr unsigned Cores = 4;
    static constexpr std::uint64_t PageBytes = 4096;
    static constexpr std::uint64_t DirtyRegionBytes = PageBytes / 2;
    // Limit queued invalidations to about 192 KiB of metadata; when full the
    // caller MUST use the original blocking cache write path (not drop data).
    static constexpr std::uint64_t MaxPendingEntries = 8192;

    // Assign a single linearization point to all guest cores. Per-core drain
    // order would reorder dependent writes from distinct CPU producers.
    bool Enqueue(unsigned core, std::uint64_t address, std::uint64_t size) {
        if (core >= Cores || size == 0 ||
            size > std::numeric_limits<std::uint64_t>::max() - address) return false;
        const auto end = address + size;
        std::lock_guard lock(mutex_);
        if (!queue_.empty()) {
            auto& tail = queue_.back();
            const auto& last = tail.range;
            if (tail.core == core &&
                (address / DirtyRegionBytes) == ((end - 1) / DirtyRegionBytes) &&
                (last.begin / DirtyRegionBytes) == ((last.end - 1) / DirtyRegionBytes) &&
                (address / DirtyRegionBytes) == (last.begin / DirtyRegionBytes) &&
                address <= last.end && last.begin <= end) {
                tail.range.begin = std::min(last.begin, address);
                tail.range.end = std::max(last.end, end);
                pending_.store(true, std::memory_order_release);
                return true;
            }
        }
        if (queue_.size() >= MaxPendingEntries) return false;
        queue_.push_back({core, {address, end}});
        pending_.store(true, std::memory_order_release);
        return true;
    }

    bool Pending() const noexcept {
        return pending_.load(std::memory_order_acquire);
    }

    // Single GPU consumer. Snapshot all queued writes atomically, preserve
    // their inter-core enqueue order, and replay without holding queue mutex.
    // Reentrant enqueues are drained in the following pass.
    template<class Replay>
    std::uint64_t Drain(Replay&& replay) {
        std::uint64_t count = 0;
        while (pending_.exchange(false, std::memory_order_acq_rel)) {
            std::vector<Write> work;
            {
                std::lock_guard lock(mutex_);
                work.swap(queue_);
            }
            for (const auto& item : work) {
                replay(item.core, item.range.begin, item.range.end - item.range.begin);
                ++count;
            }
        }
        return count;
    }

    // Only after all guest producers and GPU consumer are joined. Not
    // concurrently callable with Enqueue() or Drain().
    void ResetAfterQuiescence() {
        std::lock_guard lock(mutex_);
        queue_.clear();
        pending_.store(false, std::memory_order_release);
    }

private:
    std::mutex mutex_;
    std::vector<Write> queue_;
    std::atomic<bool> pending_{false};
};
} // namespace Eden::GpuDeferredWrite
