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
assert "F07 native memory pressure sampling outside near GC watermark" in generator
assert "total_used_memory >= minimum_memory - minimum_memory / 3" in selected
assert "(frame_tick & 1u) == 0" in selected
assert selected.count("runtime.GetDeviceMemoryUsage();")==2
for flow in (".github/workflows/encore-core-fast-gate.yml", ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-memory-pressure-sampling-host.py" in (root/flow).read_text()
cpp=r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
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
print("F07_MEMORY_BUDGET_SAMPLING_PASS native=1 desktop=1 O0=1 O2=1 low_pressure_half=1 high_pressure_every_frame=1 gc=1")
