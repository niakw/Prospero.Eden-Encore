#!/usr/bin/env python3
"""Clang ASan/UBSan: late pipeline reselection never waits under guest cache locks.

The active preflight implementation is compiled verbatim from its shipping header.
Source guards ensure the late call stays AFTER the ring drain's pipeline refresh
and BEFORE the two cache mutexes; the mock exercises an actual reservation gap.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
header=(root/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_update_descriptor.h").read_text()
raster=(root/"vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
workflow=(root/".github/workflows/encore-core-preflight.yml").read_text()

start="    template <typename WaitWorker>\n    [[nodiscard]] bool PreflightGuestDraw("
last="    template <typename WaitWorker>\n    [[nodiscard]] bool PreflightExactGuestDraw("
end="\n#endif"
assert header.count(start)==header.count(last)==1
preflights=header[header.index(start):header.index(end,header.index(last))]
# Compile the exact maintained methods, not an older named helper. This
# preserves the >= ring-boundary drain and rejects zero/oversized reservations.
assert preflights.count("wait_worker();")==2
assert "used + reserve < frame_payload_size" in preflights
assert "reserve >= frame_payload_size" in preflights
assert "used + entries < frame_payload_size" in preflights
assert "entries == 0 || entries >= frame_payload_size" in preflights

start=raster.index("void RasterizerVulkan::PrepareDraw(")
end=raster.index("void RasterizerVulkan::Draw(",start)
draw=raster[start:end]
initial=draw.index("guest_descriptor_queue.PreflightGuestDraw(")
retry=draw.index("for (unsigned preflight = 0; preflight != 2; ++preflight)")
retry_exact=draw.index("guest_descriptor_queue.PreflightExactGuestDraw(",retry)
reuse=draw.index("descriptor_buffer_ring.PreflightFrameReuse(",retry_exact)
reuse_refresh=draw.index("pipeline = pipeline_cache.CurrentGraphicsPipeline();",reuse)
reuse_preflight=draw.index("guest_descriptor_queue.PreflightExactGuestDraw(",reuse_refresh)
cap=draw.index("descriptor_buffer_ring.PreflightCapacity(",reuse_preflight)
reselection=draw.index("pipeline = pipeline_cache.CurrentGraphicsPipeline();",cap)
late=draw.index("guest_descriptor_queue.PreflightExactGuestDraw(",reselection)
cache_lock=draw.index("std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};")
# Both GPU ring drains must reselect shaders and revalidate *exact* positive
# descriptor demand before either guest cache mutex can be acquired.
assert initial < retry < retry_exact < reuse < reuse_refresh < reuse_preflight < cap < reselection < late < cache_lock
assert draw.count("guest_descriptor_queue.PreflightExactGuestDraw(")==3
assert draw.count("guest_descriptor_queue.PreflightGuestDraw(")==1
assert draw.count("pipeline->HasDescriptorEntries()")>=4
assert "gpu_memory->FlushCaching();" in draw[reuse:reuse_refresh]
for section in (draw[reuse_preflight:cap],draw[late:cache_lock]):
    assert "gpu_memory->FlushCaching();" in section
    assert "pipeline = pipeline_cache.CurrentGraphicsPipeline();" in section
    assert "GraphicsDrawDrop::NoPipeline" in section
# Guard the bounded second preflight after a pipeline may have changed again.
assert "preflight != 2" in draw[retry:reuse]
assert "pipeline = pipeline_cache.CurrentGraphicsPipeline();" in draw[retry_exact:reuse]
assert "check-ps5-late-descriptor-preflight-host.py" in workflow

cpp=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
struct DescriptorQueue {
  std::array<std::uint64_t,4096> payload{};
  const std::size_t frame_payload_size=payload.size();
  std::uint64_t* payload_start=payload.data();
  std::uint64_t* payload_cursor=payload.data();
__PREFLIGHT__
  void SetUsed(std::size_t n){assert(n<=frame_payload_size);payload_cursor=payload_start+n;}
  std::size_t Used()const{return static_cast<std::size_t>(payload_cursor-payload_start);}
};
int main(){
 DescriptorQueue q;
 unsigned waits=0;
 bool cache_locks_held=false;
 auto wait_worker=[&] { assert(!cache_locks_held);++waits; };
 // The original pipeline fits both the ordinary and large preflights.
 q.SetUsed(2596);
 assert(!q.PreflightGuestDraw(wait_worker));
 assert(!q.PreflightExactGuestDraw(wait_worker,0x400));
 assert(q.Used()==2596 && waits==0);
 // A descriptor-ring GPU drain followed by guest invalidation selects a
 // different pipeline (reservation 1700); Acquire would wait under locks.
 const std::size_t reselection_reserve=1700;
 assert(q.Used()+reselection_reserve>=q.frame_payload_size);
 assert(q.PreflightExactGuestDraw(wait_worker,reselection_reserve));
 assert(waits==1 && q.Used()==0);
 // The following Configure/Acquire now has no reason to wait under locks.
 cache_locks_held=true;
 assert(q.Used()+reselection_reserve<q.frame_payload_size);
 cache_locks_held=false;
 // No needless drains for the common reservation or adequate capacity.
 q.SetUsed(50);
 assert(!q.PreflightGuestDraw(wait_worker));
 assert(!q.PreflightExactGuestDraw(wait_worker,1700));
 assert(waits==1);
 // A frame-reuse fence may change shaders to a larger pipeline, too.
 q.SetUsed(3000);
 assert(!q.PreflightExactGuestDraw(wait_worker,1024));
 assert(q.PreflightExactGuestDraw(wait_worker,1200));
 assert(q.Used()==0 && waits==2);
 // Equality with the end boundary uses the same >= condition as Acquire.
 q.SetUsed(4096-1700);
 assert(q.PreflightExactGuestDraw(wait_worker,1700));
 assert(q.Used()==0 && waits==3);
 // Oversized reservations continue to be handled by Acquire's invariant.
 assert(!q.PreflightExactGuestDraw(wait_worker,4096));
 assert(waits==3);
 // The precise path must not drain for zero descriptors; reservations below
 // the old 1024-entry fallback still drain when they actually cross the end.
 q.SetUsed(4000);
 assert(!q.PreflightExactGuestDraw(wait_worker,0));
 assert(q.PreflightExactGuestDraw(wait_worker,128));
 assert(q.Used()==0 && waits==4);
}
"""
cc=shutil.which("clang++-18") or shutil.which("clang++")
assert cc, "Clang C++20 required for host regression"
with tempfile.TemporaryDirectory(prefix="encore-late-descriptor-") as folder:
    code=Path(folder)/"test.cpp"
    exe=Path(folder)/"test"
    code.write_text(cpp.replace("__PREFLIGHT__",preflights))
    subprocess.run([cc,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(code),"-o",str(exe)],check=True,timeout=45)
    subprocess.run([str(exe)],check=True,timeout=30)
print("LATE_DESCRIPTOR_PREFLIGHT_HOST_PASS old_preflight_gap=1 late_drain=1 frame_reuse_refresh=1 no_lock_wait=1 exact_boundary=1 zero_and_small_reservations=1 source_order=1")
