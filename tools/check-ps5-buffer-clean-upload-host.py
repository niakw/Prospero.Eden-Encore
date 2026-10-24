#!/usr/bin/env python3
"""F01: compile and execute the selected maintained upload path (O0/O2, UBSan).

The unchanged upstream dirty-range walk is checked alongside the new clean
shortcut. This proves CPU/GPU dirty-range semantics on host, NOT an FPS gain.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h").read_text()
patch = (root / "headless/backports/eden-ps5-buffer-clean-upload-fastpath.patch").read_text()
start = native.index("bool BufferCache<P>::SynchronizeBuffer(")
end = native.index("\ntemplate <class P>", start)
method = native[start:end]
guard = "if (!memory_tracker.IsRegionCpuModified(device_addr, size))"
assert guard in method and guard in patch
assert method.index(guard) < method.index("upload_copies.clear()")
assert "gpu_modified_ranges.ForEachInRange" in method
assert "memory_tracker.ForEachUploadRange" in method
assert "UploadMemory(buffer, total_size_bytes, largest_copy, copies_span);" in method
# This test extracts the selected native method. Testing a stand-in algorithm
# without compiling the actual maintained source would not prove selection.
prologue = r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <span>
#include <utility>
#include <vector>
using DAddr = std::uint64_t;
using u64 = std::uint64_t;
using u32 = std::uint32_t;
struct BufferCopy {u64 src_offset{}, dst_offset{}, size{};};
struct Buffer {DAddr cpu_addr_cached=0x1000;};
struct Tracker {
    bool dirty=false;
    int dirty_probes=0, upload_walks=0;
    bool IsRegionCpuModified(DAddr, u32) {++dirty_probes;return dirty;}
    template<class Fn> void ForEachUploadRange(DAddr addr,u32 size,Fn fn) {
        ++upload_walks;
        const bool needs_upload=dirty;
        dirty=false; // selected API consumes CPU-dirty bits
        if(needs_upload && size) fn(addr,size);
    }
};
struct GpuDirty {
    std::vector<std::pair<u64,u64>> ranges;
    template<class Fn> void ForEachInRange(u64 addr,u64 size,Fn fn) {
        for(const auto& [start,end] : ranges) {
            const u64 lo=std::max(start,addr),hi=std::min(end,addr+size);
            if(lo<hi) fn(lo,hi);
        }
    }
};
struct Dummy {};
template<class P> struct BufferCache {
    Tracker memory_tracker;
    GpuDirty gpu_modified_ranges;
    std::vector<BufferCopy> upload_copies;
    bool any_buffer_uploaded=false;
    int uploads=0;
    u64 bytes_uploaded=0, last_largest=0;
    bool SynchronizeBuffer(Buffer& buffer,DAddr device_addr,u32 size);
    void UploadMemory(Buffer&,u64 total,u64 largest,std::span<BufferCopy> copies) {
        assert(!copies.empty());
        ++uploads;
        bytes_uploaded+=total;
        last_largest=largest;
        u64 sum=0;
        for(const auto& copy:copies) sum+=copy.size;
        assert(sum==total);
    }
};
"""
epilogue = r"""
int main() {
    BufferCache<Dummy> cache{};
    Buffer buffer{};
    // Clean hot-draws must not walk, clear or allocate CPU-upload ranges.
    for(int i=0;i<1024;i++) assert(cache.SynchronizeBuffer(buffer,0x1000,256));
    assert(cache.memory_tracker.dirty_probes==1024);
    assert(cache.memory_tracker.upload_walks==0);
    assert(cache.uploads==0 && !cache.any_buffer_uploaded);
    // Dirty CPU data must still be uploaded and its dirty bits consumed.
    cache.memory_tracker.dirty=true;
    assert(!cache.SynchronizeBuffer(buffer,0x1000,256));
    assert(cache.memory_tracker.upload_walks==1);
    assert(cache.uploads==1 && cache.bytes_uploaded==256 && cache.last_largest==256);
    assert(!cache.memory_tracker.dirty && cache.any_buffer_uploaded);
    // With the CPU range clean again, the previous vector is not reused.
    assert(cache.SynchronizeBuffer(buffer,0x1000,256));
    assert(cache.uploads==1 && cache.memory_tracker.upload_walks==1);
    // Aliased GPU-dirty bytes are *excluded* from the CPU upload.
    cache.memory_tracker.dirty=true;
    cache.gpu_modified_ranges.ranges={{0x1040,0x1080}};
    assert(!cache.SynchronizeBuffer(buffer,0x1000,256));
    assert(cache.uploads==2 && cache.bytes_uploaded==448);
    assert(cache.upload_copies.size()==2);
    assert(cache.upload_copies[0].dst_offset==0 && cache.upload_copies[0].size==64);
    assert(cache.upload_copies[1].dst_offset==128 && cache.upload_copies[1].size==128);
    // All bytes GPU-owned: dirty CPU marks are still consumed, no upload.
    cache.memory_tracker.dirty=true;
    cache.gpu_modified_ranges.ranges={{0x1000,0x1100}};
    assert(cache.SynchronizeBuffer(buffer,0x1000,256));
    assert(cache.uploads==2 && cache.memory_tracker.upload_walks==3);
    assert(!cache.memory_tracker.dirty);
    // Zero-length requests never allocate or consume a retained dirty flag.
    cache.memory_tracker.dirty=true;
    assert(cache.SynchronizeBuffer(buffer,0x1000,0));
    assert(cache.memory_tracker.dirty);
}
"""
compilers = list(dict.fromkeys(filter(None, (
    shutil.which("clang++"), shutil.which("g++"), shutil.which("c++")))))
assert compilers, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f01-clean-upload-") as temp:
    cpp = Path(temp) / "upload.cpp"
    cpp.write_text(prologue + "\ntemplate<class P>\n" + method + "\n" + epilogue)
    for compiler in compilers:
        for opt in ("-O0", "-O2"):
            exe = Path(temp) / (Path(compiler).name + opt)
            built = subprocess.run(
                [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 str(cpp), "-o", str(exe)],
                capture_output=True, text=True, timeout=50)
            assert built.returncode == 0, (compiler, opt, built.stderr[-4000:])
            ran = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            assert ran.returncode == 0, (compiler, opt, ran.stderr[-4000:])
            print("ENCORE_F01_CLEAN_UPLOAD_PASS", Path(compiler).name, opt)
