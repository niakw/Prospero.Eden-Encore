#!/usr/bin/env python3
"""F01 source-extracted pinned-vs-native uniform-mask rebind regression.

Measures stage-mask assignments on identical input sequences, not mutex
duration, GPU performance or FC27 frame timing.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/video_core/buffer_cache/buffer_cache.h").read_text()
native = (root / "vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
start = "template <class P>\nvoid BufferCache<P>::SetUniformBuffersState("
end = "\ntemplate <class P>\nvoid BufferCache<P>::SetComputeUniformBufferState("
def method(src):
    assert src.count(start) == src.count(end) == 1
    return start + src.split(start, 1)[1].split(end, 1)[0]
old, new = method(pinned), method(native)
assert old != new
assert old.count("    channel_state->enabled_uniform_buffer_masks = mask;") == 1
assert new.count("        channel_state->enabled_uniform_buffer_masks = mask;") == 1
assert "    channel_state->uniform_buffer_sizes = sizes;" in new
for workflow in ("encore-core-fast-gate.yml", "encore-core-preflight.yml"):
    assert "python3 -B tools/check-native-uniform-mask-rebind-host.py" in (
        root / ".github/workflows" / workflow).read_text()
cpp = r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
using u32 = std::uint32_t;
constexpr std::size_t NUM_STAGES = 5;
using Mask = std::array<u32, NUM_STAGES>;
using UniformBufferSizes = Mask;
struct TrackingMask {
    Mask value{};
    unsigned stores{};
    bool operator!=(const Mask& other) const { return value != other; }
    TrackingMask& operator=(const Mask& other) { value=other; ++stores; return *this; }
};
struct Channel {
    TrackingMask enabled_uniform_buffer_masks;
    Mask fast_bound_uniform_buffers{};
    Mask dirty_uniform_buffers{};
    Mask uniform_buffer_binding_sizes{};
    const UniformBufferSizes* uniform_buffer_sizes{};
};
template<bool Enabled> struct Policy { static constexpr bool persistent=Enabled; };
template<class P> struct BufferCache {
    static constexpr bool HAS_PERSISTENT_UNIFORM_BUFFER_BINDINGS=P::persistent;
    Channel channel{};
    Channel* channel_state=&channel;
    void SetUniformBuffersState(const Mask&, const UniformBufferSizes*);
};
__SOURCE__
template<bool persistent>
void replay() {
    BufferCache<Policy<persistent>> owner{};
    Channel& c=owner.channel;
    Mask empty{}, a{1,0,1,0,0}, b{0,1,1,0,0};
    UniformBufferSizes sizes1{4,8,16,32,64}, sizes2{5,9,17,33,65};
    c.fast_bound_uniform_buffers.fill(12);
    owner.SetUniformBuffersState(empty,&sizes1);
    assert(c.fast_bound_uniform_buffers[0]==12);
    assert(c.uniform_buffer_sizes==&sizes1);
    owner.SetUniformBuffersState(a,&sizes1);
    assert(c.fast_bound_uniform_buffers[0]==0);
    assert(c.enabled_uniform_buffer_masks.value==a);
    if constexpr (persistent) {
       assert(c.dirty_uniform_buffers[0]==~u32{0});
       assert(c.uniform_buffer_binding_sizes[0]==0);
    }
    c.fast_bound_uniform_buffers.fill(20);
    c.dirty_uniform_buffers.fill(21);
    c.uniform_buffer_binding_sizes.fill(22);
    owner.SetUniformBuffersState(a,&sizes2);
    assert(c.uniform_buffer_sizes==&sizes2);
    assert(c.fast_bound_uniform_buffers[0]==20);
    assert(c.dirty_uniform_buffers[0]==21);
    assert(c.uniform_buffer_binding_sizes[0]==22);
    owner.SetUniformBuffersState(b,&sizes1);
    assert(c.uniform_buffer_sizes==&sizes1);
    assert(c.enabled_uniform_buffer_masks.value==b);
    assert(c.fast_bound_uniform_buffers[0]==0);
    if constexpr (persistent) {
       assert(c.dirty_uniform_buffers[0]==~u32{0});
       assert(c.uniform_buffer_binding_sizes[0]==0);
    }
    assert(c.enabled_uniform_buffer_masks.stores==EXPECTED);
}
int main() {
    replay<true>();
    replay<false>();
    std::puts("F01_UNIFORM_REBIND_SEMANTICS_PASS");
}
"""
compiler=shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-f01-uniform-") as tmp:
    for profile, body, count in (("pinned",old,4),("maintained",new,2)):
        content=cpp.replace("__SOURCE__",body).replace("EXPECTED",str(count))
        source=Path(tmp)/(profile+".cpp")
        source.write_text(content)
        for opt in ("-O0","-O2"):
            exe=Path(tmp)/(profile+opt)
            build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra",
                 "-Werror","-fsanitize=undefined","-fno-sanitize-recover=all",
                 str(source),"-o",str(exe)],capture_output=True,text=True,timeout=45)
            assert build.returncode==0,(profile,opt,build.stderr[-4000:])
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            assert run.returncode==0,(profile,opt,run.stderr[-4000:])
            assert "F01_UNIFORM_REBIND_SEMANTICS_PASS" in run.stdout
            print("F01_UNIFORM_REBIND",profile,opt,"assignments=",count,flush=True)
print("F01_UNIFORM_REBIND_HOST_PASS original_mask_assignments=4"
      " maintained_mask_assignments=2 avoided=2 calls=4 not_fps=1")
