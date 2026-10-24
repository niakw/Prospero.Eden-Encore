#!/usr/bin/env python3
"""R315: compile exact patched CheckFeedbackLoop in PS5/upstream modes."""
from pathlib import Path
from urllib.request import urlopen, Request
import hashlib
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pin = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
rels = ["src/video_core/texture_cache/texture_cache_base.h","src/video_core/texture_cache/texture_cache.h"]
shas = ["8a2318cc725ceb1b0ab3547ed4b4d99441709906","640bd38407b772d52701c22b81b3189adb17bed8"]
patches = ["headless/backports/eden-ps5-texture-null-view-remap.patch",
           "headless/backports/eden-ps5-feedback-loop-view-key.patch",
           "headless/backports/eden-ps5-feedback-loop-no-depth-fastpath.patch",
           "headless/backports/eden-ps5-feedback-loop-serial-fastpath.patch"]
apply = (root / "tools/apply-eden-backports.sh").read_text()
for patch in patches:
    assert apply.count('apply_one "$root/' + patch + '"') == 1, patch

with tempfile.TemporaryDirectory(prefix="eden-r315-feedback-view-") as folder:
    directory = Path(folder)
    for rel, sha in zip(rels, shas):
        payload = urlopen(Request(
            f"https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{rel}",
            headers={"User-Agent":"Eden-Encore-R315-pinned-source"}), timeout=25).read(500000)
        computed = hashlib.sha1(b"blob "+str(len(payload)).encode()+b"\0"+payload).hexdigest()
        assert computed == sha, (rel, computed, sha)
        target = directory / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    for patch in patches:
        subprocess.run(["git","apply","--check",str(root/patch)], cwd=directory, check=True, timeout=10)
        subprocess.run(["git","apply",str(root/patch)], cwd=directory, check=True, timeout=10)
    source = (directory/rels[1]).read_text()
    base = (directory/rels[0]).read_text()
    assert "std::vector<ImageViewId> last_feedback_view_ids;" in base
    start=source.index("void TextureCache<P>::CheckFeedbackLoop(")
    end=source.index("\ntemplate <class P>", start)
    fn=source[start:end]
    assert "&& identical_bound_views" in fn
    assert "if (same_feedback_serials && last_feedback_view_ids.size() == views.size())" in fn
    assert fn.index("same_feedback_serials &&") < fn.index("last_feedback_view_ids[i] != views[i].id")
    counter_anchor = "            if (last_feedback_view_ids[i] != views[i].id) {"
    assert fn.count(counter_anchor) == 1
    fn = fn.replace(counter_anchor, "            ++view_key_comparisons;\n" + counter_anchor)
    assert fn.index("if (views.empty())") < fn.index("if ((rt_active_mask & (1u << NUM_RT)) == 0)")
    assert fn.index("if ((rt_active_mask & (1u << NUM_RT)) == 0)") < fn.index("identical_bound_views")
    assert fn.index("last_feedback_view_ids.push_back") < fn.index("if (rt_active_mask == 0)")
    prologue=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>
inline unsigned view_key_comparisons=0;
using u32=std::uint32_t;
using u64=std::uint64_t;
using ImageViewId=int;
using ImageId=int;
constexpr unsigned NUM_RT=8;
struct ImageViewInOut { ImageViewId id{}; };
struct View { ImageId image_id{}; };
struct RenderTargets {std::array<ImageViewId,8> color_buffer_ids{};ImageViewId depth_buffer_id{};};
struct Runtime {int calls=0;void BarrierFeedbackLoop(){++calls;}};
namespace Settings {
struct Toggle {bool GetValue() const {return true;}};
struct Values {Toggle barrier_feedback_loops;};
inline Values values{};
}
struct Dummy {};
template<class P> struct TextureCache {
    Runtime runtime{};
    RenderTargets render_targets{};
    u64 render_targets_serial=1;
    u32 rt_active_mask=1u<<NUM_RT;
    std::array<ImageId,8> rt_image_id{};
    ImageId rt_depth_image_id=77;
    u64 texture_bindings_serial=1,last_feedback_loop_serial=0,last_feedback_texture_serial=0;
    bool last_feedback_loop_result=false;
#ifdef PS5_NATIVE
    std::vector<ImageViewId> last_feedback_view_ids;
#endif
    std::vector<View> slot_image_views=std::vector<View>(40);
    void CheckFeedbackLoop(std::span<const ImageViewInOut> views);
};
"""
    epilogue=r"""
