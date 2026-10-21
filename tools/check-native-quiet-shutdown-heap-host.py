#!/usr/bin/env python3
"""Compile actual native shutdown heap section: always drain, skip quiet scans."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
source=(root/"headless/main.cpp").read_text()
start="        const std::size_t tcache_drained = eden_heap_release_current_tcache();"
end="\n#endif\n        if (devices && pad)"
assert source.count(start)==1 and source.count(end)==1
section=start+source.split(start,1)[1].split(end,1)[0]
guard="if (Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed))"
assert section.count(guard)==1
assert section.index("eden_heap_release_current_tcache();")<section.index(guard)
assert section.index(guard)<section.index("eden_heap_report_roots(\"core_destroyed\");")
assert section.index(guard)<section.index('ps5_opengl_heap_snapshot("post_cache_drain", 0);')
cc=shutil.which("clang++-18") or shutil.which("clang++")
assert cc, "Clang required for sanitizer proof"
fixture=r"""
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdio>
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{false};
}
inline unsigned drains=0,reports=0,snapshots=0;
std::size_t eden_heap_release_current_tcache() {++drains;return 32;}
void eden_heap_report_roots(const char*){++reports;}
void ps5_opengl_heap_snapshot(const char*, unsigned){++snapshots;}
void after_title() {
__BLOCK__
}
int main() {
 after_title();
 assert(drains==1 && reports==0 && snapshots==0);
 Eden::Performance::detailed_gpu_profile.store(true);
 after_title();
 assert(drains==2 && reports==1 && snapshots==1);
 Eden::Performance::detailed_gpu_profile.store(false);
 after_title();
 assert(drains==3 && reports==1 && snapshots==1);
}
""".replace("__BLOCK__",section)
with tempfile.TemporaryDirectory(prefix="eden-shutdown-heap-") as temp:
    d=Path(temp)
    s=d/"shutdown.cpp";exe=d/"shutdown"
    s.write_text(fixture)
    subprocess.run([cc,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(s),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30,capture_output=True)
print("NATIVE_QUIET_SHUTDOWN_HEAP_PASS tcache_always_drained=1 quiet_snapshots_off=1 detailed_on=1")
