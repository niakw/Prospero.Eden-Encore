#!/usr/bin/env python3
"""Source-selected native indexed draw bytes must preserve wide GPU extents."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
native=(root/"vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
backport=(root/"vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h").read_text()
start="template <class P>\nvoid BufferCache<P>::UpdateIndexBuffer() {"
end="\ntemplate <class P>"
def method(s):
    assert s.count(start)==1
    p=s.index(start)
    return s[p:s.index(end,p+len(start))]
body=method(native)
legacy=method(backport)
assert "const u64 index_count" in body
assert "gpu_addr_end > gpu_addr_begin" in body
assert "static_cast<u64>(~u32{0})" in body
assert "const u32 address_size = static_cast<u32>(gpu_addr_end - gpu_addr_begin)" in legacy
assert "const u32 draw_size = (index_buffer_ref.count + index_buffer_ref.first)" in legacy
cpp=r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <optional>
#include <vector>
#include <unordered_map>
using u32=std::uint32_t;
using u64=std::uint64_t;
using DAddr=u64;
using GPUVAddr=u64;
using BufferId=u32;
namespace Dirty { constexpr u32 IndexBuffer=0; }
namespace Common {
template<class T> T AlignUp(T n,T block){return n%block ? n + block - (n%block) : n;}
}
struct Binding {
    DAddr device_addr{};
    u32 size{};
    BufferId buffer_id{};
};
constexpr Binding NULL_BINDING{};
constexpr BufferId NULL_BUFFER_ID=0;
struct IndexReference {
    GPUVAddr start{0x1000},end{0x2000};
    u32 count{16},first{};
    GPUVAddr StartAddress() const{return start;}
    GPUVAddr EndAddress() const{return end;}
    u32 FormatSizeInBytes() const{return 4;}
};
struct DrawState {
    std::vector<u32> inline_index_draw_indexes{};
    IndexReference index_buffer{};
};
struct Graphics {
    struct {DrawState draw_state{};} draw_manager{};
    struct {std::array<bool,1> flags{true};} dirty{};
};
struct Memory {
    bool mapped{true};
    unsigned queries{};
    std::optional<DAddr> GpuToCpuAddress(GPUVAddr addr){
        ++queries;
        if (!mapped) return std::nullopt;
        return addr+0x10000;
    }
};
struct TestBuffer {size_t sz{};size_t SizeBytes() const{return sz;}};
template<class P>struct BufferCache {
    static constexpr u32 CACHING_PAGESIZE=4096;
    Graphics* maxwell3d;
    Memory* gpu_memory;
    struct {Binding index_buffer{};}* channel_state;
    BufferId inline_buffer_id=NULL_BUFFER_ID;
    std::unordered_map<BufferId,TestBuffer> slot_buffers{};
    BufferId next_id=20;
    unsigned finds{};
    BufferId CreateBuffer(DAddr,u32 size,bool){
        const BufferId id=++next_id;
        slot_buffers.insert_or_assign(id,TestBuffer{size});
        return id;
    }
    BufferId FindBuffer(DAddr,u32 size,bool){
        assert(size>0);++finds;return 17;
    }
    void UpdateIndexBuffer();
};
""" + body + r"""
int main(){
    Graphics g;
    Memory mem;
    struct {Binding index_buffer{};} c;
    // Nested anonymous channel type cannot be named externally. Construct
    // the actual BufferCache and point at its own compatible state below.
}
"""
# Remove inline main and use the actual nested type through a pointer.
cpp=cpp[:cpp.index("int main(){")] + r"""
int main(){
    Graphics g;
    Memory mem;
    BufferCache<void> cache{};
    decltype(cache.channel_state) state_ptr{};
    (void)state_ptr;
    // Pointer's target is anonymous, so create the target via decltype.
    std::remove_pointer_t<decltype(cache.channel_state)> state{};
    cache.maxwell3d=&g;cache.gpu_memory=&mem;cache.channel_state=&state;
    auto& ref=g.draw_manager.draw_state.index_buffer;
    ref.start=0x2000;ref.end=0x3000;ref.first=0;ref.count=16;
    cache.UpdateIndexBuffer();
    assert(state.index_buffer.size==64 && cache.finds==1);
    // Previously end-start narrowed to zero before comparing draw bytes.
    ref.start=0x100000000ull;ref.end=ref.start+0x100000000ull;
    cache.UpdateIndexBuffer();
    assert(state.index_buffer.size==64 && cache.finds==2);
    // Previously count+first overflowed to zero.
    ref.start=0x2000;ref.end=0x3000;
    ref.count=0xffffffffu;ref.first=1u;
    cache.UpdateIndexBuffer();
    assert(state.index_buffer.size==4096 && cache.finds==3);
    // Invalid reversed GPU range safely disables the stale index binding.
    ref.start=0x3000;ref.end=0x2fff;
    cache.UpdateIndexBuffer();
    assert(state.index_buffer.size==0 && cache.finds==3);
    // Translation failures remain null, no FindBuffer call.
    mem.mapped=false;ref.start=0x2000;ref.end=0x3000;
    cache.UpdateIndexBuffer();
    assert(state.index_buffer.size==0 && cache.finds==3);
    // Inline index data still takes its original non-GPU-address route.
    g.draw_manager.draw_state.inline_index_draw_indexes={0,1,2};
    cache.UpdateIndexBuffer();
    assert(state.index_buffer.size==3 && state.index_buffer.buffer_id!=0);
}
"""
cpp=cpp.replace("#include <unordered_map>","#include <unordered_map>\n#include <type_traits>")
compiler=shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-wide-index-") as d:
    path=Path(d)/"index.cpp";path.write_text(cpp)
    for opt in ("-O0","-O2"):
        exe=Path(d)/("index"+opt)
        subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-fsanitize=undefined",str(path),"-o",str(exe)],
                       check=True,timeout=45)
        subprocess.run([str(exe)],check=True,timeout=20)
        print("NATIVE_WIDE_INDEX_RANGE_PASS",opt)
