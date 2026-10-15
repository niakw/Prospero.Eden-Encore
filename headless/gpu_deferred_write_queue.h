// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Isolated host-verified candidate for replaying guest writes past GPU cache
// mutex contention. NOT wired to guest memory until fence semantics are proven.
#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <limits>
#include <mutex>
#include <utility>
#include <vector>

namespace Eden::GpuDeferredWrite {

struct Range {
    std::uint64_t begin{}, end{}; // half-open [begin, end)
};

class Queue {
public:
    static constexpr unsigned Cores = 4;
    static constexpr std::uint64_t PageBytes = 4096;

    // Reject invalid input instead of publishing an impossible dirty range.
    // Returns false to request caller's ORIGINAL blocking invalidation path.
    bool Enqueue(unsigned core, std::uint64_t address, std::uint64_t size) {
        if (core >= Cores || size == 0 ||
            size > std::numeric_limits<std::uint64_t>::max() - address) return false;
        auto& slot = cores_[core];
        std::lock_guard lock(slot.mutex);
        const auto end = address + size;
        // Only combine writes entirely within the SAME guest page; widening
        // across a GPU-modified boundary would break fence ordering.
        if (!slot.pending.empty()) {
            auto& tail = slot.pending.back();
            if ((address / PageBytes) == ((end - 1) / PageBytes) &&
                (tail.begin / PageBytes) == ((tail.end - 1) / PageBytes) &&
                (address / PageBytes) == (tail.begin / PageBytes)) {
                tail.begin = std::min(tail.begin, address);
                tail.end = std::max(tail.end, end);
                pending_.store(true, std::memory_order_release);
                return true;
            }
        }
        slot.pending.push_back({address, end});
        pending_.store(true, std::memory_order_release);
        return true;
    }

    bool Pending() const noexcept {
        return pending_.load(std::memory_order_acquire);
    }

    // Must run on the GPU owner, outside BOTH cache mutexes, before work that
    // could read any of the guest ranges. Callback MUST pass GPU-owned writes
    // to the original dirty/fence collection path, not upload them early.
    // If a writer enqueues during one pass, drain the new batch as well.
    template <class Replay>
    std::uint64_t Drain(Replay&& replay) {
        std::uint64_t batches = 0;
        while (pending_.exchange(false, std::memory_order_acq_rel)) {
            for (unsigned core = 0; core < Cores; ++core) {
                std::vector<Range> work;
                {
                    std::lock_guard lock(cores_[core].mutex);
                    work.swap(cores_[core].pending);
                }
                for (const auto& range : work) {
                    // Callback cannot hold this queue's lock: it may acquire
                    // cache mutexes and trigger unrelated callbacks.
                    replay(core, range.begin, range.end - range.begin);
                    ++batches;
                }
            }
        }
        return batches;
    }

    // Only when guest core threads AND GPU worker have quiesced at shutdown.
    // Cannot run concurrently with Enqueue or Drain.
    void ResetAfterQuiescence() {
        for (auto& core : cores_) {
            std::lock_guard lock(core.mutex);
            core.pending.clear();
        }
        pending_.store(false, std::memory_order_release);
    }

private:
    struct PerCore {
        std::mutex mutex;
        std::vector<Range> pending;
    };
    std::array<PerCore, Cores> cores_{};
    std::atomic<bool> pending_{false};
};

} // namespace Eden::GpuDeferredWrite
