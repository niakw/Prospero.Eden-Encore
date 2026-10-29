#!/usr/bin/env python3
"""F07 PS5: source-extracted memory-budget polling avoids quiet lock work."""
from pathlib import Path
import shutil, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
a=src.index("void TextureCache<P>::TickFrame() {")
b=src.index("    sentenced_images.Tick();",a)
selected=src[a:b]
# The fixture intentionally extracts only the early budget policy, not the
# later async/runtime work where this C03 sample flag is consumed. The active
# source has no unused variable; silence only its truncated fixture copy.
sample_flag = "    const bool sample_housekeeping = detailed && ::Eden::Performance::ShouldSampleTextureHousekeeping();"
assert selected.count(sample_flag) == 1
selected = selected.replace(sample_flag, sample_flag + "\n    (void)sample_housekeeping;", 1)
assert "F07 native memory pressure sampling outside near GC watermark" in generator
assert "total_used_memory >= minimum_memory - minimum_memory / 3" in selected
assert "(frame_tick & 1u) == 0" in selected
assert selected.count("runtime.GetDeviceMemoryUsage();")==2
for flow in (".github/workflows/encore-core-fast-gate.yml", ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-memory-pressure-sampling-host.py" in (root/flow).read_text()
cpp=r"""
#include <cassert>
#include <atomic>
#include <cstddef>
#include <cstdint>
// This legacy fixture isolates the budget policy. The separate C03
// source-extracted fixture compiles the REAL CachePhaseTimer and verifies
// event counts, timer lifetimes, and silent-mode behavior.
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{false};
inline bool ShouldSampleTextureHousekeeping() noexcept { return false; }
enum class CachePhase { TextureBudgetQuery, TextureGcCollect };
struct CachePhaseTimer {
    explicit CachePhaseTimer(CachePhase, bool) noexcept {}
};
}
struct Runtime {
    bool report{true};
    std::size_t reported{100};
    int probes{0};
    bool CanReportMemoryUsage() const {return report;}
    std::size_t GetDeviceMemoryUsage() {++probes;return reported;}
};
template<class P>struct TextureCache {
    Runtime runtime;
    std::size_t total_used_memory{};
    std::size_t minimum_memory{900};
    std::size_t frame_tick{};
    int collections{};
    void RunGarbageCollector(){++collections;}
    void TickFrame();
};
struct PS5Mock {};
""" + "template<class P>\n" + selected + r"""
}
int main(){
    TextureCache<PS5Mock> c;
    for(int frame=0; frame<8; ++frame){
        c.frame_tick=frame;
        c.TickFrame();
    }
#ifdef PS5_NATIVE
    assert(c.runtime.probes==4);
#else
    assert(c.runtime.probes==8);
#endif
    assert(c.collections==0);
    c.runtime.reported=650; // above 2/3 of the 900-byte watermark
    c.frame_tick=8;c.TickFrame();
    assert(c.total_used_memory==650);
    const int count=c.runtime.probes;
    c.runtime.reported=950;
    c.frame_tick=9;c.TickFrame();
    assert(c.runtime.probes==count+1);
    assert(c.total_used_memory==950 && c.collections==1);
    c.runtime.reported=120;
    c.frame_tick=10;c.TickFrame();
    assert(c.total_used_memory==120);
    c.runtime.report=false;
    c.frame_tick=11;c.TickFrame();
    assert(c.total_used_memory==120);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++ compiler needed"
with tempfile.TemporaryDirectory(prefix="eden-f07-gpu-budget-") as dir:
    source=Path(dir)/"memory.cpp";source.write_text(cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            out=Path(dir)/(("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror","-fsanitize=undefined",
                 "-fno-sanitize-recover=all",*(['-DPS5_NATIVE=1'] if native else []),str(source),"-o",str(out)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-3200:])
            ran=subprocess.run([str(out)],capture_output=True,text=True,timeout=10)
            assert ran.returncode==0,(native,opt,ran.stderr[-3200:])
# Native BufferCache is a separately selected header in the PS5 CMake overlay.
# Check the real source body rather than duplicating the cost guard in Python.
buffer_src=(root/"vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
buffer_method=buffer_src.index("void BufferCache<P>::TickFrame() {")
buffer_budget_begin=buffer_src.index("    // If we can obtain the memory info, use it instead of the estimate.",buffer_method)
buffer_budget_end=buffer_src.index("    ++frame_tick;",buffer_budget_begin)
buffer_selected=buffer_src[buffer_budget_begin:buffer_budget_end]
assert buffer_selected.count("runtime.GetDeviceMemoryUsage();")==2
assert "total_used_memory >= minimum_memory - minimum_memory / 3" in buffer_selected
assert "(frame_tick & 1u) == 0" in buffer_selected
assert 'configure_file("${EDEN_MAINTAINED_BUFFER_PAGES}"' in (root/"headless/CMakeLists.txt").read_text()
assert "assert maintained == expected" in (root/"tools/check-ps5-buffer-pages-r437.py").read_text()
buffer_cpp=r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
struct MockRuntime {
    bool report{true};
    std::size_t reported{100};
    int probes{};
    bool CanReportMemoryUsage() const {return report;}
    std::size_t GetDeviceMemoryUsage(){++probes;return reported;}
};
template<class P>struct BufferCache {
    MockRuntime runtime;
    std::size_t total_used_memory{};
    std::size_t minimum_memory{900};
    std::size_t frame_tick{};
    int collections{};
    void RunGarbageCollector(){++collections;}
    void CheckBudget(){
"""+buffer_selected+r"""
    }
};
struct Mock{};
int main(){
    BufferCache<Mock> b;
    for(int f=0;f<8;++f){b.frame_tick=f;b.CheckBudget();}
#ifdef PS5_NATIVE
    assert(b.runtime.probes==4);
#else
    assert(b.runtime.probes==8);
#endif
    assert(b.collections==0);
    b.total_used_memory=650;
    b.runtime.reported=650;
    b.frame_tick=8;b.CheckBudget();
    const int count=b.runtime.probes;
    b.runtime.reported=950;
    b.frame_tick=9;b.CheckBudget();
    assert(b.runtime.probes==count+1);
    assert(b.total_used_memory==950 && b.collections==1);
    b.runtime.reported=120;
    b.frame_tick=10;b.CheckBudget();
    assert(b.total_used_memory==120);
    const int sampled=b.runtime.probes;
    b.runtime.report=false;
    b.frame_tick=11;b.CheckBudget();
    assert(b.runtime.probes==sampled);
    assert(b.total_used_memory==120);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-f07-buffer-budget-") as d:
    source=Path(d)/"budget.cpp";source.write_text(buffer_cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            out=Path(d)/(("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror","-fsanitize=undefined",
                 "-fno-sanitize-recover=all",*(['-DPS5_NATIVE=1'] if native else []),str(source),"-o",str(out)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-3200:])
            ran=subprocess.run([str(out)],capture_output=True,text=True,timeout=10)
            assert ran.returncode==0,(native,opt,ran.stderr[-3200:])
print("F07_MEMORY_BUDGET_SAMPLING_PASS native=1 desktop=1 O0=1 O2=1 low_pressure_half=1 high_pressure_every_frame=1 gc=1 buffer_budget=1")

# Source-extracted rolling uniform-cache heuristic (selected maintained header).
history_start=buffer_src.index("    // Calculate hits and shots and move hit bits to the right",buffer_method)
history_end=buffer_src.index("    // If we can obtain the memory info",history_start)
history_selected=buffer_src[history_start:history_end]
assert history_selected.count("std::copy_backward(")==2
assert "std::copy_n(" not in history_selected
history_cpp=r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <numeric>
using u32=std::uint32_t;
static constexpr u32 DEFAULT_SKIP_CACHE_SIZE=16;
struct ChannelState {
    std::array<u32,4> uniform_cache_hits{};
    std::array<u32,4> uniform_cache_shots{};
    u32 uniform_buffer_skip_cache_size{};
};
template<class P>struct History {
    ChannelState* channel_state{};
    void Tick(){
"""+history_selected+r"""
    }
};
struct Mock{};
int main(){
    ChannelState state;
    state.uniform_cache_hits={1,2,3,4};
    state.uniform_cache_shots={5,6,7,8};
    History<Mock> history{&state};
    history.Tick();
    assert((state.uniform_cache_hits==std::array<u32,4>{0,1,2,3}));
    assert((state.uniform_cache_shots==std::array<u32,4>{0,5,6,7}));
    assert(state.uniform_buffer_skip_cache_size==16);
    history.Tick();
    assert((state.uniform_cache_hits==std::array<u32,4>{0,0,1,2}));
    assert((state.uniform_cache_shots==std::array<u32,4>{0,0,5,6}));
    state.uniform_cache_hits={8,8,8,8};
    state.uniform_cache_shots={4,4,4,4};
    history.Tick();
    assert(state.uniform_buffer_skip_cache_size==0);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-f07-buffer-history-") as d:
    src=Path(d)/"history.cpp";src.write_text(history_cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            out=Path(d)/(("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror","-fsanitize=undefined",
                 "-fno-sanitize-recover=all",*(['-DPS5_NATIVE=1'] if native else []),str(src),"-o",str(out)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-3200:])
            ran=subprocess.run([str(out)],capture_output=True,text=True,timeout=10)
            assert ran.returncode==0,(native,opt,ran.stderr[-3200:])
print("F07_UNIFORM_CACHE_ROLLING_WINDOW_PASS O0=1 O2=1 native=1 desktop=1 shifts=2 skip_decision=1")


# The selected native BufferCache GC age must not wrap at launch. The source-
# extracted method is executed in a mocked LRU with both pressure modes.
gc_begin=buffer_src.index("void BufferCache<P>::RunGarbageCollector() {")
gc_end=buffer_src.index("\ntemplate <class P>",gc_begin+1)
gc_method=buffer_src[gc_begin:gc_end]
assert "if (frame_tick < ticks_to_destroy)" in gc_method
assert gc_method.index("if (frame_tick < ticks_to_destroy)") < gc_method.index("ForEachItemBelow(")
gc_cpp=r"""
#include <cassert>
#include <cstdint>
#include <functional>
#include <vector>
using u64=std::uint64_t;
using BufferId=int;
struct LruCache {
    int calls{};
    u64 threshold{};
    template<class Func>void ForEachItemBelow(u64 before,Func func) {
        ++calls;
        threshold=before;
        if (before>0) func(1);
    }
};
template<class P>struct BufferCache {
    u64 frame_tick{},total_used_memory{},critical_memory{100};
    int downloads{},deletions{};
    struct Buffer { int value{}; };
    std::vector<Buffer> slot_buffers{{},{42}};
    LruCache lru_cache{};
    void DownloadBufferMemory(Buffer& buffer){assert(buffer.value==42);++downloads;}
    void DeleteBuffer(BufferId id){assert(id==1);++deletions;}
    void RunGarbageCollector();
};
""" + "template<class P>\n" + gc_method + r"""
struct Mock{};
int main(){
    BufferCache<Mock> b;
    b.total_used_memory=101;
    for(u64 frame:{u64{0},u64{1},u64{59}}){
        b.frame_tick=frame;b.RunGarbageCollector();
    }
#ifdef PS5_NATIVE
    assert(b.lru_cache.calls==0 && b.downloads==0 && b.deletions==0);
#else
    assert(b.lru_cache.calls==3 && b.downloads==3 && b.deletions==3);
#endif
    b.frame_tick=60;b.RunGarbageCollector();
    assert(b.lru_cache.threshold==0);
    b.frame_tick=61;b.RunGarbageCollector();
    assert(b.lru_cache.threshold==1);
    b.total_used_memory=50; // ordinary GC requires 120 frames.
    BufferCache<Mock> low;
    low.total_used_memory=50;
    low.frame_tick=119;low.RunGarbageCollector();
#ifdef PS5_NATIVE
    assert(low.lru_cache.calls==0);
#else
    assert(low.lru_cache.calls==1);
#endif
    low.frame_tick=120;low.RunGarbageCollector();
    assert(low.lru_cache.threshold==0);
    low.frame_tick=121;low.RunGarbageCollector();
    assert(low.lru_cache.threshold==1);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-f07-buffer-gc-age-") as d:
    src=Path(d)/"gc.cpp";src.write_text(gc_cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            out=Path(d)/(("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror","-fsanitize=undefined",
                 "-fno-sanitize-recover=all",*(['-DPS5_NATIVE=1'] if native else []),str(src),"-o",str(out)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-3200:])
            ran=subprocess.run([str(out)],capture_output=True,text=True,timeout=10)
            assert ran.returncode==0,(native,opt,ran.stderr[-3200:])
print("F07_BUFFER_GC_EARLY_AGE_PASS native_no_underflow=1 desktop_original=1 normal=120 high_pressure=60 O0=1 O2=1")


# Compile the selected native ChangeRegister decrement expression with an
# artificially low driver snapshot. Desktop preserves its pinned behavior.
change_start=buffer_src.index("void BufferCache<P>::ChangeRegister(BufferId buffer_id)")
change_end=buffer_src.index("\ntemplate <class P>",change_start+1)
change_method=buffer_src[change_start:change_end]
assert "total_used_memory >= accounted_bytes" in change_method
assert "lru_cache.Free(buffer.getLRUID());" in change_method
dec_start=change_method.index("    } else {\n")
dec_end=change_method.index("        lru_cache.Free(buffer.getLRUID());",dec_start)
decrement=change_method[dec_start:dec_end]
assert decrement.count("#ifdef PS5_NATIVE")==1
decrement_cpp=r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
using u64=std::uint64_t;
namespace Common { constexpr u64 AlignUp(u64 n,u64 block){return (n+block-1)/block*block;} }
struct Usage {
    u64 total_used_memory{};
    void Unregister(std::size_t size, bool insert){
        if(insert){
            total_used_memory+=Common::AlignUp(size,1024);
"""+decrement+r"""
        }
    }
};
int main(){
    Usage u{100};
    u.Unregister(4096,false);
#ifdef PS5_NATIVE
    assert(u.total_used_memory==0);
#else
    assert(u.total_used_memory==u64{100}-u64{4096});
#endif
    u.total_used_memory=10000;
    u.Unregister(4096,false);
    assert(u.total_used_memory==5904);
    u.total_used_memory=4096;
    u.Unregister(4096,false);
    assert(u.total_used_memory==0);
    u.Unregister(0,false);
    assert(u.total_used_memory==0);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-f07-buffer-unregister-") as d:
    src=Path(d)/"budget.cpp";src.write_text(decrement_cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            out=Path(d)/(("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(['-DPS5_NATIVE=1'] if native else []),str(src),"-o",str(out)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-3200:])
            ran=subprocess.run([str(out)],capture_output=True,text=True,timeout=10)
            assert ran.returncode==0,(native,opt,ran.stderr[-3200:])
print("F07_BUFFER_USAGE_UNREGISTER_SATURATED_PASS O0=1 O2=1 native=1 desktop_original=1")


# Source-extracted channel-less frame teardown: native must drain deferred
# staging and advance retirement even after the last guest channel closes.
# Desktop retains its exact historical return semantics.
frame_begin=buffer_src.index("void BufferCache<P>::TickFrame() {")
frame_limit=buffer_src.index("    // Calculate hits and shots and move hit bits to the right",frame_begin)
frame_prelude=buffer_src[frame_begin:frame_limit]
assert "if (!channel_state)" in frame_prelude
assert "#ifdef PS5_NATIVE" in frame_prelude
assert "delayed_destruction_ring.Tick();" in frame_prelude
assert "runtime.FreeDeferredStagingBuffer(buffer);" in frame_prelude
assert "async_buffers_death_ring.clear();" in frame_prelude
assert frame_prelude.count("runtime.TickFrame(slot_buffers);")==2
frame_cpp=r"""
#include <cassert>
#include <cstddef>
#include <vector>
struct Runtime {
    int ticks{},releases{};
    void TickFrame(std::vector<int>&){++ticks;}
    void FreeDeferredStagingBuffer(int& b){assert(b>0);++releases;}
};
struct Ring {int ticks{};void Tick(){++ticks;}};
template<class P>struct BufferCache {
    void* channel_state{};
    Runtime runtime;
    std::vector<int> slot_buffers;
    std::vector<int> async_buffers_death_ring{1,2};
    Ring delayed_destruction_ring;
    std::size_t frame_tick{};
    void TickFrame();
};
"""+"template<class P>\n"+frame_prelude+r"""
}
struct Mock{};
int main(){
    BufferCache<Mock> c;
    c.TickFrame();
#ifdef PS5_NATIVE
    assert(c.runtime.ticks==1 && c.runtime.releases==2);
    assert(c.frame_tick==1 && c.delayed_destruction_ring.ticks==1);
    assert(c.async_buffers_death_ring.empty());
    c.TickFrame();
    assert(c.runtime.ticks==2 && c.runtime.releases==2);
    assert(c.frame_tick==2 && c.delayed_destruction_ring.ticks==2);
#else
    assert(c.runtime.ticks==0 && c.runtime.releases==0);
    assert(c.frame_tick==0 && c.delayed_destruction_ring.ticks==0);
    assert(c.async_buffers_death_ring.size()==2);
#endif
    c.channel_state=&c;
    c.TickFrame();
#ifdef PS5_NATIVE
    assert(c.runtime.ticks==3);
#else
    assert(c.runtime.ticks==1);
#endif
}
"""
with tempfile.TemporaryDirectory(prefix="eden-f07-buffer-no-channel-") as d:
    src=Path(d)/"channel.cpp";src.write_text(frame_cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            out=Path(d)/(("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror","-fsanitize=undefined",
                 "-fno-sanitize-recover=all",*(['-DPS5_NATIVE=1'] if native else []),str(src),"-o",str(out)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-3200:])
            ran=subprocess.run([str(out)],capture_output=True,text=True,timeout=10)
            assert ran.returncode==0,(native,opt,ran.stderr[-3200:])
print("F07_BUFFER_NO_CHANNEL_DEFERRED_RECLAIM_PASS O0=1 O2=1 native=1 desktop_original=1 releases=2")
