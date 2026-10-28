#!/usr/bin/env python3
"""F07 P0.4: reject a null BCn 3D destination before even allocating GPU scratch."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-vulkan/vk_compute_pass_cost.cpp").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
start=source.index("void BlockLinearUnswizzle3DPass::Unswizzle(")
end=source.index("\nvoid BlockLinearUnswizzle3DPass::UnswizzleChunk(",start)
body=source[start:end]
begin="    const u32 MAX_BATCH_SLICES = (std::min)(z_count, image.info.size.depth);"
last="    ASSERT(swizzles.size() == 1);"
assert body.count(begin)==body.count(last)==1
fragment=body[body.index(begin):body.index(last,body.index(begin))]
assert fragment.count("#ifdef PS5_NATIVE")==2
assert fragment.index("if (image.Handle() == VK_NULL_HANDLE)") < fragment.index(
    "image.AllocateComputeUnswizzleBuffer(MAX_BATCH_SLICES);")
assert fragment.index("image.AllocateComputeUnswizzleBuffer(MAX_BATCH_SLICES);") < fragment.index(
    "if (!image.compute_unswizzle_buffer ||")
assert "throw std::bad_alloc{};" in fragment
assert "F07 avoid wasted BCn3D output allocation for null native image" in generator
assert "F07 native reject null BCn3D destination before GPU upload" in generator
for wf in (".github/workflows/encore-core-fast-gate.yml",
           ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-bcn-image-null-preflight-host.py" in (root/wf).read_text()

cpp=r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <initializer_list>
#include <new>
using u32=std::uint32_t;
using VkImage=std::uint64_t;
using VkBuffer=std::uint64_t;
constexpr VkImage VK_NULL_HANDLE=0;
struct Buffer {
    VkBuffer handle{};
    explicit operator bool() const { return handle!=VK_NULL_HANDLE; }
    VkBuffer operator*() const { return handle; }
};
struct Image {
    struct Info { struct Size { u32 depth=8; } size; } info;
    VkImage image{};
    Buffer compute_unswizzle_buffer{};
    unsigned allocations{};
    VkImage Handle() const { return image; }
    void AllocateComputeUnswizzleBuffer(u32 n) {
        assert(n==1);
        ++allocations;
    }
};
struct Pass {
    unsigned queued{};
    void Begin(Image& image,u32 z_count=1) {
""" + fragment + r"""
        ++queued;
    }
};
int main() {
    for (auto which : {0,1,2}) {
        Image image;
        image.image=which==1 ? 3 : 0;
        image.compute_unswizzle_buffer.handle=which==0 ? 9 : 0;
        Pass pass;
        bool rejected=false;
        try {pass.Begin(image);} catch (const std::bad_alloc&) {rejected=true;}
#ifdef PS5_NATIVE
        assert(rejected && pass.queued==0);
        assert(image.allocations==(image.image==VK_NULL_HANDLE ? 0u : 1u));
#else
        assert(!rejected && pass.queued==1 && image.allocations==1);
#endif
    }
    Image valid;
    valid.image=3;
    valid.compute_unswizzle_buffer.handle=9;
    Pass pass;
    pass.Begin(valid);
    assert(pass.queued==1 && valid.allocations==1);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-bcn-null-output-") as d:
    unit=Path(d)/"test.cpp"
    unit.write_text(cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            output=Path(d)/(("ps5" if native else "desktop")+opt[1:])
            flags=["-DPS5_NATIVE=1"] if native else []
            build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                                  "-fsanitize=undefined","-fno-sanitize-recover=all",
                                  *flags,str(unit),"-o",str(output)],
                                  capture_output=True,text=True,timeout=40)
            assert build.returncode==0,(native,opt,build.stderr[-4000:])
            run=subprocess.run([str(output)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-4000:])
print("F07_BCN_DESTINATION_PREFLIGHT_PASS null_image_no_allocation=1 null_output_retry=1 zero_gpu_queue=1 native=1 desktop_original=1 O0=1 O2=1 UBSan=1")
