#!/usr/bin/env python3
"""Actual maintained GPU report prefix: heartbeat survives quiet snapshots OFF."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"headless/performance.cpp").read_text()
start="void ReportGpuThread(unsigned frame) {"
end="    // Heap growth and arena use over the run (allocation failures abort the title)."
assert source.count(start)==1 and source.count(end)==1
prefix=source[source.index(start):source.index(end)]
assert "latest_gpu_report_frame.store(frame, std::memory_order_relaxed);" in prefix
assert "latest_gpu_report_ns.store(" in prefix
guard="if (!detailed_gpu_profile.load(std::memory_order_relaxed)) return;"
assert prefix.count(guard)==1
assert prefix.index("latest_gpu_report_ns.store(")<prefix.index(guard)
assert "ps5_opengl_heap_snapshot(\"vulkan_report\", frame);" in source
assert source.index(guard)<source.index("ps5_opengl_heap_snapshot(\"vulkan_report\", frame);")
cc=shutil.which("clang++-18") or shutil.which("clang++")
assert cc
fixture=r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <ctime>
#include "frame_metrics.h"
namespace Common {
struct Clock {
 std::chrono::nanoseconds GetTimeNS() const{return std::chrono::nanoseconds{12345678};}
};
inline Clock g_wall_clock{};
}
inline std::atomic<bool> detailed_gpu_profile{false};
inline std::atomic<unsigned> latest_gpu_report_frame{0};
inline std::atomic<unsigned long long> latest_gpu_report_ns{0};
inline int additional_clocks=0;
long long ClockNs(clockid_t){++additional_clocks;return 42;}
__REPORT_PREFIX__
}
int main(){
 ReportGpuThread(17);
 assert(latest_gpu_report_frame.load()==17);
 assert(latest_gpu_report_ns.load()==12345678);
 assert(additional_clocks==0);
 detailed_gpu_profile.store(true);
 ReportGpuThread(19);
 assert(latest_gpu_report_frame.load()==19);
 assert(latest_gpu_report_ns.load()==12345678);
 assert(additional_clocks==2);
 detailed_gpu_profile.store(false);
 ReportGpuThread(21);
 assert(latest_gpu_report_frame.load()==21);
 assert(additional_clocks==2);
}
""".replace("__REPORT_PREFIX__",prefix)
with tempfile.TemporaryDirectory(prefix="eden-quiet-report-") as tmp:
    d=Path(tmp);file=d/"report.cpp";exe=d/"report"
    file.write_text(fixture)
    subprocess.run([cc,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    "-I",str(root/"headless"),str(file),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=90)
print("NATIVE_QUIET_GPU_REPORT_HOST_PASS heartbeat=1 quiet_full_report=OFF dev_full_report=ON")
