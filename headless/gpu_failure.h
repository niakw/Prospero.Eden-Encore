// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <exception>
#include <mutex>
#include <utility>

namespace Eden {
inline std::mutex gpu_failure_mutex;
// One delivery per failure for the UI observer, independent of the persistent
// fatal state consulted by worker/synchronization waiters.
inline std::exception_ptr gpu_failure;
inline std::exception_ptr gpu_failure_latched;
inline void RecordGpuFailure(std::exception_ptr error) {
    if (!error) return;
    std::lock_guard lock(gpu_failure_mutex);
    if (!gpu_failure_latched) gpu_failure_latched = error;
    if (!gpu_failure) gpu_failure = std::move(error);
}
// A UI observer may already have consumed the notification. Every outstanding
// GPU waiter must still observe the fatal cause until the title is fully gone.
inline std::exception_ptr PeekGpuFailure() {
    std::lock_guard lock(gpu_failure_mutex);
    return gpu_failure_latched;
}
inline std::exception_ptr TakeGpuFailure() {
    std::lock_guard lock(gpu_failure_mutex);
    return std::exchange(gpu_failure, {});
}
// Only at the next title's launch boundary, once prior GPU workers have joined.
inline void ResetGpuFailureForTitle() {
    std::lock_guard lock(gpu_failure_mutex);
    gpu_failure = {};
    gpu_failure_latched = {};
}
}
