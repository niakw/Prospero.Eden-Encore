#!/usr/bin/env python3
"""F07: compile source-selected writable multi-range rejection under O0/O2.

The GPU source must avoid expensive gathered fallback allocation when sparse
binding is unavailable. Read-only gathers, sparse writes and desktop keep
the previous result and FIFO commands. No real PS5 GPU/FPS proof.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "vendor/encore-active/eden-vulkan/vk_buffer_cache_cost.cpp").read_text()
generator = (ROOT / "tools/prepare-vulkan-port.py").read_text()
fast = (ROOT / ".github/workflows/encore-core-fast-gate.yml").read_text()
pre = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()
call = "python3 -B tools/check-ps5-f07-multirange-write-preflight-host.py"
assert call in fast and call in pre
assert "F07 reject unsupported native writable multirange before fallback allocation" in generator
begin = "bool BufferCacheRuntime::BindMultiRangeStorageBuffer(u64 key, bool is_written) {"
end = "\nvoid BufferCacheRuntime::BindIndexBuffer("
assert source.count(begin)==1
body = source[source.index(begin):source.index(end,source.index(begin))]
assert "if (is_written && !multi_range_buffers.use_sparse)" in body
assert body.index("if (is_written && !multi_range_buffers.use_sparse)") < body.index("multi_range_buffers.Get(")
assert body.count("if (is_written && !ref.sparse)") == 1
cpp = r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>
using u64 = std::uint64_t;
using VkDeviceSize = std::uint64_t;
using VkBuffer = std::uint64_t;
constexpr VkBuffer VK_NULL_HANDLE=0;
namespace Eden::DevVulkan { inline bool disable_multi_range=false; }
struct Device {};
struct Scheduler {};
struct Allocator {};
struct MultiRangeSource { VkBuffer handle{2}; VkDeviceSize offset{}; VkDeviceSize size{8}; };
struct MultiRangeRef {
    VkBuffer handle{5};
    VkDeviceSize address{11},size{8};
    bool sparse{},needs_gather{true};
};
namespace VideoCommon {
struct BufferCopy { u64 src_offset{},dst_offset{}; std::size_t size{}; };
}
struct MultiRangeBufferCache {
    bool use_sparse{};
    unsigned gets{},marked{};
    MultiRangeRef Get(Device&,Scheduler&,Allocator&,u64,
                      const std::vector<MultiRangeSource>&,VkDeviceSize total) {
        ++gets;
        return MultiRangeRef{5,11,total,use_sparse,!use_sparse};
    }
    void MarkGathered(u64) {++marked;}
};
struct Queue {
    unsigned adds{};
    void AddBuffer(VkBuffer, VkDeviceSize, VkDeviceSize, VkDeviceSize){++adds;}
};
struct BufferCacheRuntime {
    Device device{};
    Scheduler scheduler{};
    Allocator memory_allocator{};
    MultiRangeBufferCache multi_range_buffers{};
    std::vector<MultiRangeSource> multi_range_sources{{}};
    VkDeviceSize multi_range_total{8};
    Queue guest_descriptor_queue{};
    unsigned before{},after{},copies{};
    void PreCopyBarrier(){++before;}
    void PostCopyBarrier(){++after;}
    template<class T>
    void CopyBuffer(VkBuffer,VkBuffer,const T& regions,bool) {
        assert(regions.size()==1);
        ++copies;
    }
    bool BindMultiRangeStorageBuffer(u64,bool);
};
__SOURCE__
int main() {
    {
        BufferCacheRuntime c;
        assert(!c.BindMultiRangeStorageBuffer(1,true));
#ifdef PS5_NATIVE
        assert(c.multi_range_buffers.gets==0 && c.copies==0);
#else
        assert(c.multi_range_buffers.gets==1 && c.copies==0);
#endif
        assert(c.guest_descriptor_queue.adds==0);
    }
    {
        BufferCacheRuntime c;
        assert(c.BindMultiRangeStorageBuffer(1,false));
        assert(c.multi_range_buffers.gets==1 && c.copies==1);
        assert(c.before==1 && c.after==1);
        assert(c.multi_range_buffers.marked==1 && c.guest_descriptor_queue.adds==1);
    }
    {
        BufferCacheRuntime c;
        c.multi_range_buffers.use_sparse=true;
        assert(c.BindMultiRangeStorageBuffer(1,true));
        assert(c.multi_range_buffers.gets==1 && c.copies==0);
        assert(c.before==0 && c.after==0 && c.guest_descriptor_queue.adds==1);
    }
    {
        BufferCacheRuntime c;
        c.multi_range_sources.clear();
        assert(!c.BindMultiRangeStorageBuffer(1,true));
        assert(c.multi_range_buffers.gets==0);
    }
    {
        BufferCacheRuntime c;
        Eden::DevVulkan::disable_multi_range=true;
        assert(!c.BindMultiRangeStorageBuffer(1,true));
        assert(c.multi_range_buffers.gets==0);
        Eden::DevVulkan::disable_multi_range=false;
    }
}
""".replace("__SOURCE__",body)
compiler = shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-multirange-writes-") as d:
    src=Path(d)/"multi.cpp"
    src.write_text(cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            exe=Path(d)/(str(int(native))+opt)
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(["-DPS5_NATIVE=1"] if native else []),str(src),"-o",str(exe)]
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
            assert result.returncode==0,(native,opt,result.stderr[-5000:])
            result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            assert result.returncode==0,(native,opt,result.stderr[-5000:])
            print("F07_MULTIRANGE_WRITE_PREFLIGHT_PASS native="+str(int(native)),opt)
print("F07_NO_PS5_GPU_OR_FPS_PROOF")