int main() {
#ifdef PS5_NATIVE
    TextureCache<Dummy> generation{};
    generation.render_targets.depth_buffer_id=30;
    generation.slot_image_views[1].image_id=77;
    const ImageViewInOut key_sample[]={{1}};
    generation.CheckFeedbackLoop(key_sample);
    assert(view_key_comparisons==0);
    ++generation.render_targets_serial;
    generation.CheckFeedbackLoop(key_sample);
    assert(view_key_comparisons==0); // RT mismatch skips the old key scan
    ++generation.texture_bindings_serial;
    generation.CheckFeedbackLoop(key_sample);
    assert(view_key_comparisons==0); // TSC mismatch also skips it
    generation.CheckFeedbackLoop(key_sample);
    assert(view_key_comparisons==1); // still verify identical views for reuse
#endif
    TextureCache<Dummy> tc{};
    tc.render_targets.depth_buffer_id=30; // same image via a *different* view
    tc.slot_image_views[1].image_id=77;
    tc.slot_image_views[2].image_id=88;
    const ImageViewInOut samples_depth[]={{1}};
    const ImageViewInOut unrelated[]={{2}};
    tc.CheckFeedbackLoop(samples_depth);
    assert(tc.runtime.calls==1);
    tc.CheckFeedbackLoop(unrelated); // same TIC/TSC base and same RT
#ifdef PS5_NATIVE
    assert(tc.runtime.calls==1); // no stale barrier on unrelated image
    tc.CheckFeedbackLoop(samples_depth);
    assert(tc.runtime.calls==2); // cannot reuse prior false
    tc.CheckFeedbackLoop(samples_depth);
    assert(tc.runtime.calls==3); // valid cached barrier still issued
    tc.CheckFeedbackLoop(std::span<const ImageViewInOut>{});
    assert(tc.runtime.calls==3); // empty image set correctly invalidates
    assert(tc.last_feedback_view_ids.empty());
    tc.CheckFeedbackLoop(std::span<const ImageViewInOut>{});
    assert(tc.runtime.calls==3); // repeated untextured draw stays barrier-free
    tc.CheckFeedbackLoop(samples_depth);
    assert(tc.runtime.calls==4);
    tc.rt_active_mask=0;
    ++tc.render_targets_serial;
    tc.CheckFeedbackLoop(samples_depth);
    assert(tc.runtime.calls==4); // no active render target
    assert(tc.last_feedback_view_ids.empty());
    tc.rt_active_mask=1u; // color-only, no depth; cached false without scanning
    tc.CheckFeedbackLoop(samples_depth);
    assert(tc.runtime.calls==4);
    assert(tc.last_feedback_view_ids.empty());
    tc.rt_active_mask=1u<<NUM_RT; // same view + serial, depth reactivated
    tc.CheckFeedbackLoop(samples_depth);
    assert(tc.runtime.calls==5);
#else
    assert(tc.runtime.calls==2); // reproduce upstream stale true
#endif
}
"""
    cpp=directory/"feedback.cpp"
    cpp.write_text(prologue+"template<class P>\n"+fn+epilogue)
    for label, flags in (("ps5",["-DPS5_NATIVE"]),("upstream",[])):
        binary=directory/label
        subprocess.run(["c++","-std=c++20","-O2","-Wall","-Wextra","-Werror",
                        *flags,str(cpp),"-o",str(binary)], check=True,timeout=30)
        subprocess.run([str(binary)],check=True,timeout=10)
        print("PASS R315 binding-sensitive feedback barrier",label)
print("PASS R315 exact pinned Eden patch replay and PS5 barrier identity regression")
