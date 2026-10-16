#!/usr/bin/env python3
"""Deterministic atomic dirty-mask race: pinned negative vs maintained native header.

The test pauses a page switch *after* the old mask was copied to the replay
vector. Another producer atomically adds a bit to that old page. The pinned
header then loses that bit, whereas the native replacement captures the
actual displaced atomic value. A host result does not qualify console timing.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/core/gpu_dirty_memory_manager.h").read_text()
maintained = (root / "vendor/encore-active/eden-core/overrides/core/gpu_dirty_memory_manager.h").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()

old = "                    back_buffer.emplace_back(tmp);\\n                    current.exchange(t, std::memory_order_relaxed);"
fixed = """                    // A concurrent same-region CAS can extend the mask AFTER
                    // our initial load. Exchange first, then save the actual
                    // displaced value in the already reserved vector slot.
                    // This keeps the normal same-region CAS path lock-free.
                    back_buffer.emplace_back(tmp);
                    back_buffer.back() = current.exchange(t, std::memory_order_acq_rel);"""
assert pinned.count(old.replace("\\n", "\n")) == 1
assert maintained == pinned.replace(old.replace("\\n", "\n"), fixed)
assert 'set(EDEN_NATIVE_DIRTY_HEADER_ROOT' in cmake
assert 'target_include_directories(core BEFORE PUBLIC "${EDEN_NATIVE_DIRTY_HEADER_ROOT}")' in cmake
assert 'if(PS5_NATIVE)' in cmake.split('set(EDEN_NATIVE_DIRTY_HEADER_ROOT', 1)[0]
assert "python3 -B tools/check-native-gpu-dirty-transition-host.py" in workflow
assert maintained.count("back_buffer.back() = current.exchange(t, std::memory_order_acq_rel);") == 1

source = r"""
#include "core/gpu_dirty_memory_manager.h"
#include <atomic>
#include <cassert>
#include <cstdint>
#include <functional>
#include <set>
#include <thread>

static std::atomic<int> phase{0};
void Core::PinnedRaceGate() {
    int expected = 0;
    assert(phase.compare_exchange_strong(expected, 1));
    while (phase.load(std::memory_order_acquire) != 2) {
        std::this_thread::yield();
    }
}
int main() {
    constexpr PAddr first = 0x2000, next = 0x2800;
    Core::GPUDirtyMemoryManager dirty;
    dirty.Collect(first, 64);
    std::thread transition([&] { dirty.Collect(next, 64); });
    while (phase.load(std::memory_order_acquire) != 1) {
        std::this_thread::yield();
    }
    // This fast-path CAS updates the first page while the other thread
    // still holds the slow-page-transition mutex. Old code loses this bit.
    dirty.Collect(first + 64, 64);
    phase.store(2, std::memory_order_release);
    transition.join();

    std::set<PAddr> observed;
    std::function<void(PAddr, std::size_t)> receive =
        [&](PAddr a, std::size_t n) {
            assert(a % 64 == 0 && n % 64 == 0);
            for (PAddr p = a; p < a + n; p += 64) observed.insert(p);
        };
    dirty.Gather(receive);
    assert(observed.count(first) == 1);
    assert(observed.count(next) == 1);
#ifdef EXPECT_FIXED
    assert(observed.count(first + 64) == 1);
    assert(observed.size() == 3);
#else
    assert(observed.count(first + 64) == 0);
    assert(observed.size() == 2);
#endif
}
"""
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang C++20 required"
with tempfile.TemporaryDirectory(prefix="encore-dirty-race-") as tmp:
    stage = Path(tmp)
    unit = stage / "race.cpp"
    unit.write_text(source)
    include_stub = stage / "core"
    include_stub.mkdir()
    (include_stub / "device_memory_manager.h").write_text(
        "#pragma once\n#include <cstddef>\n#include <cstdint>\n"
        "using PAddr = std::uint64_t;\nusing u32 = std::uint32_t;\n"
        "using u64 = std::uint64_t;\n"
        "namespace Core { inline constexpr std::size_t DEVICE_PAGEBITS = 12; }\n"
    )
    for label, header, is_fixed in (
        ("pinned_original", pinned, False),
        ("maintained_native", maintained, True),
    ):
        instrumented = header.replace(
            "namespace Core {", "namespace Core {\nvoid PinnedRaceGate();", 1
        )
        mark = (
            "                    back_buffer.emplace_back(tmp);\n"
            if not is_fixed else
            "                    back_buffer.back() = current.exchange(t, std::memory_order_acq_rel);"
        )
        if is_fixed:
            assert instrumented.count(mark) == 1
            instrumented = instrumented.replace(
                mark, "                    PinnedRaceGate();\n" + mark
            )
        else:
            assert instrumented.count(mark) == 1
            instrumented = instrumented.replace(
                mark, mark + "                    PinnedRaceGate();\n"
            )
        # The original gate must happen before its exchange. The fixed
        # gate must happen after emplace and before exchange.
        (include_stub / "gpu_dirty_memory_manager.h").write_text(instrumented)
        binary = stage / label
        command = [clang, "-std=c++20", "-O1", "-g", "-pthread",
                   "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                   "-fno-sanitize-recover=all", "-I", str(stage),
                   str(unit), "-o", str(binary)]
        if is_fixed:
            command.insert(1, "-DEXPECT_FIXED")
        subprocess.run(command, check=True, timeout=45)
        subprocess.run([str(binary)], check=True, timeout=45)
print("NATIVE_GPU_DIRTY_TRANSITION_HOST_PASS stale_mask_loss_original=1 exchange_displaced_mask_fixed=1 deterministic_threads=2 sanitizer=address_undefined native_only=1")
