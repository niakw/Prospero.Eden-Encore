// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Source-only, session-owned FIFO for deferred guest cache writes.
// Completion watermarks are a host contract, NOT a GPU fence or runtime enable.
#include <algorithm>
#include <atomic>
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
    bool published{true}; // False until producer finishes the guest RAM store.
};

class Queue {
public:
    using Sequence = std::uint64_t;
    struct Ticket {
        Sequence sequence{};
        std::uint64_t generation{};
    };
    static constexpr unsigned Cores = 4;
    static constexpr std::uint64_t PageBytes = 4096;
    static constexpr std::uint64_t DirtyRegionBytes = PageBytes / 2;

    // Legacy host-only immediate publication. The inactive native bridge
    // still calls this BEFORE its backing RAM store; that path is unsafe to
    // activate until it is replaced by Reserve + post-store Publish.
    std::optional<Ticket> EnqueueTracked(unsigned core, std::uint64_t address,
                                         std::uint64_t size) {
        return EnqueueImpl(core, address, size, true);
    }

    // Reserve an order position before touching guest RAM. The GPU consumer
    // cannot replay this entry until the producer has finished the actual
    // write and explicitly called Publish(ticket).
    std::optional<Ticket> Reserve(unsigned core, std::uint64_t address,
                                  std::uint64_t size) {
        return EnqueueImpl(core, address, size, false);
    }

