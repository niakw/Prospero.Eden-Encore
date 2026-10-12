#!/usr/bin/env python3
"""R377: source-extracted guest write telemetry batching with independent threads."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
text = (root / "headless/performance.h").read_text()
source = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
oracle = (root / "tools/prepare-vulkan-port.py").read_text()
begin = text.index("class BatchedGuestWriteTimer {")
end = text.index("// Opt-in API wall times:", begin)
timer = text[begin:end]
assert 'if (++batch.calls == 64) batch.Flush();' in timer
assert 'static thread_local Batch batch{};' in timer
assert '~Batch() { Flush(); }' in timer
assert 'if (!enabled) return;' in timer
assert 'if (enabled) start = Common::g_wall_clock.GetTimeNS();' in timer
assert "BatchedGuestWriteTimer guest_write_timer;" in source
assert "BatchedGuestWriteTimer guest_write_timer;" in oracle
assert "DiagnosticTimer guest_write_timer" not in source

code = r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <thread>
#include <cstdint>
namespace Common {
struct Clock {
    std::atomic<std::uint64_t> calls{};
    std::chrono::nanoseconds GetTimeNS() noexcept {
        calls.fetch_add(1,std::memory_order_relaxed);
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch());
    }
};
inline Clock g_wall_clock{};
}
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{false};
struct Totals {
    std::atomic<std::uint64_t> calls{}, nanoseconds{};
};
inline Totals guest_cpu_write{};
__REAL_TIMER__
}
int main() {
    using namespace Eden::Performance;
    for (int i=0;i<100;++i) BatchedGuestWriteTimer timer{};
    assert(guest_cpu_write.calls.load()==0);
    assert(guest_cpu_write.nanoseconds.load()==0);
    assert(Common::g_wall_clock.calls.load()==0);
    detailed_gpu_profile.store(true);
    // Block 1: no inter-core atomic RMW until all 64 samples completed.
    for (int i=0;i<63;++i) BatchedGuestWriteTimer timer{};
    assert(guest_cpu_write.calls.load()==0);
    assert(guest_cpu_write.nanoseconds.load()==0);
    for (int i=0;i<1;++i) BatchedGuestWriteTimer timer{};
    assert(guest_cpu_write.calls.load()==64);
    assert(guest_cpu_write.nanoseconds.load()>0);
    for (int i=0;i<63;++i) BatchedGuestWriteTimer timer{};
    assert(guest_cpu_write.calls.load()==64);
    for (int i=0;i<1;++i) BatchedGuestWriteTimer timer{};
    assert(guest_cpu_write.calls.load()==128);
    // Independently flush the final residue when each worker exits.
    std::thread a([] {
        for (int i=0;i<63;++i) BatchedGuestWriteTimer timer{};
    });
    std::thread b([] {
        for (int i=0;i<127;++i) BatchedGuestWriteTimer timer{};
    });
    a.join();b.join();
    // 128 original + 63 worker A + 127 worker B = 318.
    assert(guest_cpu_write.calls.load()==318);
    const auto clocks = Common::g_wall_clock.calls.load();
    assert(clocks==318*2);
    detailed_gpu_profile.store(false);
    for (int i=0;i<128;++i) BatchedGuestWriteTimer timer{};
    assert(Common::g_wall_clock.calls.load()==clocks);
    assert(guest_cpu_write.calls.load()==318);
}
""".replace("__REAL_TIMER__", timer)
env=os.environ.copy()
if sys.platform=="darwin" and not env.get("SDKROOT"):
    sdk=Path("/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk")
    if sdk.is_dir():env["SDKROOT"]=str(sdk)
with tempfile.TemporaryDirectory(prefix="eden-r377-batch-") as d:
    path=Path(d)/"batch.cpp";exe=Path(d)/"batch"
    path.write_text(code)
    subprocess.run(["c++","-std=c++20","-O1","-pthread","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined",str(path),"-o",str(exe)],
                   check=True,env=env,timeout=40)
    subprocess.run([str(exe)],check=True,env=env,timeout=15)
print("PASS R377 guest-write exact 64 batch, TLS worker exit, quiet zero-clock/counters")
