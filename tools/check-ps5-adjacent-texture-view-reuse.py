#!/usr/bin/env python3
"""R320 exact pinned Eden FillImageViews PS5/upstream C++ regression."""
from pathlib import Path
from urllib.request import urlopen, Request
import hashlib,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
pin="5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
rel="src/video_core/texture_cache/texture_cache.h"
sha="640bd38407b772d52701c22b81b3189adb17bed8"
patch_rel="headless/backports/eden-ps5-adjacent-valid-view-reuse.patch"
assert (root/"tools/apply-eden-backports.sh").read_text().count('apply_one "$root/'+patch_rel+'"')==1
with tempfile.TemporaryDirectory(prefix="eden-r320-tic-") as d:
    w=Path(d)
    p=w/rel
    p.parent.mkdir(parents=True)
    with urlopen(Request(f"https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{rel}",
                         headers={"User-Agent":"Eden-Encore-R320-pinned-source"}),timeout=25) as src:
        blob=src.read(220000)
    actual=hashlib.sha1(b"blob "+str(len(blob)).encode()+b"\0"+blob).hexdigest()
    assert actual==sha,(actual,sha)
    p.write_bytes(blob)
    patch=root/patch_rel
    subprocess.run(["git","apply","--check",str(patch)],cwd=w,check=True,timeout=10)
    subprocess.run(["git","apply",str(patch)],cwd=w,check=True,timeout=10)
    source=p.read_text()
    a=source.index("void TextureCache<P>::FillImageViews(")
    b=source.index("\ntemplate <class P>",a)
    fn=source[a:b]
    assert fn.count("#ifdef PS5_NATIVE")==3
    cpp=w/"texture.cpp"
    cpp.write_text(r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <span>
using u32=std::uint32_t;
using ImageViewId=int;
constexpr ImageViewId NULL_IMAGE_VIEW_ID=0;
struct ImageViewInOut {u32 index{};bool blacklist{};ImageViewId id{};};
struct ImageViewBase {int image_id{};};
struct Image {int scale_rating{};};
struct Dummy {};
template<class P> struct TextureCache {
 bool has_deleted_images=false;
 std::array<ImageViewBase,20> slot_image_views{};
 std::array<Image,20> slot_images{};
 int visits=0,scales=0,deletes_remaining=0,null_first=0;
 ImageViewId VisitImageView(u32 index,bool) {
  ++visits;
  if(deletes_remaining>0){--deletes_remaining;has_deleted_images=true;}
  if(index==9&&null_first>0){--null_first;return NULL_IMAGE_VIEW_ID;}
  return static_cast<ImageViewId>(index);
 }
 bool ScaleDown(Image&){++scales;return false;}
 void FillImageViews(std::span<ImageViewInOut>,bool,bool);
};
template<class P>
""" + fn + r"""
int main(){
 TextureCache<Dummy> t;
 std::array<ImageViewInOut,6> read{{{3},{3},{4},{4},{3},{3}}};
 t.FillImageViews(read,false,false);
#ifdef PS5_NATIVE
 assert(t.visits==4);
#else
 assert(t.visits==6);
#endif
 for(const auto& v:read)assert(v.id==static_cast<ImageViewId>(v.index));
 t.visits=0;t.null_first=1;
 std::array<ImageViewInOut,2> nulls{{{9},{9}}};
 t.FillImageViews(nulls,false,false);
 assert(t.visits==2&&nulls[0].id==0&&nulls[1].id==9);
 t.visits=0;t.scales=0;
 std::array<ImageViewInOut,2> blacklisted{{{3,true},{3,true}}};
 t.FillImageViews(blacklisted,false,true);
 assert(t.visits==2&&t.scales==2);
 t.visits=0;t.deletes_remaining=1;
 std::array<ImageViewInOut,2> invalidated{{{3},{3}}};
 t.FillImageViews(invalidated,false,false);
#ifdef PS5_NATIVE
 assert(t.visits==3);
#else
 assert(t.visits==4);
#endif
}
""")
    for label,flags in (("ps5",["-DPS5_NATIVE"]),("upstream",[])):
        binary=w/label
        subprocess.run(["c++","-std=c++20","-O2","-Wall","-Wextra","-Werror",
                        *flags,str(cpp),"-o",str(binary)],check=True,timeout=30)
        subprocess.run([str(binary)],check=True,timeout=10)
        print("PASS R320 original FillImageViews",label)
print("PASS R320 exact pinned source and duplicate texture preparation regression")