    // Releasing mutex_ after the producer's real store publishes the payload
    // to a GPU consumer that subsequently acquires the same mutex. Publishing
    // a stale session ticket, a nonexistent ticket or an already published
    // entry fails without advancing the FIFO.
    bool Publish(Ticket ticket) {
        std::lock_guard lock(mutex_);
        if (closed_ || failed_ || ticket.generation != generation_ || ticket.sequence == 0 ||
            ticket.sequence > accepted_) return false;
        for (auto& entry : queue_) {
            if (entry.last_sequence == ticket.sequence && !entry.published) {
                entry.published = true;
                return true;
            }
        }
        return false;
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

    // A callback exception permanently poisons this title's queue. Replaying
    // it again is unsafe because the callback may have made partial cache
    // changes before throwing. Only quiescent teardown can clear the poison.
    bool Failed() const {
        std::lock_guard lock(mutex_);
        return failed_;
    }

    // Generation-tagged wait for either queued or reserved writes.
    // Caller MUST schedule a GPU-owner drain, without holding any GPU cache
    // lock, before waiting. The result is replay-callback completion only,
    // NOT GPU/device-fence completion or safe native CPU-read synchronization.
    // A stale ticket cannot become valid again after an idle session reset.
    bool WaitUntil(Ticket ticket) {
        std::unique_lock lock(mutex_);
        if (ticket.generation != generation_ || ticket.sequence == 0 ||
            ticket.sequence > accepted_) return false;
        completed_cv_.wait(lock, [&] {
            return completed_ >= ticket.sequence || closed_ || failed_ ||
                   generation_ != ticket.generation;
        });
        return generation_ == ticket.generation &&
               completed_ >= ticket.sequence;
    }

    // Deliberately NO WaitUntil(Sequence) overload. Sequence numbers reset
    // after quiescence; only generation-tagged tickets can be waited upon.
    // A stale read ticket must never succeed against another title session.

    // GPU owner only. Capture ONE finite FIFO batch while holding the queue
    // mutex, then replay it without that mutex. New enqueues remain pending
    // until a later GPU boundary, even if they arrive during replay.
    //
    // The requested generation-tagged ticket is a MINIMUM completion target,
    // not an upper cutoff: entries accepted before the snapshot may be
    // included. A stale session's ticket cannot drain another session.
    // Only published guest payloads are eligible for replay.
    template<class Replay>
    std::uint64_t DrainThrough(Ticket target, Replay&& replay) {
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
        std::vector<Write> work;
        {
            std::lock_guard lock(mutex_);
            if (closed_ || failed_ || target.generation != generation_ || target.sequence == 0 ||
                target.sequence > accepted_ || completed_ >= target.sequence) return 0;
            // Reserve + Publish is ordered, but publishers can finish out of
            // order. Drain only the contiguous PUBLISHED prefix. Never
            // overtake an earlier uncommitted guest RAM write.
            std::size_t ready = 0;
            while (ready != queue_.size() && queue_[ready].published) ++ready;
            if (ready == 0) return 0;
            if (ready == queue_.size()) {
                work.swap(queue_);
            } else {
                work.assign(queue_.begin(), queue_.begin() + ready);
                queue_.erase(queue_.begin(), queue_.begin() + ready);
            }
        }
        // Under the consumer mutex no other replay can be in flight.
        // The snapshot includes ONLY the published FIFO prefix.
        try {
            for (const auto& item : work) {
                replay(item.core, item.range.begin, item.range.end - item.range.begin);
            }
        } catch (...) {
            // The callback may have partially modified GPU caches. Never
            // acknowledge this batch, retry it, or permit later work to
            // overtake it. Report failure to readers and propagate the error.
            {
                std::lock_guard lock(mutex_);
                failed_ = true;
            }
            completed_cv_.notify_all();
            throw;
        }
        {
            std::lock_guard lock(mutex_);
            completed_ = work.back().last_sequence;
        }
        completed_cv_.notify_all();
        return static_cast<std::uint64_t>(work.size());
    }

    template<class Replay>
    std::uint64_t Drain(Replay&& replay) {
        Ticket target{};
        {
            std::lock_guard lock(mutex_);
            target = {accepted_, generation_};
        }
        return DrainThrough(target, std::forward<Replay>(replay));
    }

    // Shutdown barrier: reject future work, release CPU waiters, then wait
    // until any in-flight GPU replay callback has returned. No GPU cache lock
    // may be held while calling Close(). Never call it recursively from replay.
    // Producers and waiters still must be joined before destroying the Queue.
    void Close() {
        if (active_consumer_ == this) std::terminate();
        {
            std::lock_guard lock(mutex_);
            closed_ = true;
            close_completed_ = false;
        }
        completed_cv_.notify_all();
        // DrainThrough holds consumer_mutex_ for the complete replay batch.
        // Lock order is consumer_mutex_ -> mutex_ on a drain; never hold
        // mutex_ while waiting for this lock.
        std::lock_guard owner(consumer_mutex_);
        {
            std::lock_guard lock(mutex_);
            close_completed_ = true;
        }
    }

    // Reset only AFTER Close(), joining producers/readers and releasing all
    // GPU cache locks. Serialize with the consumer as an extra safety barrier.
    // Reject open-session resets instead of silently recycling live tickets.
    // A caller must still enforce full thread quiescence before destruction.
    bool ResetAfterQuiescence() {
        if (active_consumer_ == this) return false;
        std::lock_guard owner(consumer_mutex_);
        std::lock_guard lock(mutex_);
        if (!closed_ || !close_completed_) return false;
        queue_.clear();
        accepted_ = completed_ = 0;
        generation_ = FreshGeneration(); // Unique across ALL queue instances.
        failed_ = false;
        closed_ = false;
        close_completed_ = false;
        return true;
    }

private:
    // Tickets must identify the owning queue as well as the title session.
    // An epoch starting at 1 for every Queue would permit cross-address-space
    // confusion whenever two independent queues reached the same sequence.
    static std::uint64_t FreshGeneration() {
        auto prior = next_generation_.load(std::memory_order_relaxed);
        do {
            if (prior == std::numeric_limits<std::uint64_t>::max())
                std::terminate(); // Never issue a duplicate epoch on wrap.
        } while (!next_generation_.compare_exchange_weak(
            prior, prior + 1, std::memory_order_relaxed));
        return prior + 1;
    }
    static inline std::atomic<std::uint64_t> next_generation_{0};

    std::optional<Ticket> EnqueueImpl(unsigned core, std::uint64_t address,
                                      std::uint64_t size, bool published) {
        if (core >= Cores || size == 0 ||
            size > std::numeric_limits<std::uint64_t>::max() - address)
            return std::nullopt;
        const auto end = address + size;
        std::lock_guard lock(mutex_);
        if (closed_ || failed_ || accepted_ == std::numeric_limits<Sequence>::max())
            return std::nullopt;
        const Sequence sequence = accepted_ + 1;
        if (published && !queue_.empty()) {
            auto& tail = queue_.back();
            const auto& last = tail.range;
            if (tail.published && tail.core == core &&
                (address / DirtyRegionBytes) == ((end - 1) / DirtyRegionBytes) &&
                (last.begin / DirtyRegionBytes) == ((last.end - 1) / DirtyRegionBytes) &&
                (address / DirtyRegionBytes) == (last.begin / DirtyRegionBytes) &&
                address <= last.end && last.begin <= end) {
                tail.range.begin = std::min(last.begin, address);
                tail.range.end = std::max(last.end, end);
                tail.last_sequence = sequence;
                accepted_ = sequence;
                return Ticket{sequence, generation_};
            }
        }
        queue_.push_back({core, {address, end}, sequence, published});
        accepted_ = sequence;
        return Ticket{sequence, generation_};
    }

    std::mutex consumer_mutex_; // Never held by producer or CPU waiter.
    static inline thread_local const Queue* active_consumer_{nullptr};
    mutable std::mutex mutex_;
    std::condition_variable completed_cv_;
    std::vector<Write> queue_;
    Sequence accepted_{};
    Sequence completed_{};
    std::uint64_t generation_{FreshGeneration()};
    bool closed_{};
    bool failed_{};
    bool close_completed_{};
};
} // namespace Eden::GpuDeferredWrite
