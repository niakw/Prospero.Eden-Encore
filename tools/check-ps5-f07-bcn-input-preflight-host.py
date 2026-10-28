#!/usr/bin/env python3
"""F07 native BCn3D pre-allocation source-extracted input/batch rejection."""
from pathlib import Path
import shutil, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/"vendor/encore-active/eden-vulkan/vk_compute_pass_cost.cpp").read_text()
gen=(ROOT/"tools/prepare-vulkan-port.py").read_text()
pinned=(ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_compute_pass.cpp").read_text()
start=src.index("void BlockLinearUnswizzle3DPass::Unswizzle(")
end=src.index("\nvoid BlockLinearUnswizzle3DPass::UnswizzleChunk(",start)
method=src[start:end]
begin="    using namespace VideoCommon::Accelerated;"
stop="    const u32 MAX_BATCH_SLICES = (std::min)(z_count, image.info.size.depth);"
assert method.count(begin)==1 and method.count(stop)==1
block=method[method.index(begin)+len(begin):method.index(stop)]
assert block.startswith("\n\n#ifdef PS5_NATIVE")
assert block.rstrip().endswith("#endif")
assert "swizzles.size() != 1" in block
assert "z_count > image.info.size.depth - z_start" in block
assert "input.buffer_offset >= image.guest_size_bytes" in block
assert "input.buffer_offset > (~VkDeviceSize{0} - swizzled.offset)" in block
assert "mapped_span" not in block.split("if (input.buffer_offset")[1]
assert method.index("throw std::bad_alloc{};") < method.index("image.AllocateComputeUnswizzleBuffer")
assert stop in pinned and "F07 reject native BCn3D invalid slice and descriptor offsets before allocation" in gen
for wf in (".github/workflows/encore-core-fast-gate.yml",
           ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-bcn-input-preflight-host.py" in (ROOT/wf).read_text()
cpp=r"""
#include <cassert>
#include <cstdint>
#include <new>
#include <span>
#include <vector>
using u32=std::uint32_t;
using VkDeviceSize=std::uint64_t;
using VkBuffer=std::uint64_t;
constexpr VkBuffer VK_NULL_HANDLE=0;
struct Swizzle { VkDeviceSize buffer_offset{}; };
struct Staging { VkBuffer buffer{}; VkDeviceSize offset{}; };
struct Image { struct Info { struct Size { u32 depth{}; } size; } info; VkDeviceSize guest_size_bytes{}; };
struct Pass {
    unsigned allocated{};
    void Validate(Image& image,const Staging& swizzled,std::span<const Swizzle> swizzles,
                  u32 z_start,u32 z_count) {
        // The desktop fixture deliberately extracts a native-only guard.
        (void)image; (void)swizzled; (void)swizzles;
        (void)z_start; (void)z_count;
""" + block + r"""
        ++allocated;
    }
};
int main() {
    Pass p;
    Image image{{{8}},128};
    Staging staging{17,8};
    Swizzle valid[2]{{0},{8}};
    const auto run=[&](std::span<const Swizzle> sw,u32 z,u32 n,Staging sg=Staging{17,8}) {
        bool failed=false;
        auto count=p.allocated;
        try { p.Validate(image,sg,sw,z,n); }
        catch(const std::bad_alloc&) { failed=true; }
        assert(p.allocated==count+(failed?0:1));
        return failed;
    };
    assert(!run(std::span(valid,1),0,1));
    assert(!run(std::span(valid,1),6,2));
    assert(!run(std::span(valid+1,1),2,2));
#ifdef PS5_NATIVE
    assert(run({},0,1));
    assert(run(std::span(valid,2),0,1));
    assert(run(std::span(valid,1),0,0));
    assert(run(std::span(valid,1),8,1));
    assert(run(std::span(valid,1),~u32{0},1));
    assert(run(std::span(valid,1),7,2));
    assert(run(std::span(valid,1),1,8));
    assert(run(std::span(valid,1),0,1,Staging{0,8}));
    Swizzle at_end[]{ {128} };
    assert(run(at_end,0,1));
    Swizzle beyond[]{ {129} };
    assert(run(beyond,0,1));
    Swizzle sum_overflow[]{ {8} };
    assert(run(sum_overflow,0,1,Staging{17,~VkDeviceSize{0}-7}));
#else
    // Desktop's unchanged code intentionally has no early guard.
    assert(!run({},0,1));
    assert(!run(std::span(valid,1),8,1));
#endif
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-bcn-input-") as temp:
    srcfile=Path(temp)/"guard.cpp"
    srcfile.write_text(cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            exe=Path(temp)/(("ps5" if native else "desktop")+opt[1:])
            args=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                  "-fsanitize=undefined","-fno-sanitize-recover=all",
                  *(["-DPS5_NATIVE=1"] if native else []),str(srcfile),"-o",str(exe)]
            built=subprocess.run(args,capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-4000:])
            done=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert done.returncode==0,(native,opt,done.stderr[-4000:])
print("F07_BCN3D_INPUT_PREFLIGHT_PASS invalid_batches=1 no_allocation=1 offset_subtract=1 offset_sum=1 desktop_unchanged=1 O0=1 O2=1 UBSan=1")
