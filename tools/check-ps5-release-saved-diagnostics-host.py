#!/usr/bin/env python3
"""Release-only saved log preference -> sampled GPU cache diagnostics O0/O2.

Compile the EXACT selected source's launch initialization with a host atomic
harness. Same PS5 release binary must reset per-title counters, opt into the
lightweight 1/16-draw phase samples only when Detailed Logging is selected,
and restore zero-cost quiet counters on the next session. This test does NOT
claim to identify a particular FC27 HUD stall or validate game performance.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
main = (root / "headless/main.cpp").read_text()
perf = (root / "headless/performance.h").read_text()
services = (root / "headless/prosperoeden/eden_services.cpp").read_text()
begin = "#if defined(PS5_NATIVE) && !defined(EDEN_DEV_PROFILE)\n        // A saved Detailed Logging preference"
assert main.count(begin) == 1
end = "\n#endif\n#ifdef EDEN_DEV_VULKAN"
block = main.split(begin, 1)[1].split(end, 1)[0]
body = block[block.index("        Eden::Performance::ResetCachePhases();"):]
assert body.count("Eden::Performance::ResetCachePhases();") == 1
assert "launch_preferences.detailed_logging, std::memory_order_relaxed" in body
assert "if (!detailed_gpu_profile.load(std::memory_order_relaxed)) return false;" in perf
assert "detailed_gpu_profile.store(value.detailed_logging" in services

cpp = r"""
#include <atomic>
#include <cassert>
#include <cstddef>
struct Prefs { bool detailed_logging{}; };
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{false};
inline unsigned resets{};
inline unsigned sampled_draws{};
void ResetCachePhases() {
    ++resets;
    sampled_draws = 0;
}
bool SampleDraw() {
    if (!detailed_gpu_profile.load(std::memory_order_relaxed)) return false;
    return (++sampled_draws & 15u) == 0u;
}
}
void StartGame(Prefs launch_preferences) {
""" + body + r"""
}
int main() {
    StartGame({false});
    assert(!Eden::Performance::detailed_gpu_profile.load());
    for (int i = 0; i < 32; ++i) assert(!Eden::Performance::SampleDraw());
    assert(Eden::Performance::sampled_draws == 0);
    StartGame({true});
    assert(Eden::Performance::detailed_gpu_profile.load());
    for (int i = 0; i < 15; ++i) assert(!Eden::Performance::SampleDraw());
    assert(Eden::Performance::SampleDraw());
    assert(Eden::Performance::sampled_draws == 16);
    // Another game title without detailed logs MUST not inherit last game's
    // profiling or counters; no duplicate launcher build is needed.
    StartGame({false});
    assert(!Eden::Performance::detailed_gpu_profile.load());
    assert(Eden::Performance::sampled_draws == 0);
    for (int i = 0; i < 32; ++i) assert(!Eden::Performance::SampleDraw());
    assert(Eden::Performance::resets == 3);
}
"""
with tempfile.TemporaryDirectory(prefix="encore-release-log-toggle-") as tmp:
    src = Path(tmp)/"toggle.cpp"
    src.write_text(cpp)
    for opt in ("-O0", "-O2"):
        output = Path(tmp)/("toggle"+opt[2:])
        subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",opt,
                        str(src),"-o",str(output)], check=True, timeout=30,
                       capture_output=True, text=True)
        subprocess.run([str(output)], check=True, timeout=10)
print("ENCORE_RELEASE_SAVED_DIAGNOSTICS_HOST_PASS single_build=1 O0=1 O2=1 no_quiet_timers=1")
