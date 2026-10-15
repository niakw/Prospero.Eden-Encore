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
    std::optional<Sequence> EnqueueTracked(unsigned core, std::uint64_t address,
                                           std::uint64_t size) {
        const auto ticket = EnqueueImpl(core, address, size, true);
        if (!ticket) return std::nullopt;
        return ticket->sequence;
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
        if (closed_ || ticket.generation != generation_ || ticket.sequence == 0 ||
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

    // Generation-tagged wait for two-phase reservations. A stale ticket
    // cannot become valid again after an idle session reset.
    bool WaitUntil(Ticket ticket) {
        std::unique_lock lock(mutex_);
        if (ticket.generation != generation_ || ticket.sequence == 0 ||
            ticket.sequence > accepted_) return false;
        completed_cv_.wait(lock, [&] {
            return completed_ >= ticket.sequence || closed_ ||
                   generation_ != ticket.generation;
        });
        return generation_ == ticket.generation &&
               completed_ >= ticket.sequence;
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

    // GPU owner only. Capture ONE finite FIFO batch while holding the queue
    // mutex, then replay it without that mutex. New enqueues remain pending
    // until a later GPU boundary, even if they arrive during replay.
    //
    // The requested watermark is a MINIMUM completion target, not an upper
    // cutoff: entries merged into the tail or accepted before this snapshot
    // may be included. No callback may run before its guest payload is
    // published (a separate, currently UNPROVEN native contract).
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
        std::vector<Write> work;
        {
            std::lock_guard lock(mutex_);
            if (watermark > accepted_ || completed_ >= watermark) return 0;
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
        for (const auto& item : work) {
            replay(item.core, item.range.begin, item.range.end - item.range.begin);
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
        if (generation_ == std::numeric_limits<std::uint64_t>::max()) {
            std::terminate(); // Never recycle a session ticket generation.
        }
        ++generation_;
        closed_ = false;
    }

private:
    std::optional<Ticket> EnqueueImpl(unsigned core, std::uint64_t address,
                                      std::uint64_t size, bool published) {
        if (core >= Cores || size == 0 ||
            size > std::numeric_limits<std::uint64_t>::max() - address)
            return std::nullopt;
        const auto end = address + size;
        std::lock_guard lock(mutex_);
        if (closed_ || accepted_ == std::numeric_limits<Sequence>::max())
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
    std::uint64_t generation_{1};
    bool closed_{};
};
} // namespace Eden::GpuDeferredWrite
