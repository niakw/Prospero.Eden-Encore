#!/usr/bin/env python3
"""Execute source-extracted native FillImageViews under O0/O2 and UBSan."""
from pathlib import Path
import shutil, subprocess, tempfile, ast
root=Path(__file__).resolve().parents[1]
native=(root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
pinned=(root/"vendor/sources/eden/src/video_core/texture_cache/texture_cache.h").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
pre=(root/".github/workflows/encore-core-preflight.yml").read_text()
fast=(root/".github/workflows/encore-core-fast-gate.yml").read_text()
call="python3 -B tools/check-ps5-f07-nonadjacent-tic-memo-host.py"
assert call in fast and call in pre
assert "F07 bounded per-draw nonadjacent TIC memo and generator parity" in gen
ast.parse(gen)
start="void TextureCache<P>::FillImageViews(std::span<ImageViewInOut> views, bool compute, bool blacklist) {"
end="\ntemplate <class P>\nvoid TextureCache<P>::CheckFeedbackLoop("
def method(s):
 assert s.count(start)==s.count(end)==1
 return s[s.index(start):s.index(end,s.index(start))]
source=method(native)
baseline=method(pinned)
assert "view_memo" not in baseline
assert source.count("view_memo[view.index & 15U]")==2
assert source.count("std::array<ViewMemo, 16> view_memo{}")==1
assert "previous_view_id" not in source
assert source.index("!blacklist && !has_deleted_images")<source.index("VisitImageView(view.index, compute)")
assert source.count("cached.id != NULL_IMAGE_VIEW_ID")==1
code=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <span>
using u32=std::uint32_t; using ImageViewId=std::size_t;
constexpr ImageViewId NULL_IMAGE_VIEW_ID=0;
struct ImageViewInOut {u32 index{};bool blacklist{};ImageViewId id{};};
struct ImageViewBase {std::size_t image_id{};};
struct Image {bool down{};u32 scale_rating{3};};
template<class P>struct TextureCache {
 bool has_deleted_images{}, delete_nine{};
 std::array<unsigned,64> visits{};unsigned total{},scales{};
 std::array<ImageViewBase,64> slot_image_views{};
 std::array<Image,64> slot_images{};
 ImageViewId VisitImageView(u32 idx,bool) {
  assert(idx<63);++visits[idx];++total;
  if(idx==9 && delete_nine){delete_nine=false;has_deleted_images=true;}
  return idx==7 ? NULL_IMAGE_VIEW_ID : idx+1;
 }
 bool ScaleDown(Image& i){++scales;if(i.down)return false;i.down=true;return true;}
 void FillImageViews(std::span<ImageViewInOut>,bool,bool);
};
""" + "template<class P>\n" + source + r"""
int main(){
 using V=ImageViewInOut;
 {TextureCache<int> c;std::array<V,3> a{V{1},V{2},V{1}};
 c.FillImageViews(a,false,false);
 #ifdef PS5_NATIVE
 assert(c.total==2 && c.visits[1]==1);
 #else
 assert(c.total==3 && c.visits[1]==2);
 #endif
 assert(a[0].id==a[2].id);
 c.FillImageViews(a,false,false);
 #ifdef PS5_NATIVE
 assert(c.total==4);
 #else
 assert(c.total==6);
 #endif
 }
 {TextureCache<int> c;std::array<V,3> a{V{1},V{17},V{1}};
 c.FillImageViews(a,false,false);assert(c.total==3);}
 {TextureCache<int> c;std::array<V,3> a{V{7},V{7},V{7}};
 c.FillImageViews(a,true,false);assert(c.total==3 && a[0].id==0);}
 {TextureCache<int> c;c.delete_nine=true;std::array<V,3> a{V{5},V{9},V{5}};
 c.FillImageViews(a,false,false);
 #ifdef PS5_NATIVE
 assert(c.total==5 && c.visits[5]==3 && c.visits[9]==2);
 #else
 assert(c.total==6);
 #endif
 }
 {TextureCache<int> c;c.slot_image_views[4].image_id=4;
 std::array<V,3> a{V{3,true},V{2},V{3,true}};
 c.FillImageViews(a,false,true);
 assert(c.total==6 && c.scales==4 && c.slot_images[4].scale_rating==0);}
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-tic-reuse-") as tmp:
 src=Path(tmp)/"tic.cpp";src.write_text(code)
 for opt in ("-O0","-O2"):
  for native_on in (False,True):
   binary=Path(tmp)/("tic"+opt[1:]+("ps5" if native_on else "desktop"))
   cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
        "-fsanitize=undefined","-fno-sanitize-recover=all",
        *(["-DPS5_NATIVE=1"] if native_on else []),str(src),"-o",str(binary)]
   p=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
   assert p.returncode==0,(cmd,p.stderr[-5000:])
   p=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20)
   assert p.returncode==0,(opt,native_on,p.stdout,p.stderr[-5000:])
print("F07_NONADJACENT_TIC_MEMO_PASS duplicate=1 collisions=1 null=1 deletion=1 blacklist=1 desktop=1 O0_O2=1")
