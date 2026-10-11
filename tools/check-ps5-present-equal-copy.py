#!/usr/bin/env python3
"""R316: actual pinned Eden present-copy code and branch-sensitive native C++ fixture."""
from pathlib import Path
from urllib.request import urlopen, Request
import ast
import hashlib
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pin = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
rel = "src/video_core/renderer_vulkan/vk_present_manager.cpp"
blob_sha = "3491f8fb7563f2557a476fec8edb4f220f5d27fc"
url = f"https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{rel}"
with urlopen(Request(url, headers={"User-Agent":"Eden-Encore-R316-pinned-source"}), timeout=25) as request:
    raw = request.read(150000)
actual_sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
assert actual_sha == blob_sha, (actual_sha, blob_sha)
source = raw.decode()
assert "frame->image = memory_allocator.CreateImage({" in source
assert ".format = swapchain.GetImageFormat()" in source
# Swapchain output image and frame image both have swapchain.GetImageFormat().
# This prevents changing the blit path on formats which require conversion.

module = ast.parse((root / "tools/prepare-vulkan-port.py").read_text())
adapters = [
    call for call in ast.walk(module) if isinstance(call, ast.Call)
    and isinstance(call.func, ast.Name) and call.func.id == "adapt"
    and len(call.args) == 3
    and isinstance(call.args[0], ast.Constant)
    and call.args[0].value == rel
]
assert len(adapters) == 1
replacements = [ast.literal_eval(t) for t in adapters[0].args[2].elts]
matches = [(old, new) for old, new in replacements if "if (blit_supported)" in old]
assert len(matches) == 1
old, new = matches[0]
assert source.count(old) == 1
source = source.replace(old, new)
start = source.index("    if (blit_supported\n#ifdef PS5_NATIVE")
end = source.index("\n    cmdbuf.PipelineBarrier(", start)
statement = source[start:end]
assert "VK_FILTER_LINEAR" in statement
assert "cmdbuf.CopyImage(" in statement
assert "cmdbuf.BlitImage(" in statement
assert statement.count("#ifdef PS5_NATIVE") == 1

head = r"""
#include <cassert>
#include <cstdint>
struct Extent { unsigned width{}, height{}; };
struct Frame { int width{}, height{}; int* image{}; };
struct Recorder {
    mutable int copied{}, blitted{};
    template<class... T> void CopyImage(T...) const { ++copied; }
    template<class... T> void BlitImage(T...) const { ++blitted; }
};
static constexpr int VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL=1;
static constexpr int VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL=2;
static constexpr int VK_FILTER_LINEAR=3;
inline int MakeImageBlit(int,int,unsigned,unsigned) { return 0; }
inline int MakeImageCopy(int,int,unsigned,unsigned) { return 0; }
void scenario(int from_width, int from_height, unsigned to_width, unsigned to_height,
              bool blit_supported, bool expected_copy) {
    int original_image=123;
    Frame frame_value{from_width,from_height,&original_image};
    const Frame* frame=&frame_value;
    const Extent extent{to_width,to_height};
    const int image=321;
    const Recorder cmdbuf{};
"""
tail = r"""
    if (expected_copy) {
        assert(cmdbuf.copied==1 && cmdbuf.blitted==0);
    } else {
        assert(cmdbuf.copied==0 && cmdbuf.blitted==1);
    }
}
int main() {
#ifdef PS5_NATIVE
    scenario(3840,2160,3840,2160,true,true);
    scenario(2560,1440,3840,2160,true,false);
    scenario(1920,1080,3840,2160,true,false);
    scenario(3840,2160,3840,2160,false,true);
    scenario(2560,1440,3840,2160,false,true);
    scenario(3840,2160,2560,1440,true,false);
#else
    scenario(3840,2160,3840,2160,true,false);
    scenario(2560,1440,3840,2160,true,false);
    scenario(3840,2160,3840,2160,false,true);
#endif
}
"""
with tempfile.TemporaryDirectory(prefix="eden-r316-copy-on-equal-") as tmp:
    cpp = Path(tmp)/"present.cpp"
    cpp.write_text(head + statement + tail)
    for name,flags in (("ps5",["-DPS5_NATIVE"]),("upstream",[])):
        exe = Path(tmp)/name
        subprocess.run(["c++","-std=c++20","-O2","-Wall","-Wextra","-Werror",
                        *flags,str(cpp),"-o",str(exe)],check=True,timeout=30)
        subprocess.run([str(exe)],check=True,timeout=10)
        print("PASS R316 exact native present choice",name)
print("PASS R316 pinned Eden VideoOut copy/blit source contract")
