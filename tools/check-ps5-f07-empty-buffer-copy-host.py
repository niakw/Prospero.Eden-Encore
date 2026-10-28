#!/usr/bin/env python3
"""Exercise the selected Vulkan empty-copy and zero-size clear guards.

Empty batches must never enqueue a zero-region copy on PS5. An explicit
barrier request retains both original ordering barriers; desktop is unchanged.
"""
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/"vendor/encore-active/eden-vulkan/vk_buffer_cache_cost.cpp").read_text()
pinned=(ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_buffer_cache.cpp").read_text()
generator=(ROOT/"tools/prepare-vulkan-port.py").read_text()
fast=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
preflight=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
invoke="python3 -B tools/check-ps5-f07-empty-buffer-copy-host.py"
assert invoke in fast and invoke in preflight
ast.parse(generator)
assert "F07 avoid barrier-free empty Vulkan buffer copies" in generator
assert "F07 skip zero-sized Vulkan buffer fill" in generator
begin="void BufferCacheRuntime::CopyBuffer(VkBuffer dst_buffer, VkBuffer src_buffer,"
stop="    static constexpr VkMemoryBarrier READ_BARRIER{"
def guards(text):
    assert text.count(begin)==1
    start=text.index("    if (dst_buffer == VK_NULL_HANDLE",text.index(begin))
    end=text.index(stop,start)
    return text[start:end]
selected=guards(source)
original=guards(pinned)
clear_begin="void BufferCacheRuntime::ClearBuffer(VkBuffer dest_buffer, u32 offset, size_t size, u32 value) {"
def clear_guards(text):
    assert text.count(clear_begin)==1
    start=text.index("    if (dest_buffer == VK_NULL_HANDLE",text.index(clear_begin))
    end=text.index("    static constexpr VkMemoryBarrier READ_BARRIER{", start)
    return text[start:end]
selected_clear=clear_guards(source)
original_clear=clear_guards(pinned)
assert selected_clear.count("if (size == 0)")==1
assert "#ifdef PS5_NATIVE" in selected_clear and "#endif" in selected_clear
assert selected_clear.index("dest_buffer == VK_NULL_HANDLE") < selected_clear.index("if (size == 0)")
assert "if (size == 0)" not in original_clear
assert source.index("if (size == 0)", source.index(clear_begin)) < source.index("scheduler.Record(",source.index(clear_begin))
assert selected.count("if (copies.empty())") == 1
assert selected.count("PreCopyBarrier();") == 1
assert selected.count("PostCopyBarrier();") == 1
assert selected.index("if (copies.empty())") < selected.index("PreCopyBarrier();")
assert "#ifdef PS5_NATIVE" in selected and "#endif" in selected
assert "copies.empty()" not in original
assert selected.index("dst_buffer == VK_NULL_HANDLE") < selected.index("copies.empty()")
assert source.count("scheduler.RecordWithUploadBuffer(")>=1
assert source.count("scheduler.RequestOutsideRenderPassOperationContext();")>=1

cpp=r"""
#include <cassert>
#include <cstddef>
#include <span>
using VkBuffer=std::size_t;
constexpr VkBuffer VK_NULL_HANDLE=0;
struct Copy {std::size_t size;};
struct Runtime {
 unsigned records{};
 unsigned pre_barriers{}, post_barriers{};
 void PreCopyBarrier() { ++pre_barriers; }
 void PostCopyBarrier() { ++post_barriers; }
 void CopyBuffer(VkBuffer dst_buffer,VkBuffer src_buffer,
                 [[maybe_unused]] std::span<const Copy> copies,
                 [[maybe_unused]] bool barrier,bool) {
""" + selected + r"""
  // Mock only what follows the original guarded region. Both upload
  // and transfer paths can queue one callback, with extra barriers
  // when requested.
  ++records;
 }
};
struct ClearRuntime {
 unsigned records{};
 void ClearBuffer(VkBuffer dest_buffer, [[maybe_unused]] unsigned offset,
                  [[maybe_unused]] std::size_t size, [[maybe_unused]] unsigned value) {
""" + selected_clear + r"""
  ++records;
 }
};
int main() {
 Runtime invalid;
 invalid.CopyBuffer(0,2,{},false,false);
 invalid.CopyBuffer(1,0,{},true,false);
 assert(invalid.records==0);

 Runtime empty;
 empty.CopyBuffer(1,2,{},false,false);
#ifdef PS5_NATIVE
 assert(empty.records==0);
#else
 assert(empty.records==1);
#endif

 Runtime barrier;
 barrier.CopyBuffer(1,2,{},true,false);
#ifdef PS5_NATIVE
 assert(barrier.records==0 && barrier.pre_barriers==1 && barrier.post_barriers==1);
#else
 assert(barrier.records==1 && barrier.pre_barriers==0 && barrier.post_barriers==0);
#endif

 Runtime one;
 const Copy item{1024};
 one.CopyBuffer(1,2,std::span<const Copy>(&item,1),false,false);
 assert(one.records==1);
 one.CopyBuffer(1,2,std::span<const Copy>(&item,1),true,true);
 assert(one.records==2);

 Runtime many;
 const Copy items[2]{{128},{256}};
 many.CopyBuffer(1,2,items,false,true);
 assert(many.records==1);

 ClearRuntime cleared;
 cleared.ClearBuffer(0,0,16,0);
 assert(cleared.records==0);
 cleared.ClearBuffer(1,0,0,0);
#ifdef PS5_NATIVE
 assert(cleared.records==0);
#else
 assert(cleared.records==1);
#endif
 cleared.ClearBuffer(1,4,256,0xaabbccdd);
#ifdef PS5_NATIVE
 assert(cleared.records==1);
#else
 assert(cleared.records==2);
#endif
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-empty-copy-") as folder:
    path=Path(folder)/"guards.cpp"
    path.write_text(cpp)
    for opt in ("-O0","-O2"):
        for ps5 in (False,True):
            exe=Path(folder)/("guard"+opt+("ps5" if ps5 else "desktop"))
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(["-DPS5_NATIVE=1"] if ps5 else []),str(path),"-o",str(exe)]
            build=subprocess.run(cmd,text=True,capture_output=True,timeout=40)
            assert build.returncode==0,(cmd,build.stderr[-4000:])
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            assert run.returncode==0,(opt,ps5,run.stderr[-4000:])
print("F07_EMPTY_BUFFER_COPY_HOST_PASS null=1 zero_no_barrier=1"
      " barrier_only_pre_post=1 no_empty_vulkan_copy=1 one=1 many=1 zero_fill=1 desktop=1 O0_O2=1")
