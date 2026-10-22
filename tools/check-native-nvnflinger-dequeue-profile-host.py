#!/usr/bin/env python3
"""Compile the selected native dequeue call with the DEV timer on and off."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
cmake = (ROOT / "headless/CMakeLists.txt").read_text()
profile = "EDEN_NVNF_DEQUEUE_PROFILE"
assert src.startswith('#ifdef ' + profile + '\n#include "performance.h"\n#endif\n')
assert cmake.count('list(APPEND core_sources "$' + '{EDEN_MAINTAINED_PROFILE_DEQUEUE}")') == 1
assert cmake.count("target_compile_definitions(core PRIVATE " + profile + "=1)") == 1
assert "buffer_queue_producer_standard.cpp" not in cmake
start = src.index("#ifdef " + profile + "\n        const auto dequeue_start")
end = src.index("        if (status != Status::NoError)", start)
fragment = src[start:end]
assert fragment.count("#ifdef " + profile) == 2
assert fragment.count("#endif") == 2
assert fragment.count("Status status = WaitForFreeSlotThenRelock(") == 1
assert fragment.count("::Eden::Performance::AddSince(") == 1
fixture = r"""
#include <atomic>
#include <cassert>
#include <mutex>
using s32 = int;
enum class Status { NoError, BadValue };
#ifdef EDEN_NVNF_DEQUEUE_PROFILE
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{true};
inline std::atomic<int> clock_calls{};
inline std::atomic<int> add_calls{};
constexpr int guest_dequeue_wait = 1;
long long NowNs() { ++clock_calls; return 100; }
void AddSince(int key, long long stamp) {
    assert(key == guest_dequeue_wait && stamp == 100);
    ++add_calls;
}
}
#endif
struct Probe {
    std::mutex mutex;
    int calls{};
    Status WaitForFreeSlotThenRelock(bool async, s32* found, Status* flags,
                                     std::unique_lock<std::mutex>& lock) {
        assert(lock.owns_lock() && !async && found && flags);
        ++calls;
        return Status::NoError;
    }
    Status Run() {
        bool async = false;
        s32 found = -1;
        Status return_flags = Status::NoError;
        std::unique_lock<std::mutex> lock(mutex);
""" + fragment + r"""
        return status;
    }
};
int main() {
    Probe p{};
    assert(p.Run() == Status::NoError && p.calls == 1);
#ifdef EDEN_NVNF_DEQUEUE_PROFILE
    assert(Eden::Performance::clock_calls == 1 && Eden::Performance::add_calls == 1);
    Eden::Performance::detailed_gpu_profile.store(false);
    assert(p.Run() == Status::NoError && p.calls == 2);
    assert(Eden::Performance::clock_calls == 1 && Eden::Performance::add_calls == 1);
#else
    assert(p.Run() == Status::NoError && p.calls == 2);
#endif
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-dequeue-profile-") as tmp:
    source = Path(tmp) / "selected.cpp"
    source.write_text(fixture)
    for profile_on in (False, True):
        for opt in ("-O0", "-O2"):
            binary = Path(tmp) / f"selected-{int(profile_on)}-{opt}"
            args = [compiler, "-std=c++20", opt, "-pthread", "-Wall", "-Wextra",
                    "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all"]
            if profile_on:
                args.append("-DEDEN_NVNF_DEQUEUE_PROFILE=1")
            subprocess.run([*args, str(source), "-o", str(binary)], check=True, timeout=45)
            subprocess.run([str(binary)], check=True, timeout=12)
            print("NATIVE_NVN_DEQUEUE_PROFILE_PASS", "dev" if profile_on else "release", opt)
