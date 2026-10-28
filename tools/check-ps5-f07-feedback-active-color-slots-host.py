#!/usr/bin/env python3
"""F07 source-extracted PS5 sparse feedback-color alias search parity."""
from pathlib import Path
import shutil, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
s=(root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
start=s.index("void TextureCache<P>::CheckFeedbackLoop(")
end=s.index("\ntemplate <class P>",start+20)
method=s[start:end]
assert method.count("std::countr_zero(color_slots)")==2
assert "F07 enumerate active color slots for feedback view IDs" in gen
assert "F07 enumerate active color slots for feedback image IDs" in gen
assert method.count("color_slots &= color_slots - 1;")==2
assert method.count("#else\n                for (size_t i = 0; i < 8; ++i)")==2
for wf in (".github/workflows/encore-core-fast-gate.yml", ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-feedback-active-color-slots-host.py" in (root/wf).read_text()

cpp=r"""
#include <array>
#include <bit>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>
using u32=std::uint32_t;using u64=std::uint64_t;
using ImageViewId=int;using ImageId=int;
constexpr u32 NUM_RT=8;
struct ImageViewInOut{ImageViewId id{};};
struct ImageView{ImageId image_id{};};
struct RenderTargets{
  std::array<ImageViewId,8> color_buffer_ids{};
  ImageViewId depth_buffer_id{};
};
struct Runtime{unsigned barriers{};void BarrierFeedbackLoop(){++barriers;}};
namespace Settings{
struct Toggle{bool enabled{true};bool GetValue()const{return enabled;}};
struct Values{Toggle barrier_feedback_loops;};
inline Values values{};
}
template<class P>struct TextureCache{
 Runtime runtime{};
 RenderTargets render_targets{};
 u64 render_targets_serial{1},texture_bindings_serial{1};
 u64 last_feedback_loop_serial{},last_feedback_texture_serial{};
 bool last_feedback_loop_result{};
 u32 rt_active_mask{1u<<NUM_RT};
 std::array<ImageId,8> rt_image_id{};
 ImageId rt_depth_image_id{77};
 std::vector<ImageView> slot_image_views=std::vector<ImageView>(64);
#ifdef PS5_NATIVE
 std::vector<ImageViewId> last_feedback_view_ids;
#endif
 void CheckFeedbackLoop(std::span<const ImageViewInOut> views);
};
struct Policy{};
template<class P>
""" + method + r"""
int main(){
 const ImageViewInOut depth_alias[]={{1}};
 const ImageViewInOut no_alias[]={{4}};
 const ImageViewInOut exact_depth_view[]={{2}};
 const ImageViewInOut null_view[]={{0}};
 for(u32 mask=0;mask<256;++mask){
   TextureCache<Policy> c{};
   c.rt_active_mask=(1u<<NUM_RT)|mask;
   c.render_targets.depth_buffer_id=2;
   c.slot_image_views[1].image_id=77;
   c.slot_image_views[4].image_id=88;
   for(u32 i=0;i<8;++i){
     c.render_targets.color_buffer_ids[i]=static_cast<int>(10+i);
     c.rt_image_id[i]=static_cast<int>(20+i);
   }
   c.CheckFeedbackLoop(depth_alias);
   assert(c.runtime.barriers==1);
   TextureCache<Policy> exact{};
   exact.rt_active_mask=(1u<<NUM_RT)|mask;
   exact.render_targets.depth_buffer_id=2;
   exact.slot_image_views[2].image_id=77;
   exact.CheckFeedbackLoop(exact_depth_view);
   assert(exact.runtime.barriers==0);
   TextureCache<Policy> unrelated{};
   unrelated.rt_active_mask=(1u<<NUM_RT)|mask;
   unrelated.slot_image_views[4].image_id=88;
   unrelated.CheckFeedbackLoop(no_alias);
   assert(unrelated.runtime.barriers==0);
   TextureCache<Policy> view_collision{};
   view_collision.rt_active_mask=(1u<<NUM_RT)|mask;
   view_collision.slot_image_views[1].image_id=77;
   view_collision.render_targets.color_buffer_ids[6]=1;
   view_collision.CheckFeedbackLoop(depth_alias);
   assert(view_collision.runtime.barriers==((mask & (1u<<6)) ? 0u:1u));
   TextureCache<Policy> image_collision{};
   image_collision.rt_active_mask=(1u<<NUM_RT)|mask;
   image_collision.slot_image_views[1].image_id=77;
   image_collision.rt_image_id[3]=77;
   image_collision.CheckFeedbackLoop(depth_alias);
   assert(image_collision.runtime.barriers==((mask & (1u<<3)) ? 0u:1u));
 }
 TextureCache<Policy> empty{};
 empty.CheckFeedbackLoop(null_view);
 assert(empty.runtime.barriers==0);
 TextureCache<Policy> color_only{};
 color_only.rt_active_mask=0xff;
 color_only.slot_image_views[1].image_id=77;
 color_only.CheckFeedbackLoop(depth_alias);
 assert(color_only.runtime.barriers==0);
 Settings::values.barrier_feedback_loops.enabled=false;
 TextureCache<Policy> disabled{};
 disabled.CheckFeedbackLoop(depth_alias);
 assert(disabled.runtime.barriers==0);
}
""";
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-active-color-feedback-") as td:
    source=Path(td)/"feedback.cpp";source.write_text(cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            exe=Path(td)/(("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(['-DPS5_NATIVE=1'] if native else []),
                 str(source),"-o",str(exe)]
            build=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
            assert build.returncode==0,(native,opt,build.stderr[-4000:])
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-4000:])
print("F07_ACTIVE_COLOR_FEEDBACK_PASS native_desktop_O0_O2 masks=256 depth=1 color_view_alias=1 color_image_alias=1 disabled=1")
