// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <exception>
#include <mutex>
#include <utility>

namespace Eden {
inline std::mutex gpu_failure_mutex;
inline std::exception_ptr gpu_failure;
inline void RecordGpuFailure(std::exception_ptr error) {
    std::lock_guard lock(gpu_failure_mutex);
    if (!gpu_failure) gpu_failure = std::move(error);
}
// Observe a recorded worker failure without consuming it. Multiple CPU
// waiters may depend on the same fatal event to stop waiting.
inline std::exception_ptr PeekGpuFailure() {
    std::lock_guard lock(gpu_failure_mutex);
    return gpu_failure;
}
inline std::exception_ptr TakeGpuFailure() {
    std::lock_guard lock(gpu_failure_mutex);
    return std::exchange(gpu_failure, {});
}
}
