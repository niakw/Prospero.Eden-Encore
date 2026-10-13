// SPDX-License-Identifier: GPL-3.0-or-later
// Read-only, native development witness for a game that stops presenting.
// This is NOT a watchdog, a scheduler, a queue implementation or a recovery path.
// Never walk kernel thread lists, sample another thread's stack, or change timing
// or wake-up semantics here. Publish only bounded atomic state.
#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>

namespace Eden::GameplayStallTrace {

enum class GpuPhase : unsigned {
    Uninitialized = 0,
    AwaitingCommand = 1,  // includes normal, harmless guest idle
    DispatchSubmit = 2,
    DispatchTick = 3,
    DispatchFlush = 4,
    DispatchInvalidate = 5,
    PublishingFence = 6,
    CommandFinished = 7,
};

inline std::atomic<bool> enabled{false};
inline std::atomic<unsigned> gpu_phase{0};
inline std::atomic<long long> gpu_phase_since_ns{0};
inline std::atomic<unsigned long long> gpu_commands_completed{0};
inline std::atomic<unsigned long long> gpu_producer_waits_started{0};
inline std::atomic<unsigned long long> gpu_producer_waits_finished{0};
inline std::atomic<unsigned> gpu_producer_waits_active{0};
inline std::atomic<unsigned long long> gpu_producer_waits_over_100ms{0};
inline std::atomic<unsigned long long> gpu_producer_wait_max_ns{0};
inline std::atomic<unsigned long long> binder_dequeues_started{0};
inline std::atomic<unsigned long long> binder_dequeues_finished{0};
inline std::atomic<unsigned> binder_dequeues_active{0};
inline std::atomic<unsigned long long> binder_dequeues_over_100ms{0};
inline std::atomic<unsigned long long> binder_dequeue_max_ns{0};

inline long long ClockNs() noexcept {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

inline void Max(std::atomic<unsigned long long>& target, unsigned long long value) noexcept {
    unsigned long long prev = target.load(std::memory_order_relaxed);
    while (prev < value &&
           !target.compare_exchange_weak(prev, value, std::memory_order_relaxed)) {}
}

// Call only after the previous title/worker has stopped.
inline void ResetForTitle(bool diagnostic_mode) noexcept {
    enabled.store(false, std::memory_order_release);
    gpu_phase.store(0, std::memory_order_relaxed);
    gpu_phase_since_ns.store(0, std::memory_order_relaxed);
    gpu_commands_completed.store(0, std::memory_order_relaxed);
    gpu_producer_waits_started.store(0, std::memory_order_relaxed);
    gpu_producer_waits_finished.store(0, std::memory_order_relaxed);
    gpu_producer_waits_active.store(0, std::memory_order_relaxed);
    gpu_producer_waits_over_100ms.store(0, std::memory_order_relaxed);
    gpu_producer_wait_max_ns.store(0, std::memory_order_relaxed);
    binder_dequeues_started.store(0, std::memory_order_relaxed);
    binder_dequeues_finished.store(0, std::memory_order_relaxed);
    binder_dequeues_active.store(0, std::memory_order_relaxed);
    binder_dequeues_over_100ms.store(0, std::memory_order_relaxed);
    binder_dequeue_max_ns.store(0, std::memory_order_relaxed);
    enabled.store(diagnostic_mode, std::memory_order_release);
}

inline void GpuMark(GpuPhase phase) noexcept {
    if (!enabled.load(std::memory_order_relaxed)) return;
    gpu_phase_since_ns.store(ClockNs(), std::memory_order_relaxed);
    gpu_phase.store(static_cast<unsigned>(phase), std::memory_order_release);
}

inline void GpuCommandFinished() noexcept {
    if (!enabled.load(std::memory_order_relaxed)) return;
    gpu_commands_completed.fetch_add(1, std::memory_order_relaxed);
    GpuMark(GpuPhase::CommandFinished);
}

inline long long WaitStart(std::atomic<unsigned long long>& starts,
                           std::atomic<unsigned>& active) noexcept {
    if (!enabled.load(std::memory_order_relaxed)) return 0;
    const long long begin = ClockNs();
    starts.fetch_add(1, std::memory_order_relaxed);
    active.fetch_add(1, std::memory_order_relaxed);
    return begin;
}

inline void WaitEnd(long long start, std::atomic<unsigned long long>& finished,
                    std::atomic<unsigned>& active,
                    std::atomic<unsigned long long>& over_100ms,
                    std::atomic<unsigned long long>& max_ns) noexcept {
    if (!start) return;
    const long long end = ClockNs();
    if (end > start) {
        const auto duration = static_cast<unsigned long long>(end - start);
        Max(max_ns, duration);
        if (duration >= 100'000'000ULL)
            over_100ms.fetch_add(1, std::memory_order_relaxed);
    }
    finished.fetch_add(1, std::memory_order_relaxed);
    active.fetch_sub(1, std::memory_order_relaxed);
}

inline long long GpuProducerWaitStart() noexcept {
    return WaitStart(gpu_producer_waits_started, gpu_producer_waits_active);
}
inline void GpuProducerWaitEnd(long long start) noexcept {
    WaitEnd(start, gpu_producer_waits_finished, gpu_producer_waits_active,
            gpu_producer_waits_over_100ms, gpu_producer_wait_max_ns);
}
inline long long BinderDequeueStart() noexcept {
    return WaitStart(binder_dequeues_started, binder_dequeues_active);
}
inline void BinderDequeueEnd(long long start) noexcept {
    WaitEnd(start, binder_dequeues_finished, binder_dequeues_active,
            binder_dequeues_over_100ms, binder_dequeue_max_ns);
}

} // namespace Eden::GameplayStallTrace
