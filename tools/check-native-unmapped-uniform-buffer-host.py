#!/usr/bin/env python3
"""Source-selected unmapped shader cbuf must not dereference empty optional."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
active=(root/"vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
backport=(root/"vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h").read_text()
start="template <class P>\nvoid BufferCache<P>::BindGraphicsUniformBuffer("
end="template <class P>\nvoid BufferCache<P>::UpdateGraphicsBuffers("
def source_method(text):
    assert text.count(start)==text.count(end)==1
    return text[text.index(start):text.index(end)]
impl=source_method(active)
original=source_method(backport)
assert "if (!device_addr)" in impl
assert "channel_state->uniform_buffers[stage][index] = NULL_BINDING;" in impl
assert "if (!device_addr)" not in original
assert "device_addr = *device_addr" in impl
# The fallback is the SAME sentinel as DisableGraphicsUniformBuffer.
assert "channel_state->uniform_buffers[stage][index] = NULL_BINDING;" in impl
assert impl.index("if (!device_addr)") < impl.index(".device_addr = *device_addr")
program=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <optional>
using u32=std::uint32_t;
using DAddr=std::uint64_t;
using GPUVAddr=std::uint64_t;
using BufferId=u32;
struct Binding {
    DAddr device_addr{};
    u32 size{};
    BufferId buffer_id{};
};
inline constexpr Binding NULL_BINDING{.device_addr=0,.size=0,.buffer_id=0};
struct MockMemory {
    unsigned lookups{};
    bool mapped=true;
    std::optional<DAddr> GpuToCpuAddress(GPUVAddr addr) {
        ++lookups;
        if (!mapped) return std::nullopt;
        return DAddr{0x10000}+addr;
    }
};
struct State {
    std::array<std::array<Binding,4>,2> uniform_buffers{};
};
template<class P>
struct BufferCache {
    MockMemory* gpu_memory;
    State* channel_state;
    void BindGraphicsUniformBuffer(size_t,u32,GPUVAddr,u32);
    void DisableGraphicsUniformBuffer(size_t,u32);
};
""" + impl + r"""
int main() {
    MockMemory mem;
    State state;
    BufferCache<void> cache{&mem,&state};
    cache.BindGraphicsUniformBuffer(1,2,0x1200,512);
    const auto& live=state.uniform_buffers[1][2];
    assert(live.device_addr==0x11200 && live.size==512 && live.buffer_id==0);
    // A valid prior slot must not survive a now-unmapped GPU cbuf.
    state.uniform_buffers[1][2].buffer_id=17;
    mem.mapped=false;
    cache.BindGraphicsUniformBuffer(1,2,0x1200,512);
    const auto& unmapped=state.uniform_buffers[1][2];
    assert(unmapped.device_addr==0 && unmapped.size==0 && unmapped.buffer_id==0);
    // A later remap publishes new mapping normally.
    mem.mapped=true;
    cache.BindGraphicsUniformBuffer(1,2,0x1300,128);
    const auto& remapped=state.uniform_buffers[1][2];
    assert(remapped.device_addr==0x11300 && remapped.size==128 && remapped.buffer_id==0);
    assert(mem.lookups==3);
    cache.DisableGraphicsUniformBuffer(1,2);
    assert(state.uniform_buffers[1][2].size==0);
}
"""
# BindGraphicsUniformBuffer AND DisableGraphicsUniformBuffer bodies are present
# in the selected contiguous method range, rather than using mock behavior.
assert "void BufferCache<P>::DisableGraphicsUniformBuffer(" in impl
compiler=shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-cbuf-unmapped-") as tmp:
    f=Path(tmp)/"uniform.cpp"
    f.write_text(program)
    for opt in ("-O0","-O2"):
        exe=Path(tmp)/("uniform"+opt)
        subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        str(f),"-o",str(exe)],check=True,timeout=45)
        subprocess.run([str(exe)],check=True,timeout=20)
        print("NATIVE_UNMAPPED_UNIFORM_BUFFER_HOST_PASS",opt)
