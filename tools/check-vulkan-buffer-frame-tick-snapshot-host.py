#!/usr/bin/env python3
"""Source-extracted frame-reclamation tick snapshot, ASan/UBSan (host only)."""
from pathlib import Path
import subprocess
import shutil
import tempfile
ROOT=Path(__file__).resolve().parents[1]
ACTIVE=(ROOT/"vendor/encore-active/eden-vulkan/vk_buffer_cache_cost.cpp").read_text()
PIN=(ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_buffer_cache.cpp").read_text()
GEN=(ROOT/"tools/prepare-vulkan-port.py").read_text()
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-vulkan-buffer-frame-tick-snapshot-host.py" in FAST
assert "python3 -B tools/check-vulkan-buffer-frame-tick-snapshot-host.py" in FULL
assert "Capture the completed GPU tick once" in GEN
start="void BufferCacheRuntime::TickFrame("
end="\n\nu64 BufferCacheRuntime::CurrentTick()"
def extract(s):
    assert s.count(start)==1 and s.count(end)==1
    return s[s.index(start):s.index(end,s.index(start))]
original=extract(PIN)
modified=extract(ACTIVE)
assert "scheduler.IsFree(it->LastUsageTick())" in original
assert "scheduler.GetMasterSemaphore().KnownGpuTick()" in modified
assert "scheduler.IsFree(it->LastUsageTick())" not in modified
assert "#ifdef PS5_NATIVE\n    // No tracked buffers" in modified
assert modified.index("if (slot_buffers.begin() == slot_buffers.end())") < modified.index("KnownGpuTick()")
assert "No tracked buffers: avoid even the GPU-completion semaphore snapshot" in GEN
cpp=r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>
using u64=std::uint64_t;
namespace Common { template<class T> struct SlotVector:std::vector<T>{}; }
struct Buffer {
  u64 tick;
  bool tracking=true;
  u64 LastUsageTick() const noexcept {return tick;}
  void ResetUsageTracking() noexcept {
    tracking=false;
#ifdef PS5_NATIVE
    // The selected Buffer::ResetUsageTracking retires the usage tick too.
    tick=0;
#endif
  }
};
struct MasterSemaphore {
  u64 completed=0;
  mutable unsigned reads=0;
  u64 KnownGpuTick() const noexcept {++reads;return completed;}
};
struct Scheduler {
  MasterSemaphore& m;
  bool IsFree(u64 tick)const noexcept{return m.KnownGpuTick()>=tick;}
  MasterSemaphore& GetMasterSemaphore()const noexcept{return m;}
};
struct BufferCacheRuntime {
  Scheduler& scheduler;
  void TickFrame(Common::SlotVector<Buffer>&) noexcept;
};
INJECT
int main(){
  MasterSemaphore sem{7,0};
  Scheduler scheduler{sem};
  BufferCacheRuntime cache{scheduler};
  Common::SlotVector<Buffer> buffers;
  for(u64 tick:std::array<u64,6>{0,3,6,7,8,12})
    buffers.push_back(Buffer{tick,tick!=0});
  cache.TickFrame(buffers);
  for(unsigned i=0;i<buffers.size();++i)
    assert(buffers[i].tracking==(i>=4));
  assert(sem.reads==FRAME_READS);
#ifdef PS5_NATIVE
  // The initial unused buffer has tick zero, not a pending GPU use.
  assert(buffers[0].tick==0);
  for(unsigned i=1;i<4;++i)assert(buffers[i].tick==0);
  assert(buffers[4].tick==8 && buffers[5].tick==12);
#endif
  sem.completed=12;
  cache.TickFrame(buffers);
  for(const auto& buffer:buffers)assert(!buffer.tracking);
  assert(sem.reads==2*FRAME_READS);
  buffers.clear();
  cache.TickFrame(buffers);
  assert(sem.reads==
#ifdef PS5_NATIVE
         EMPTY_NATIVE_READS
#else
         EMPTY_READS
#endif
  );
  std::puts("ENCORE_BUFFER_FRAME_TICK_SNAPSHOT_PASS");
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="eden-tick-snapshot-") as d:
    folder=Path(d)
    for name,body,reads,empty,native_empty,ps5 in (
        ("pinned",original,6,12,12,False),
        ("maintained-desktop",modified,1,3,3,False),
        ("maintained-ps5",modified,1,3,2,True),
    ):
        src=folder/(name+".cpp")
        binary=folder/name
        program=(cpp.replace("INJECT",body)
                    .replace("EMPTY_NATIVE_READS",str(native_empty))
                    .replace("FRAME_READS",str(reads))
                    .replace("EMPTY_READS",str(empty)))
        src.write_text(program)
        subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        *(["-DPS5_NATIVE=1"] if ps5 else []),
                        str(src),"-o",str(binary)],check=True,timeout=90)
        subprocess.run([str(binary)],check=True,timeout=30)
print("VULKAN_BUFFER_TICK_SNAPSHOT_HOST_PASS no_empty_ps5_poll=1 desktop_unchanged=1; PS5 FPS unmeasured")
