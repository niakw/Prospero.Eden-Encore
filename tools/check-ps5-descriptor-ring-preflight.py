#!/usr/bin/env python3
"""R323 source-backed: move descriptor-buffer frame wait outside GPU cache pair."""
from pathlib import Path
from urllib.request import Request,urlopen
import ast,hashlib,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
pin="5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
blobs={
 "src/video_core/renderer_vulkan/vk_descriptor_buffer.h":"6f96bcc326e10a313470f6d8cb3022a86f6f2aa2",
 "src/video_core/renderer_vulkan/vk_descriptor_buffer.cpp":"279847fa997ecb72b77e693a751859d9c4e780c8",
 "src/video_core/renderer_vulkan/vk_rasterizer.cpp":"f43bea1220c262678b744f793876b7e5ea69bdff"
}
gen=(root/"tools/prepare-vulkan-port.py").read_text()
tree=ast.parse(gen)
adapter=[x for x in ast.walk(tree) if isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=="adapt" and x.args]
def adapter_changes(path):
 c=[x for x in adapter if isinstance(x.args[0],ast.Constant) and x.args[0].value==path]
 assert len(c)==1,(path,len(c))
 # Other replacements may be generated from local string variables; only
 # production R323 pairs have a direct pair of string literals.
 return [ast.literal_eval(x) for x in c[0].args[2].elts if isinstance(x,ast.Tuple)
         and all(isinstance(e,ast.Constant) for e in x.elts)]
patched={}
for path,sha in blobs.items():
 with urlopen(Request(f"https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{path}",
                      headers={"User-Agent":"Eden-Encore-R323-pinned-source"}),timeout=25) as r:
  blob=r.read(220000)
 got=hashlib.sha1(b"blob "+str(len(blob)).encode()+b"\0"+blob).hexdigest()
 assert got==sha,(path,got,sha)
 patched[path]=blob.decode()
for path in blobs:
 changes=adapter_changes(path)
 wanted="PreflightFrameReuse" if path.endswith("vk_descriptor_buffer.cpp") or path.endswith("vk_descriptor_buffer.h") else "CanUseDescriptorBuffer"
 pairs=[(old,new) for old,new in changes if wanted in new]
 if path.endswith("vk_rasterizer.cpp"):
  # Select the original GRAPHICS R323 adapter, not the later compute fence.
  pairs=[(old,new) for old,new in changes
         if "descriptor_buffer_ring.PreflightFrameReuse(scheduler)" in new
         and "pipeline_cache.CurrentGraphicsPipeline()" in new]
 assert len(pairs)==1,(path,len(pairs))
 old,new=pairs[0]
 assert patched[path].count(old)==1,path
 patched[path]=patched[path].replace(old,new)
# The adapter-produced new block is before any guest-cache pair acquisition.
rast=patched["src/video_core/renderer_vulkan/vk_rasterizer.cpp"]
assert "pipeline->CanUseDescriptorBuffer()" in rast
assert rast.index("descriptor_buffer_ring.PreflightFrameReuse(scheduler)") < rast.index("std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};")
frame = rast.split("descriptor_buffer_ring.PreflightFrameReuse(scheduler)", 1)[1].split(
    "descriptor_buffer_ring.PreflightCapacity(", 1)[0]
assert "gpu_memory->FlushCaching();" in frame
assert frame.count("pipeline = pipeline_cache.CurrentGraphicsPipeline();") == 2
assert "guest_descriptor_queue.PreflightExactGuestDraw(" in frame
hdr=(root/"tools/prepare-vulkan-port.py").read_text()
assert "return uses_descriptor_buffer && descriptor_set_layout;" in hdr
cpp=patched["src/video_core/renderer_vulkan/vk_descriptor_buffer.cpp"]
# Original Allocate remains authoritative on skipped/no-preflight paths.
assert "if (frame_reused)" in cpp
assert "scheduler.Wait(frame_ticks[frame_index]);" in cpp
assert "scheduler.Finish();" in cpp
# The linked native descriptor TU is generated from the adapted Vulkan
# descriptor implementation, not from unpatched upstream. Protect this
# composition rule to catch a declaration-only link failure.
assert "if name == 'vk_descriptor_buffer':" in gen
assert "text = (output / 'vulkan_descriptor_buffer.cpp').read_text()" in gen
assert "('vk_descriptor_buffer', 10, 4)" in gen
assert cpp.count("scheduler.Wait(frame_ticks[frame_index]);") == 2
assert cpp.count("scheduler.Finish();") == 2
start=cpp.index("bool DescriptorBufferRing::PreflightFrameReuse(")
end=cpp.index("\n}",start)+2
method=cpp[start:end]
with tempfile.TemporaryDirectory(prefix="eden-r323-ring-") as tmp:
 p=Path(tmp)/"ring.cpp"
 p.write_text(r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>
using u64=std::uint64_t;
struct Scheduler{
 int waits=0;
 u64 last=0;
 void Wait(u64 tick){++waits;last=tick;}
};
class DescriptorBufferRing{
public:
 bool PreflightFrameReuse(Scheduler&);
 bool frame_reused=false;
 std::vector<int> chunks{7};
 size_t frame_index=2;
 std::array<u64,8> frame_ticks{};
};
#ifdef PS5_NATIVE
""" + method + r"""
#endif
int main(){
 Scheduler s;
 DescriptorBufferRing r;
#ifdef PS5_NATIVE
 assert(!r.PreflightFrameReuse(s) && s.waits==0);
 r.frame_reused=true;
 r.chunks.clear();
 assert(!r.PreflightFrameReuse(s) && r.frame_reused && s.waits==0);
 r.chunks.push_back(7);
 r.frame_ticks[2]=421;
 assert(r.PreflightFrameReuse(s) && s.waits==1 && s.last==421);
 assert(!r.frame_reused && !r.PreflightFrameReuse(s) && s.waits==1);
 // An independent next-frame recycle must repeat the normal fence drain.
 r.frame_reused=true;r.frame_ticks[2]=623;
 assert(r.PreflightFrameReuse(s) && s.waits==2 && s.last==623);
#else
 assert(s.waits==0);
#endif
}
""")
 for label,flags in (("ps5",["-DPS5_NATIVE"]),("upstream",[])):
  exe=Path(tmp)/label
  subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",
                  *flags,str(p),"-o",str(exe)],check=True,timeout=30)
  subprocess.run([str(exe)],check=True,timeout=10)
  print("PASS R323 native and upstream ring preflight",label)
print("PASS R323 pinned core descriptor frame wait moved ahead of both cache locks")
