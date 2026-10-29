#!/usr/bin/env python3
"""Execute the PS5 native texture-GC pressure decision extracted from production.

This proves the maximum probe count, bounded refresh, critical bypass, and
post-eviction reset. It does not measure driver latency or console FPS.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
start = header.index("void TextureCache<P>::RunGarbageCollector() {")
end = header.index("\ntemplate <class P>", start)
gc = header[start:end]
begin = gc.index("    constexpr unsigned kDirtyProbeReuse = 8;")
end = gc.index("\n#endif", begin)
decision = gc[begin:end]
assert "dirty_probe_remaining = kDirtyProbeReuse;" in decision
assert "total_used_memory >= critical_memory" in decision
assert gc.count("dirty_probe_remaining = 0;") == 3  # initial, after eviction, critical pass
assert "must_download && !DirtyEvictionsForCleanup()" in gc
assert "must_download && !DirtyEvictions()" in gc  # desktop remains untouched
assert "Pinned native GC pressure-probe anchor changed" in generator
assert "F07 bound native dirty GC pressure checks after clean-image rewrite" in generator
assert "gc = gc.replace(old, new)" in generator

compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
if not compiler:
    raise SystemExit("Missing C++20 compiler")
cpp = r"""
#include <cassert>
#include <cstdint>
namespace Eden::Performance {
static unsigned calls = 0;
static bool keep_dirty = true;
bool KeepDirtyTextures() { ++calls; return keep_dirty; }
}
int main() {
    bool high_priority_mode = false;
    std::uint64_t total_used_memory = 90;
    const std::uint64_t critical_memory = 100;
""" + decision + r"""
    using Eden::Performance::calls;
    using Eden::Performance::keep_dirty;
    for (int i = 0; i < 64; ++i) assert(!DirtyEvictionsForCleanup());
    assert(calls == 0);
    high_priority_mode = true;
    keep_dirty = true;
    for (int i = 0; i < 32; ++i) assert(!DirtyEvictionsForCleanup());
    assert(calls == 4); // one kernel-backed probe per eight skipped candidates
    keep_dirty = false;
    assert(DirtyEvictionsForCleanup()); // next visit must refresh
    assert(calls == 5);
    for (int i = 0; i < 7; ++i) assert(DirtyEvictionsForCleanup());
    assert(calls == 5);
    // The production deletion path resets this budget after each eviction.
    dirty_probe_remaining = 0;
    keep_dirty = true;
    assert(!DirtyEvictionsForCleanup());
    assert(calls == 6);
    total_used_memory = critical_memory;
    for (int i = 0; i < 64; ++i) assert(DirtyEvictionsForCleanup());
    assert(calls == 6); // critical memory never trusts a cached keep decision
    total_used_memory = 90;
    dirty_probe_remaining = 0; // production critical-pass boundary
    keep_dirty = false;
    assert(DirtyEvictionsForCleanup());
    assert(calls == 7);
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="f07-gc-pressure-") as tmp:
    src = Path(tmp) / "pressure.cpp"
    src.write_text(cpp)
    for opt in ("-O0", "-O2"):
        exe = Path(tmp) / ("pressure" + opt[1:])
        subprocess.run([compiler, "-std=c++20", opt, "-fsanitize=undefined",
                        "-fno-sanitize-recover=all", str(src), "-o", str(exe)],
                       check=True, capture_output=True, text=True)
        subprocess.run([str(exe)], check=True, capture_output=True, text=True)
print("F07_GC_PRESSURE_PROBE_PASS")
