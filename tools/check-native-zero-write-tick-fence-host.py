#!/usr/bin/env python3
"""Source-selected native BufferCache zero-tick GPU fence probe regression."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/"vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
backport = (root/"vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h").read_text()
start="template <class P>\nvoid BufferCache<P>::SynchronizeBufferWrites("
assert source.count(start) == backport.count(start) == 1
def method(s):
    i=s.index(start)
    return s[i:s.index("\ntemplate <class P>",i+len(start))]
body=method(source)
previous=method(backport)
assert "buffer_tick != 0 && !runtime.IsFree(buffer_tick)" in body
assert "buffer_tick != 0" not in previous
assert body.replace(
    "        // New and never-GPU-written buffers have a zero fence tick.\n"
    "        // Scheduler::Wait(0) cannot wait; skip its IsFree semaphore probe.\n",
    "").replace("buffer_tick != 0 && !runtime.IsFree(buffer_tick)",
                "!runtime.IsFree(buffer_tick)") == previous
program=r"""
#include <cassert>
#include <cstdint>
using u64=std::uint64_t;
struct MockBuffer {
    u64 tick{};
    u64 getWriteTick() const noexcept {return tick;}
};
struct MockRuntime {
    unsigned probes{},waits{};
    u64 last_probe{},last_wait{};
    bool free=true;
    bool IsFree(u64 tick) {
        ++probes;last_probe=tick;return free;
    }
    void Wait(u64 tick) {
        ++waits;last_wait=tick;
        assert(tick != 0);
    }
};
template<class P>struct BufferCache {
    using Buffer=MockBuffer;
    static constexpr bool IS_OPENGL=false;
    MockRuntime runtime;
    void SynchronizeBufferWrites(Buffer&);
};
""" + body + r"""
int main() {
    BufferCache<void> cache;
    MockBuffer buffer{};
    cache.runtime.free=false;
    // Tick 0 means no pending GPU fence; no semaphore probe or wait.
    cache.SynchronizeBufferWrites(buffer);
    assert(cache.runtime.probes==0 && cache.runtime.waits==0);
    // A nonzero completed fence retains its ordinary IsFree call.
    buffer.tick=11;
    cache.runtime.free=true;
    cache.SynchronizeBufferWrites(buffer);
    assert(cache.runtime.probes==1 && cache.runtime.waits==0);
    assert(cache.runtime.last_probe==11);
    // A nonzero unfinished fence retains the same waiting semantics.
    buffer.tick=12;
    cache.runtime.free=false;
    cache.SynchronizeBufferWrites(buffer);
    assert(cache.runtime.probes==2 && cache.runtime.waits==1);
    assert(cache.runtime.last_probe==12 && cache.runtime.last_wait==12);
    // Never-written buffers stay fast even after unrelated waits.
    buffer.tick=0;
    cache.SynchronizeBufferWrites(buffer);
    assert(cache.runtime.probes==2 && cache.runtime.waits==1);
}
"""
compiler=shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-zero-fence-tick-") as tmp:
    source_file=Path(tmp)/"fence.cpp"
    source_file.write_text(program)
    for opt in ("-O0","-O2"):
        executable=Path(tmp)/("fence"+opt)
        subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-fsanitize=undefined",str(source_file),"-o",str(executable)],
                       check=True,timeout=40)
        subprocess.run([str(executable)],check=True,timeout=20)
        print("NATIVE_ZERO_TICK_GPU_FENCE_PASS",opt)
