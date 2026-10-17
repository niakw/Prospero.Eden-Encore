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
assert cmake.count("native-hle-overrides.cmake") == 1
assert 'write_derived("${PORT_BUILD_DIR}/k_thread.cpp"' not in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/k_thread.cpp"' not in cmake
assert "file(READ" not in module and "string(REPLACE" not in module
assert "write_derived(" not in module
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
assert active == pinned.replace(old, fixed), "Unexpected maintained KThread drift"
print("ENCORE_HLE_SOURCE_LAYOUT_PASS source_files=11 generated_k_thread=0")
