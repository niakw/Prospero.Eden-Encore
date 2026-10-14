#!/usr/bin/env python3
"""R393: test the EXACT production guest IPC attribution under ASan/UBSan.

No Sony SDK, no PS5 build. Cross-check generation and detailed-only gating.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "headless/performance.h").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
report = (root / "headless/performance.cpp").read_text()
first = header.index("inline constexpr unsigned guest_ipc_thread_slots")
last = header.index("void RecordHle(", first)
impl = header[first:last]
assert "inline constexpr unsigned guest_ipc_thread_slots = 1024;" in impl
assert "inline constexpr unsigned guest_ipc_max_probes = 64;" in impl
assert "n < guest_ipc_max_probes" in impl
assert "std::array<GuestIpcThread, guest_ipc_thread_slots>" in impl
assert "std::memory_order_relaxed" in impl
assert "std::printf(" not in impl and "NowNs()" not in impl
assert "GetThreadName" not in impl and "mutex" not in impl.lower()
anchor = cmake.index('const auto ipc_tid = ipc_profile ? GetCurrentThread(kernel).GetThreadId() : 0;')
assert anchor < cmake.index("session->SendSyncRequest(kernel, message, buffer_size);", anchor)
assert "if (ipc_profile) ::Eden::Performance::FinishGuestIpc(" in cmake
assert "BeginGuestIpc(ipc_tid, ipc_start)" in cmake
assert "EDEN_DEV_IPC_THREAD tid=%llu calls=%llu ns=%llu max_ns=%llu" in report
assert "EDEN_DEV_IPC_ACTIVE tid=%llu age_ms=%.3f" in report
assert "std::array<ActiveIpcRow, 8>" in report
assert "EDEN_DEV_IPCHIST lt50us=%llu lt500us=%llu lt5ms=%llu" in report
before = report.rfind("#ifdef EDEN_DEV_PROFILE", 0, report.index("EDEN_DEV_IPC_THREAD"))
after = report.find("#endif", report.index("EDEN_DEV_IPC_THREAD"))
assert before >= 0 and after > before
assert "std::array<IpcRow, 12>" in report
# Reporting must obey the same detailed-only switch as the SVC profiler.
# With detailed logging disabled, no extra 5-second thread table or histogram.
ipc_section = report[before:after]
assert "if (detailed_gpu_profile.load(std::memory_order_relaxed)) {" in ipc_section
assert ipc_section.index("if (detailed_gpu_profile.load(std::memory_order_relaxed)) {") < ipc_section.index("EDEN_DEV_IPC_THREAD")
assert ipc_section.rstrip().endswith("}")


cpp = r"""
#include <array>
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <thread>
#include <vector>
namespace Eden::Performance {
struct Totals {
    std::atomic<unsigned long long> calls{}, nanoseconds{}, requested_bytes{};
};
inline Totals guest_ipc_wait{};
__PRODUCTION__
}
int main() {
    using namespace Eden::Performance;
    constexpr unsigned workers = 8, per_worker = 500;
    std::vector<std::thread> pool;
    for (unsigned i = 0; i < workers; ++i)
        pool.emplace_back([i] {
            const auto tid = 1ull + i * guest_ipc_thread_slots;  // force collision/probing
            for (unsigned n = 0; n < per_worker; ++n) {
                RecordGuestIpc(tid, n % 4 == 0 ? 1'000 : n % 4 == 1 ? 80'000 :
                                       n % 4 == 2 ? 2'000'000 : 9'000'000);
            }
        });
    for (auto& t : pool) t.join();
    assert(guest_ipc_wait.calls.load() == workers * per_worker);
    unsigned found = 0;
    for (const auto& t : guest_ipc_threads) {
        if (!t.calls.load()) continue;
        assert(t.calls.load() == per_worker);
        assert(t.max_ns.load() == 9'000'000);
        ++found;
    }
    assert(found == workers);
    for (const auto& bin : guest_ipc_hist)
        assert(bin.load() == workers * (per_worker / 4));
    assert(guest_ipc_overflow_calls.load() == 0);
    // Zero/unknown ID, negative elapsed and full-table overflow must be safe.
    RecordGuestIpc(0, -3);
    assert(guest_ipc_overflow_calls.load() == 1);
    // Fill every remaining independent slot, then enforce a bounded overflow.
    // The original 8 collision TIDs all hash to slot 1 and occupy slots 1..8.
    for (unsigned slot = 0; slot < guest_ipc_thread_slots; ++slot) {
        if (slot >= 1 && slot <= workers) continue;
        RecordGuestIpc(static_cast<unsigned long long>(slot) +
                       2ull * guest_ipc_thread_slots, 150);
    }
    unsigned occupied = 0;
    for (const auto& t : guest_ipc_threads) if (t.tid.load()) ++occupied;
    assert(occupied == guest_ipc_thread_slots);
    RecordGuestIpc(900000, 30'000'000);
    assert(guest_ipc_overflow_calls.load() == 2);
    // An active IPC becomes visible BEFORE it returns. A nested completion
    // must not erase the original (still pending) start timestamp.
    auto* active = BeginGuestIpc(1, 1'000'000);
    assert(active && active->active_since_ns.load() == 1'000'000);
    auto* nested = BeginGuestIpc(1, 2'000'000);
    assert(nested == active && active->active_since_ns.load() == 1'000'000);
    FinishGuestIpc(nested, 1, 2'000'000, 1'000);
    assert(active->active_since_ns.load() == 1'000'000);
    FinishGuestIpc(active, 1, 1'000'000, 5'000'000);
    assert(active->active_since_ns.load() == 0);
    assert(guest_ipc_wait.calls.load() ==
           workers * per_worker + (guest_ipc_thread_slots - workers) + 4);
}
""".replace("__PRODUCTION__", impl)

compiler = next((c for c in ("clang++-18", "clang++", "g++") if shutil.which(c)), None)
if not compiler:
    raise SystemExit("Host C++20 compiler unavailable")
env = os.environ.copy()
if sys.platform == "darwin" and not env.get("SDKROOT"):
    sdk = Path("/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk")
    if sdk.is_dir():
        env["SDKROOT"] = str(sdk)
with tempfile.TemporaryDirectory(prefix="eden-r393-guest-ipc-") as temp:
    src = Path(temp) / "ipc.cpp"
    exe = Path(temp) / "ipc"
    src.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-pthread",
                    "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", str(src), "-o", str(exe)],
                   check=True, env=env, timeout=90)
    subprocess.run([str(exe)], check=True, env=env, timeout=30)
print("PASS R395 bounded R393 IPC counters under ASan/UBSan, collisions, saturation, overflow and detailed-only SVC gate")
