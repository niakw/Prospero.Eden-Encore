#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify R300 quiet CPU/IO clock gates in actual selected native sources (host only)."""
from pathlib import Path
import platform, shutil, subprocess, sys, tempfile

cmake = (Path(__file__).resolve().parents[1] / "headless/CMakeLists.txt").read_text()
def section(start, end):
    assert cmake.count(start) == 1, start
    return cmake.split(start, 1)[1].split(end, 1)[0]

idle = section('string(REPLACE "${idle_old}" [=[', ']=] physical_core_source').strip()
assert idle.startswith("void PhysicalCore::Idle() {")
assert "const bool profile_idle = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed);" in idle
assert "const long long start = profile_idle ? ::Eden::Performance::NowNs() : 0;" in idle
assert "if (profile_idle)\n            ::Eden::Performance::CountIdle(" in idle
assert "m_on_interrupt.wait(lk, [this] { return m_is_interrupted; });" in idle
# The writer modifies m_is_interrupted under m_guard using ordinary stores.
# Do not permit an unlocked atomic builtin read in native development code.
assert "__atomic_load_n(&m_is_interrupted" not in cmake

# Buffer dequeue diagnostics also live in a tracked DEV-only source now.
dequeue = (Path(__file__).resolve().parents[1] /
           "vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
assert 'list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_DEQUEUE}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/buffer_queue_producer.cpp"' not in cmake
assert "const auto dequeue_start = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed) ? ::Eden::Performance::NowNs() : 0;" in dequeue
assert "if (dequeue_start) ::Eden::Performance::AddSince(::Eden::Performance::guest_dequeue_wait, dequeue_start);" in dequeue
assert dequeue.index("const auto dequeue_start") < dequeue.index("Status status = WaitForFreeSlotThenRelock(async")
assert dequeue.index("Status status = WaitForFreeSlotThenRelock(async") < dequeue.index("if (dequeue_start)")

# Host-syncpoint event-wait callback is now maintained C++ (DEV only).
nvctrl = (Path(__file__).resolve().parents[1] /
          "vendor/encore-active/eden-core/src/core/hle/service/nvdrv/devices/nvhost_ctrl.cpp").read_text()
assert 'list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_NVCTRL}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/nvhost_ctrl.cpp"' not in cmake
assert "const auto wait_start = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed) ? ::Eden::Performance::NowNs() : 0;" in nvctrl
assert "RegisterHostAction(fence_id, target_value, [this, slot, wait_start]()" in nvctrl
assert "if (wait_start) ::Eden::Performance::AddSince(::Eden::Performance::guest_sync_wait, wait_start);" in nvctrl
assert nvctrl.index("const auto wait_start") < nvctrl.index("RegisterHostAction(fence_id")
assert nvctrl.index("RegisterHostAction(fence_id") < nvctrl.index("if (wait_start)")

ipc = section('string(REPLACE "${ipc_old}"', ' ipc_source "${ipc_source}")')
# R393 additionally attributes sync IPC latency to its original guest thread.
# Quiet gameplay must still skip the clock and thread ID lookup entirely.
assert "const bool ipc_profile = ::Eden::Performance::detailed_gpu_profile.load" in ipc
assert "const auto ipc_start = ipc_profile ? ::Eden::Performance::NowNs() : 0;" in ipc
assert "const auto ipc_tid = ipc_profile ? GetCurrentThread(kernel).GetThreadId() : 0;" in ipc
assert "auto* const ipc_slot = ipc_profile ? ::Eden::Performance::BeginGuestIpc(ipc_tid, ipc_start) : nullptr;" in ipc
assert "if (ipc_profile) ::Eden::Performance::FinishGuestIpc(ipc_slot, ipc_tid, ipc_start," in ipc
assert "AddSince(::Eden::Performance::guest_ipc_wait" not in ipc
assert (ipc.index("const auto ipc_tid") < ipc.index("BeginGuestIpc(")
        < ipc.index("session->SendSyncRequest(") < ipc.index("FinishGuestIpc("))
assert "ipc_profile ? GetCurrentThread" in ipc and "ipc_profile ? ::Eden::Performance::BeginGuestIpc" in ipc
# The diagnostic filesystem units are now maintained C++ sources,
# no longer strings embedded in headless/CMakeLists.txt.
maintained = Path(__file__).resolve().parents[1] / "vendor/encore-active/eden-core/src/core/hle/service/filesystem/fsp"
fs_file = (maintained / "fs_i_file.cpp").read_text()
fs_storage = (maintained / "fs_i_storage.cpp").read_text()
assert 'EDEN_MAINTAINED_PROFILE_FS_FILE' in cmake
assert 'EDEN_MAINTAINED_PROFILE_FS_STORAGE' in cmake
for fragment, name in [(fs_file, "guest_fs_file"), (fs_storage, "guest_fs_storage")]:
    assert "const auto fs_start = ::Eden::Performance::detailed_gpu_profile.load" in fragment
    assert f"if (fs_start) {{\n        ::Eden::Performance::AddSince(::Eden::Performance::{name}, fs_start);" in fragment
assert fs_file.index("backend->Read(") < fs_file.index("if (fs_start)") < fs_file.index("EDEN_FS_FILE_READ")
assert fs_storage.index("EDEN_FS_SHORT_STORAGE") < fs_storage.index("if (fs_start)")
assert "fs_read != static_cast<std::size_t>(length)" in fs_storage
fs_open = (maintained / "fs_i_filesystem.cpp").read_text()
assert 'EDEN_MAINTAINED_PROFILE_FS_SYSTEM' in cmake
assert 'list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_FS_SYSTEM}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/fs_i_filesystem.cpp"' not in cmake
# All three requested operations must gate their diagnostic logging; no
# new clock sampling on the quiet (non-profiled) filesystem path.
guard = "if (::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed))"
assert fs_open.count(guard) == 3
for method, kind in (("OpenFile", "file"), ("OpenDirectory", "directory"),
                     ("GetEntryType", "entry")):
    start = fs_open.index("Result IFileSystem::" + method + "(")
    stop = fs_open.find("\nResult IFileSystem::", start + 1)
    body = fs_open[start:stop if stop >= 0 else len(fs_open)]
    assert guard in body and "EDEN_FS_OPEN kind=" + kind in body
    assert body.index("const Result fs_open_result") < body.index(guard)
    assert body.index(guard) < body.index("R_TRY(fs_open_result)")


if sys.platform == "darwin" and platform.machine() == "arm64":
    print("PASS: native clock/IPC/FS source gates; x86 pause mock deferred to Linux CI")
    raise SystemExit(0)

compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
assert compiler, "C++20 compiler required"
program = r"""
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstddef>
#include <cstdio>
#include <mutex>
namespace Eden::Performance {
std::atomic<bool> detailed_gpu_profile{false};
std::atomic<unsigned> idle_spin_iterations{0}, clock_reads{0}, counted{0};
long long NowNs() { return ++clock_reads; }
void CountIdle(std::size_t, long long, bool) { ++counted; }
}
class PhysicalCore {
public: void Idle();
private:
    std::mutex m_guard;
    std::condition_variable m_on_interrupt;
    bool m_is_interrupted{true};
    std::size_t m_core_index{0};
};
INJECT
int main() {
    PhysicalCore core;
    for (int i=0; i<10000; ++i) core.Idle();
    assert(Eden::Performance::clock_reads == 0 && Eden::Performance::counted == 0);
    Eden::Performance::detailed_gpu_profile.store(true);
    for (int i=0; i<5; ++i) core.Idle();
    assert(Eden::Performance::clock_reads == 10 && Eden::Performance::counted == 5);
    Eden::Performance::detailed_gpu_profile.store(false);
    for (int i=0; i<10000; ++i) core.Idle();
    assert(Eden::Performance::clock_reads == 10 && Eden::Performance::counted == 5);
    std::puts("PASS: extracted native Idle body skips quiet-mode clock probes and counters");
}
""".replace("INJECT", idle)
with tempfile.TemporaryDirectory(prefix="eden-quiet-cpuio-") as d:
    src, exe = Path(d)/"idle.cpp", Path(d)/"idle"
    src.write_text(program)
    subprocess.run([compiler, "-std=c++20", "-O2", "-pthread", "-Wall", "-Wextra",
                    "-Werror", str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=10)
print("PASS: R300 native CPU/IPC and maintained FS quiet clock guards; short-read still checked")
print("HOST-ONLY: native PS5 SDK and FC27/BOTW validation pending")
