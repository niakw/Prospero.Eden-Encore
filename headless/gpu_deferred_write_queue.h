// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Source-only, session-owned FIFO for deferred guest cache writes.
// Completion watermarks are a host contract, NOT a GPU fence or runtime enable.
#include <algorithm>
#include <condition_variable>
#include <cstdint>
#include <exception>
#include <limits>
#include <mutex>
#include <optional>
#include <utility>
#include <vector>

namespace Eden::GpuDeferredWrite {
struct Range {
    std::uint64_t begin{}, end{}; // half-open
};
struct Write {
    unsigned core{};
    Range range{};
    // A merged FIFO entry acknowledges all consecutive enqueues through this id.
    std::uint64_t last_sequence{};
};

class Queue {
public:
    using Sequence = std::uint64_t;
    static constexpr unsigned Cores = 4;
    static constexpr std::uint64_t PageBytes = 4096;
    static constexpr std::uint64_t DirtyRegionBytes = PageBytes / 2;

    // The mutex assigns one total order across guest cores. A failed enqueue
    // MUST NOT be treated as an acknowledged deferred write.
    std::optional<Sequence> EnqueueTracked(unsigned core, std::uint64_t address,
                                           std::uint64_t size) {
        if (core >= Cores || size == 0 ||
            size > std::numeric_limits<std::uint64_t>::max() - address) return std::nullopt;
        const auto end = address + size;
        std::lock_guard lock(mutex_);
        if (closed_ || accepted_ == std::numeric_limits<Sequence>::max()) {
            return std::nullopt;
        }
        const auto sequence = accepted_ + 1;
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
                tail.last_sequence = sequence;
                accepted_ = sequence;
                return sequence;
            }
        }
        queue_.push_back({core, {address, end}, sequence});
        accepted_ = sequence;
        return sequence;
    }

    // Existing opt-in native bridge uses this signature. There is deliberately
    // no automatic fallback for a rejected write: caller must not reorder work.
    bool Enqueue(unsigned core, std::uint64_t address, std::uint64_t size) {
        return EnqueueTracked(core, address, size).has_value();
    }

    Sequence AcceptedSequence() const {
        std::lock_guard lock(mutex_);
        return accepted_;
    }
    Sequence CompletedSequence() const {
        std::lock_guard lock(mutex_);
        return completed_;
    }

    // True includes entries being replayed but not yet acknowledged.
    bool Pending() const {
        std::lock_guard lock(mutex_);
        return completed_ != accepted_;
    }

    // CPU caller: the GPU owner MUST have been scheduled before this wait;
    // no GPU cache lock or queue mutex may be held by the waiter. Completion
    // only means the replay callback returned, NOT completion of a Vulkan fence.
    // Returns false on shutdown or for a ticket this session never accepted.
    bool WaitUntil(Sequence sequence) {
        std::unique_lock lock(mutex_);
        if (sequence > accepted_) return false;
        completed_cv_.wait(lock, [&] { return completed_ >= sequence || closed_; });
        return completed_ >= sequence;
    }

    // GPU owner only. Drain a fixed watermark so continuing guest producers
    // cannot indefinitely starve the next draw/command. The consumer never
    // holds the queue lock while calling the original rasterizer.
    template<class Replay>
    std::uint64_t DrainThrough(Sequence watermark, Replay&& replay) {
        // Only one GPU owner can replay a session at a time. A second owner
        // waits for the first before it rechecks its requested watermark.
        // Recursive replay on the same thread is a caller contract violation:
        // fail fast rather than deadlock or silently skip an invalidation.
        if (active_consumer_ == this) std::terminate();
        std::unique_lock owner(consumer_mutex_);
        struct RestoreOwner {
            const Queue*& slot;
            const Queue* prior;
            ~RestoreOwner() { slot = prior; }
        } restore{active_consumer_, active_consumer_};
        active_consumer_ = this;
        std::uint64_t count = 0;
        while (true) {
            std::vector<Write> work;
            {
                std::lock_guard lock(mutex_);
                if (completed_ >= watermark) break;
                work.swap(queue_);
            }
            // This can only happen if the single-GPU-consumer contract is
            // violated, or if a caller supplied a future/invalid watermark.
            if (work.empty()) break;
            Sequence last_done = 0;
            for (const auto& item : work) {
                replay(item.core, item.range.begin, item.range.end - item.range.begin);
                last_done = item.last_sequence;
                ++count;
            }
            {
                std::lock_guard lock(mutex_);
                completed_ = std::max(completed_, last_done);
            }
            completed_cv_.notify_all();
        }
        return count;
    }

    template<class Replay>
    std::uint64_t Drain(Replay&& replay) {
        return DrainThrough(AcceptedSequence(), std::forward<Replay>(replay));
    }

    // Wake CPU waiters when the owning title begins shutdown. Producers must
    // eventually quiesce before the queue/memory manager itself is destroyed.
    void Close() {
        {
            std::lock_guard lock(mutex_);
            closed_ = true;
        }
        completed_cv_.notify_all();
    }

    // Only after all producers, waiters and GPU consumer have joined. No old
    // session sequence ticket may be reused after reset.
    void ResetAfterQuiescence() {
        std::lock_guard lock(mutex_);
        queue_.clear();
        accepted_ = completed_ = 0;
        closed_ = false;
    }

private:
    std::mutex consumer_mutex_; // Never held by producer or CPU waiter.
    static inline thread_local const Queue* active_consumer_{nullptr};
    mutable std::mutex mutex_;
    std::condition_variable completed_cv_;
    std::vector<Write> queue_;
    Sequence accepted_{};
    Sequence completed_{};
    bool closed_{};
};
} // namespace Eden::GpuDeferredWrite
