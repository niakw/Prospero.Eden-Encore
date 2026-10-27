#!/usr/bin/env python3
"""F07 P0.3: execute native sparse clean render-target preparation at O0/O2.

The extracted C++ path preserves active target order, depth last, and full
clear semantics. An empty target set avoids empty PrepareImageView calls only
on PS5; dirty targets never take the clean path.
"""
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
native=(root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
backports=(root/"vendor/encore-active/eden-backports/src/video_core/texture_cache/texture_cache.h").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
fast=(root/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(root/".github/workflows/encore-core-preflight.yml").read_text()
invocation="python3 -B tools/check-ps5-f07-sparse-render-target-refresh-host.py"
assert invocation in fast and invocation in pre
ast.parse(generator)
assert "F07 sparse clean render-target refresh using active attachment mask" in generator
start="void TextureCache<P>::UpdateRenderTargets(bool is_clear) {"
end="\n    const VideoCommon::RenderTargets previous_render_targets = render_targets;"
def clean(source):
    assert source.count(start)==source.count(end)==1
    section=source[source.index(start):source.index(end,source.index(start))]
    return section[section.index("    if (!flags[Dirty::RenderTargets]) {"):]
original=clean(backports)
updated=clean(native)
assert "std::countr_zero(active_colors)" in updated
assert "std::countr_zero(active_colors)" not in original
assert updated.count("PrepareImageView(color_buffer_id, true, is_clear && IsFullClear(color_buffer_id));")==2
assert updated.count("PrepareImageView(depth_buffer_id, true, is_clear && IsFullClear(depth_buffer_id));")==2
assert updated.count("if (!flags[Dirty::RenderTargets])")==1
assert updated.count("return;")==1
assert "const VideoCommon::RenderTargets previous_render_targets = render_targets;" in native
assert "const bool rescaled = RescaleRenderTargets();" in native
assert "#include <bit>" in native

cpp=r"""
#include <array>
#include <bit>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>
using u32=std::uint32_t;
using ImageViewId=std::uint32_t;
constexpr std::size_t NUM_RT=8;
namespace Dirty { enum {RenderTargets=0}; }
struct RenderTargets {
 std::array<ImageViewId,NUM_RT> color_buffer_ids{};
 ImageViewId depth_buffer_id{};
};
struct GPU {
 struct {std::array<bool,1> flags{};} dirty;
};
struct Fixture {
 GPU gpu{};
 GPU* maxwell3d=&gpu;
 RenderTargets render_targets{};
 u32 rt_active_mask{};
 std::vector<ImageViewId> attempts{};
 std::vector<ImageViewId> prepared{};
 std::vector<ImageViewId> cleared{};
 unsigned full_clear_calls{};
 unsigned dirty_passes{};
 bool IsFullClear(ImageViewId id){++full_clear_calls;return id==25 || id==71;}
 void PrepareImageView(ImageViewId id,bool modified,bool clear) {
  assert(modified);
  attempts.push_back(id);
  if (id) prepared.push_back(id);
  if (clear && id) cleared.push_back(id);
 }
 void Execute(bool is_clear) {
   auto& flags = maxwell3d->dirty.flags;
""" + updated + r"""
   ++dirty_passes;
 }
};
int main(){
 Fixture empty;
 empty.Execute(false);
#ifdef PS5_NATIVE
 assert(empty.attempts.empty());
#else
 assert(empty.attempts.size()==NUM_RT+1);
#endif
 assert(empty.prepared.empty() && empty.full_clear_calls==0);
 empty.Execute(true);
#ifdef PS5_NATIVE
 assert(empty.attempts.empty());
#else
 assert(empty.attempts.size()==2*(NUM_RT+1));
#endif
 assert(empty.full_clear_calls==0);

 Fixture sparse;
 sparse.render_targets.color_buffer_ids[0]=11;
 sparse.render_targets.color_buffer_ids[3]=25;
 sparse.render_targets.color_buffer_ids[7]=37;
 sparse.render_targets.depth_buffer_id=71;
 sparse.rt_active_mask=(1U<<0)|(1U<<3)|(1U<<7)|(1U<<NUM_RT);
 sparse.Execute(true);
 assert((sparse.prepared==std::vector<ImageViewId>{11,25,37,71}));
 assert((sparse.cleared==std::vector<ImageViewId>{25,71}));
 assert(sparse.full_clear_calls==4);
#ifdef PS5_NATIVE
 assert(sparse.attempts.size()==4);
#else
 assert(sparse.attempts.size()==NUM_RT+1);
#endif
 sparse.Execute(false);
 assert(sparse.full_clear_calls==4);
 assert(sparse.prepared.size()==8);
 assert(sparse.cleared.size()==2);

 Fixture colors;
 colors.render_targets.color_buffer_ids[5]=50;
 colors.rt_active_mask=1U<<5;
 colors.Execute(false);
 assert((colors.prepared==std::vector<ImageViewId>{50}));

 Fixture dirty;
 dirty.gpu.dirty.flags[Dirty::RenderTargets]=true;
 dirty.render_targets.color_buffer_ids[0]=1;
 dirty.rt_active_mask=1;
 dirty.Execute(true);
 assert(dirty.dirty_passes==1);
 assert(dirty.prepared.empty() && dirty.attempts.empty());
 assert(dirty.gpu.dirty.flags[Dirty::RenderTargets]);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-rt-sparse-") as folder:
    source=Path(folder)/"rt.cpp"
    source.write_text(cpp)
    for opt in ("-O0","-O2"):
        for native_on in (False,True):
            exe=Path(folder)/("rt"+opt+("ps5" if native_on else "desktop"))
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(["-DPS5_NATIVE=1"] if native_on else []),str(source),"-o",str(exe)]
            build=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
            assert build.returncode==0,(opt,native_on,build.stderr[-5000:])
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            assert run.returncode==0,(opt,native_on,run.stderr[-5000:])
print("F07_SPARSE_RT_REFRESH_PASS empty=1 sparse=1 depth_last=1"
      " clear=1 repeat=1 dirty=1 desktop=1 native_O0_O2=1")
