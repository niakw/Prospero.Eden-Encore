#!/usr/bin/env python3
"""F07 P0.4: invalid BCn3D destination is rejected before any GPU work."""
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
begin="#ifdef PS5_NATIVE\n    // A failed destination image is not a successful async BCn upload."
last="    ASSERT(swizzles.size() == 1);"
assert body.count(begin)==1
assert body.count(last)==1
guard=body[body.index(begin):body.index(last,body.index(begin))]
assert "if (image.Handle() == VK_NULL_HANDLE" in guard
assert "!image.compute_unswizzle_buffer" in guard
assert "*image.compute_unswizzle_buffer == VK_NULL_HANDLE" in guard
assert "throw std::bad_alloc{};" in guard
assert body.index("image.AllocateComputeUnswizzleBuffer(MAX_BATCH_SLICES);") < body.index(begin)
assert body.index(begin) < body.index("scheduler.RequestOutsideRenderPassOperationContext();")
assert "F07 native reject null BCn3D destination before GPU upload" in generator
for wf in (".github/workflows/encore-core-fast-gate.yml",
           ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-bcn-image-null-preflight-host.py" in (root/wf).read_text()

cpp=r"""
#include <cassert>
#include <cstdint>
#include <new>
using VkImage=std::uint64_t;
using VkBuffer=std::uint64_t;
constexpr VkImage VK_NULL_HANDLE=0;
struct Buffer {
    VkBuffer handle{};
    explicit operator bool() const { return handle!=VK_NULL_HANDLE; }
    VkBuffer operator*() const { return handle; }
};
struct Image {
    VkImage image{};
    Buffer compute_unswizzle_buffer{};
    VkImage Handle() const { return image; }
};
struct Pass {
    unsigned queued{};
    void Begin(Image& image) {
""" + guard + r"""
        ++queued;
    }
};
int main() {
    for (Image img : { Image{0,{9}}, Image{3,{0}}, Image{0,{0}} }) {
        Pass p;
        bool rejected=false;
        try {p.Begin(img);} catch (const std::bad_alloc&) { rejected=true; }
#ifdef PS5_NATIVE
        assert(rejected && p.queued==0);
#else
        assert(!rejected && p.queued==1);
#endif
    }
    Pass valid;
    Image image{3,{9}};
    valid.Begin(image);
    assert(valid.queued==1);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-bcn-output-null-") as d:
    source_file=Path(d)/"test.cpp"
    source_file.write_text(cpp)
    for native in (True, False):
        for opt in ("-O0","-O2"):
            output=Path(d)/(("ps5" if native else "desktop")+opt[1:])
            flags=["-DPS5_NATIVE=1"] if native else []
            build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                                  "-fsanitize=undefined","-fno-sanitize-recover=all",
                                  *flags,str(source_file),"-o",str(output)],
                                 capture_output=True,text=True,timeout=40)
            assert build.returncode==0,(native,opt,build.stderr[-4000:])
            run=subprocess.run([str(output)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-4000:])
print("F07_BCN_DESTINATION_PREFLIGHT_PASS null_image=1 null_output=1 prior_to_gpu_queue=1 native_retry_signal=1 desktop_original=1 O0=1 O2=1 UBSan=1")
