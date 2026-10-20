#!/usr/bin/env python3
"""Verify source/prepare/test boundaries for maintained HLE overrides.

Only reads versioned files; never modifies source or builds production objects.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[3]
cmake = (root / "headless/CMakeLists.txt").read_text()
module = (root / "vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/verify/hle/check-hle-overlay-layout.py" in workflow
assert cmake.count('include("${PORT_ROOT}/vendor/encore-active/eden-threading/native-hle-overrides.cmake")') == 1
assert 'write_derived("${PORT_BUILD_DIR}/k_thread.cpp"' not in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/k_thread.cpp"' not in cmake
assert not any(
    line.lstrip().startswith(("file(READ", "string(REPLACE", "write_derived("))
    for line in module.splitlines()
)
assert module.count("function(encore_replace_core_source pinned relative)") == 1
assert module.count("get_target_property(sources core SOURCES)") == 1
assert module.count("list(REMOVE_ITEM sources") == 1
assert module.count("list(APPEND sources") == 1
assert "if(EDEN_BLOCKING_GUEST_CONTEXT_LOCKS)" in module
assert "if(PS5_NATIVE)" in module
assert 'target_include_directories(core BEFORE PUBLIC "${_encore_sync_root}")' in module

thread_root = root / "vendor/encore-active/eden-threading/src/core/hle/kernel"
sync_root = root / "vendor/encore-active/eden-sync/src/core/hle/kernel"
for relative in (
    "k_thread.cpp", "k_thread.h", "k_slab_heap.h", "k_scheduler.cpp",
    "slab_helpers.h", "k_worker_task_manager.h",
    "k_condition_variable.cpp", "k_address_arbiter.cpp",
    "svc/svc_condition_variable.cpp", "svc/svc_address_arbiter.cpp",
    "svc/svc_synchronization.cpp", "svc/svc_thread.cpp",
):
    assert (thread_root / relative).is_file(), ("missing maintained source", relative)
    assert relative.split("/")[-1] in module, ("missing CMake selection", relative)
assert (sync_root / "k_synchronization_object.h").is_file()

pinned = (root / "vendor/sources/eden/src/core/hle/kernel/k_thread.cpp").read_text()
active = (thread_root / "k_thread.cpp").read_text()
old = """        // Acquire the scheduler lock.
        KScopedSchedulerLock sl{kernel};

        // Signal.
        m_signaled = true;
        KSynchronizationObject::NotifyAvailable(kernel);

        // Close the thread.
        this->Close(kernel);"""
fixed = """        {
            KScopedSchedulerLock sl{kernel};
            m_signaled = true;
            KSynchronizationObject::NotifyAvailable(kernel);
        }

        // Finalization may block; scheduling must be enabled here.
        this->Close(kernel);"""
assert pinned.count(old) == 1
# The maintained wait lifecycle also publishes the wait queue before the
# state transition. Check both narrow deviations from the pinned source.
wait_before = """    void KThread::BeginWait(KernelCore& kernel, KThreadQueue* queue) {
        // Set our state as waiting.
        this->SetState(kernel, ThreadState::Waiting);

        // Set our wait queue.
        m_wait_queue = queue;
    }"""
wait_after = """    void KThread::BeginWait(KernelCore& kernel, KThreadQueue* queue) {
        // Publish the wait queue before exposing the waiting state.
        // A scheduler state-change observer must not see a waiting thread
        // with no queue to route its wakeup/cancellation to.
        m_wait_queue = queue;
        this->SetState(kernel, ThreadState::Waiting);
    }"""
assert pinned.count(wait_before) == 1
notify_before = "    void KThread::NotifyAvailable(KernelCore& kernel, KSynchronizationObject* signaled_object, Result wait_result) {\n        // Lock the scheduler.\n        KScopedSchedulerLock sl(kernel);\n        // If we're waiting, notify our queue that we're available.\n        if (this->GetState() == ThreadState::Waiting) {\n            m_wait_queue->NotifyAvailable(kernel, this, signaled_object, wait_result);\n        }\n    }"
notify_after = "    void KThread::NotifyAvailable(KernelCore& kernel, KSynchronizationObject* signaled_object, Result wait_result) {\n        // Lock the scheduler.\n        KScopedSchedulerLock sl(kernel);\n        // If we're waiting, notify our queue that we're available.\n        if (this->GetState() == ThreadState::Waiting) {\n            if (m_wait_queue == nullptr) {\n                ASSERT_MSG(false, \"wait_queue is nullptr!\");\n                return;\n            }\n            m_wait_queue->NotifyAvailable(kernel, this, signaled_object, wait_result);\n        }\n    }"
cancel_before = "    void KThread::CancelWait(KernelCore& kernel, Result wait_result, bool cancel_timer_task) {\n        // Lock the scheduler.\n        KScopedSchedulerLock sl(kernel);\n        // If we're waiting, notify our queue that we're available.\n        if (this->GetState() == ThreadState::Waiting) {\n            m_wait_queue->CancelWait(kernel, this, wait_result, cancel_timer_task);\n        }\n    }"
cancel_after = "    void KThread::CancelWait(KernelCore& kernel, Result wait_result, bool cancel_timer_task) {\n        // Lock the scheduler.\n        KScopedSchedulerLock sl(kernel);\n        // If we're waiting, notify our queue that we're available.\n        if (this->GetState() == ThreadState::Waiting) {\n            if (m_wait_queue == nullptr) {\n                ASSERT_MSG(false, \"wait_queue is nullptr!\");\n                return;\n            }\n            m_wait_queue->CancelWait(kernel, this, wait_result, cancel_timer_task);\n        }\n    }"
assert pinned.count(notify_before) == pinned.count(cancel_before) == 1
# A no-op state transition must not publish an identical atomic state.
state_before = "        const ThreadState old_state = m_thread_state.load(std::memory_order_relaxed);\n        m_thread_state.store(\n            static_cast<ThreadState>((old_state & ~ThreadState::Mask) | (state & ThreadState::Mask)),\n            std::memory_order_relaxed);\n        if (m_thread_state.load(std::memory_order_relaxed) != old_state) {\n            KScheduler::OnThreadStateChanged(kernel, this, old_state);\n        }"
state_after = "        const ThreadState old_state = m_thread_state.load(std::memory_order_relaxed);\n        const ThreadState next_state = static_cast<ThreadState>(\n            (old_state & ~ThreadState::Mask) | (state & ThreadState::Mask));\n        // Scheduler lock serializes state transitions. Avoid an atomic store\n        // and second atomic load for an unchanged runnable/waiting state.\n        if (next_state != old_state) {\n            m_thread_state.store(next_state, std::memory_order_relaxed);\n            KScheduler::OnThreadStateChanged(kernel, this, old_state);\n        }"
assert pinned.count(state_before) == 1
assert active == (pinned.replace(old, fixed).replace(wait_before, wait_after)
                  .replace(notify_before, notify_after)
                  .replace(cancel_before, cancel_after)
                  .replace(state_before, state_after)), "Unexpected maintained KThread drift"
slab_pinned = (root / "vendor/sources/eden/src/core/hle/kernel/slab_helpers.h").read_text()
slab_active = (thread_root / "slab_helpers.h").read_text()
slab_before = """        Free(kernel, static_cast<Derived*>(this));
        if (is_initialized) {
            Derived::PostDestroy(kernel, arg);
        }"""
slab_after = """        if (is_initialized) {
            Derived::PostDestroy(kernel, arg);
        }
        Free(kernel, static_cast<Derived*>(this));"""
assert slab_pinned.count(slab_before) == 2
assert slab_active == slab_pinned.replace(slab_before, slab_after)
worker_pinned = (root / "vendor/sources/eden/src/core/hle/kernel/k_worker_task_manager.h").read_text()
worker_active = (thread_root / "k_worker_task_manager.h").read_text()
worker_old = "    KWorkerTaskManager();"
worker_new = "    KWorkerTaskManager();\n    void WaitForRequests() { m_waiting_thread.WaitForRequests(); }"
assert worker_pinned.count(worker_old) == 1
assert worker_active == worker_pinned.replace(worker_old, worker_new)
assert "configure_file(" in module and "COPYONLY)" in module
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/slab_helpers.h"' not in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/k_worker_task_manager.h"' not in cmake
print("ENCORE_HLE_SOURCE_LAYOUT_PASS source_files=13 generated_k_thread=0")
