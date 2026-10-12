#!/usr/bin/env python3
"""R319: pinned GPU descriptor overflow drain without guest-cache lock."""
from pathlib import Path
from urllib.request import urlopen, Request
import ast
import hashlib
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
pin="5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
paths={
 "src/video_core/renderer_vulkan/vk_update_descriptor.h":"9f30e65dbd1d08dc70d4a00053c7dd44b2653c1f",
 "src/video_core/renderer_vulkan/vk_rasterizer.cpp":"f43bea1220c262678b744f793876b7e5ea69bdff"
}
tree=ast.parse((root/"tools/prepare-vulkan-port.py").read_text())
adapt_calls=[x for x in ast.walk(tree) if isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=="adapt"]
def replacements(path):
    calls=[x for x in adapt_calls if isinstance(x.args[0],ast.Constant) and x.args[0].value==path]
    assert len(calls)==1, path
    result=[]
    for pair in calls[0].args[2].elts:
        try: result.append(ast.literal_eval(pair))
        except (ValueError, TypeError, SyntaxError): pass
    return result
patched={}
for path,sha in paths.items():
    url=f"https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{path}"
    with urlopen(Request(url,headers={"User-Agent":"Eden-Encore-R319-pinned-source"}),timeout=25) as r:
        data=r.read(200000)
    git_blob=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
    assert git_blob==sha, (path,git_blob,sha)
    patched[path]=data.decode()
header_path="src/video_core/renderer_vulkan/vk_update_descriptor.h"
raster_path="src/video_core/renderer_vulkan/vk_rasterizer.cpp"
hr=[x for x in replacements(header_path) if "PreflightGuestDraw" in x[1]]
# R382 preserves the already-inserted preflight in its before/after
# scheduling-capacity replacement. Select only the ORIGINAL R319 insertion
# into the pinned upstream file, whose original source has no preflight.
rr=[x for x in replacements(raster_path)
    if "PreflightGuestDraw" in x[1] and "PreflightGuestDraw" not in x[0]]
assert len(hr)==len(rr)==1
h_old,h_new=hr[0]
r_old,r_new=rr[0]
assert patched[header_path].count(h_old)==1
patched[header_path]=patched[header_path].replace(h_old,h_new)
assert patched[raster_path].count(r_old)==1
patched[raster_path]=patched[raster_path].replace(r_old,r_new)
header=patched[header_path]
raster=patched[raster_path]
assert "#ifdef PS5_NATIVE\n    template <typename WaitWorker>" in header
assert "guest_descriptor_queue.PreflightGuestDraw([this] { scheduler.WaitWorker(); })" in raster
assert raster.index("PreflightGuestDraw") < raster.index("GraphicsPipeline* const pipeline{pipeline_cache.CurrentGraphicsPipeline()}")
assert "gpu_memory->FlushCaching();\n    }\n#endif" in raster
# Acquire must retain its original worker wait (also handles exceptional
# reservations larger than 0x400 and non-PS5 builds).
impl=(urlopen(Request(
    f"https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/src/video_core/renderer_vulkan/vk_update_descriptor.cpp",
    headers={"User-Agent":"Eden-Encore-R319-pinned-source"}),timeout=25).read()).decode()
assert "scheduler.WaitWorker();" in impl
assert "if (used + reserve >= frame_payload_size)" in impl
start=header.index("    template <typename WaitWorker>")
end=header.index("\n#endif",start)
method=header[start:end]
code=r"""
#include <cassert>
#include <cstddef>
#include <vector>
struct Queue {
    const size_t frame_payload_size=0x80000;
    std::vector<unsigned> buffer=std::vector<unsigned>(frame_payload_size);
    unsigned* payload_start=buffer.data();
    unsigned* payload_cursor=payload_start;
""" + method + r"""
    void consume(size_t n) { assert(size_t(payload_cursor-payload_start)+n<frame_payload_size); payload_cursor+=n; }
    void original_acquire_fallback(size_t n, int& waits) {
        if (size_t(payload_cursor-payload_start)+n>=frame_payload_size) {
            ++waits; payload_cursor=payload_start;
        }
        consume(n);
    }
};
int main(){
    Queue q;
    int waits=0;
    // Ordinary draw: no wait, cursor untouched.
    q.consume(1024);
    assert(!q.PreflightGuestDraw([&]{++waits;}));
    assert(waits==0 && q.payload_cursor-q.payload_start==1024);
    // Ring almost full: preflight waits before locks and restarts safely.
    q.consume(q.frame_payload_size-1024-500);
    assert(q.PreflightGuestDraw([&]{++waits;}));
    assert(waits==1 && q.payload_cursor==q.payload_start);
    q.original_acquire_fallback(1000, waits);
    assert(waits==1);
    // Exceptional draw with >0x400 descriptors still relies on original gate.
    q.consume(q.frame_payload_size-1000-1500);
    assert(!q.PreflightGuestDraw([&]{++waits;}));
    q.original_acquire_fallback(1600,waits);
    assert(waits==2);
    // Exactly at the boundary must pre-drain as in Acquire (>=).
    q.consume(q.frame_payload_size-1600-1024);
    assert(q.PreflightGuestDraw([&]{++waits;}));
    assert(waits==3 && q.payload_cursor==q.payload_start);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-r319-guest-descriptors-") as tmp:
    cpp=Path(tmp)/"preflight.cpp"
    cpp.write_text(code)
    exe=Path(tmp)/"preflight"
    subprocess.run(["c++","-std=c++20","-O2","-Wall","-Wextra","-Werror",str(cpp),"-o",str(exe)],check=True,timeout=30)
    subprocess.run([str(exe)],check=True,timeout=10)
print("PASS R319 pinned producer preflight, overflow worker fence, and original larger fallback")
