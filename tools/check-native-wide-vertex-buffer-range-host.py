#!/usr/bin/env python3
"""Native vertex-buffer address ranges must not wrap through 32-bit extent."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
native=(root/"vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
backport=(root/"vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h").read_text()
start="template <class P>\nvoid BufferCache<P>::UpdateVertexBuffer(u32 index) {"
end="\ntemplate <class P>"
def extract(s):
    assert s.count(start)==1
    i=s.index(start)
    return s[i:s.index(end,i+len(start))]
body=extract(native)
old=extract(backport)
assert "const u64 address_size" in body
assert "gpu_addr_end > gpu_addr_begin" in body
assert "static_cast<u64>(~u32{0})" in body
assert "if (size == 0)" in body
assert "const u32 address_size = static_cast<u32>(gpu_addr_end - gpu_addr_begin)" in old
assert "UpdateVertexBufferSlot(index, NULL_BINDING);" in body
fixture=r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <optional>
using u32=std::uint32_t;
using u64=std::uint64_t;
using GPUVAddr=u64;
using DAddr=u64;
using BufferId=u32;
constexpr u64 operator""_MiB(unsigned long long n) {return n*1024ull*1024ull;}
namespace Dirty { constexpr u32 VertexBuffer0=0; }
struct Binding {
    DAddr device_addr{};
    u32 size{};
    BufferId buffer_id{};
};
constexpr Binding NULL_BINDING{};
struct Stream {
    GPUVAddr address{};
    bool enable{true};
    GPUVAddr Address() const {return address;}
};
struct GPURegs {
    std::array<Stream,2> vertex_streams{};
    std::array<Stream,2> vertex_stream_limits{};
};
struct GPUState {
    GPURegs regs{};
    struct {std::array<bool,2> flags{true,true};} dirty{};
};
struct Channel {std::array<Binding,2> vertex_buffers{};};
struct Memory {
    bool mapped{true},inside{true};
    u64 max_bytes{2*1024*1024};
    u32 ranges{},lookups{};
    std::optional<DAddr> GpuToCpuAddress(GPUVAddr addr) {
        ++lookups; if(!mapped)return std::nullopt;return DAddr{0x10000}+addr;
    }
    bool IsWithinGPUAddressRange(GPUVAddr) {return inside;}
    u64 MaxContinuousRange(GPUVAddr,u32 size) {
        ++ranges;
        return (std::min)(static_cast<u64>(size),max_bytes);
    }
};
template<class P>struct BufferCache {
    GPUState* maxwell3d;
    Memory* gpu_memory;
    Channel* channel_state;
    u32 finds{},updates{};
    Binding last{};
    BufferId FindBuffer(DAddr,u32 bytes,bool) {
        assert(bytes!=0);
        ++finds;return 17;
    }
    void UpdateVertexBufferSlot(u32,Binding b) {
        ++updates;last=b;
    }
    void UpdateVertexBuffer(u32 index);
};
""" + body + r"""
int main() {
    GPUState regs{};
    Channel channel{};
    Memory mem{};
    BufferCache<void> cache{&regs,&mem,&channel};
    auto set=[&](u64 first,u64 length) {
        regs.regs.vertex_streams[0].address=first;
        regs.regs.vertex_stream_limits[0].address=first+length-1;
    };
    set(0x2000,4096);
    cache.UpdateVertexBuffer(0);
    assert(channel.vertex_buffers[0].size==4096 && cache.finds==1);
    assert(channel.vertex_buffers[0].device_addr==0x12000);
    assert(mem.ranges==0);
    // Old u32 cast returned zero, dropping a valid (clipped) >=4GiB draw.
    set(0x100000000ull,0x100000000ull);
    cache.UpdateVertexBuffer(0);
    assert(channel.vertex_buffers[0].size==2*1024*1024);
    assert(cache.finds==2 && mem.ranges==1);
    // Old code returned 1 byte rather than a valid multi-megabyte range.
    set(0x200000000ull,0x100000001ull);
    cache.UpdateVertexBuffer(0);
    assert(channel.vertex_buffers[0].size==2*1024*1024);
    assert(cache.finds==3 && mem.ranges==2);
    // Inverted end never produces a wrapped unsigned range.
    regs.regs.vertex_streams[0].address=0x4000;
    regs.regs.vertex_stream_limits[0].address=0x3fff-1;
    cache.UpdateVertexBuffer(0);
    assert(channel.vertex_buffers[0].size==0 && cache.finds==3);
    // Empty post-clamp continuous memory must retire a previous binding.
    set(0x2000,128*1024*1024);
    mem.max_bytes=0;
    cache.UpdateVertexBuffer(0);
    assert(channel.vertex_buffers[0].size==0 && cache.finds==3);
    assert(cache.last.size==0);
    // Unmapped GPU addresses keep the original null slot semantics.
    mem.mapped=false;
    set(0x2000,4096);
    cache.UpdateVertexBuffer(0);
    assert(channel.vertex_buffers[0].size==0 && cache.finds==3);
    // Non-dirty ranges must not alter the state.
    regs.dirty.flags[0]=false;
    cache.UpdateVertexBuffer(0);
    assert(cache.finds==3);
}
"""
compiler=shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-wide-vertex-range-") as d:
    src=Path(d)/"test.cpp";src.write_text(fixture)
    for opt in ("-O0","-O2"):
        exe=Path(d)/("vertex"+opt)
        subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-fsanitize=undefined",str(src),"-o",str(exe)],
                        check=True,timeout=45)
        subprocess.run([str(exe)],check=True,timeout=20)
        print("NATIVE_WIDE_VERTEX_RANGE_PASS",opt)
