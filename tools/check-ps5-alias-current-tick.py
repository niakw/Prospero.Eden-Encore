#!/usr/bin/env python3
"""R321: exact pinned alias synchronizer replay, PS5/upstream C++ behavioral regression."""
from pathlib import Path
from urllib.request import Request,urlopen
import subprocess,hashlib,tempfile
root=Path(__file__).resolve().parents[1]
pin="5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
rel="src/video_core/texture_cache/texture_cache.h"
sha="640bd38407b772d52701c22b81b3189adb17bed8"
patch_rel="headless/backports/eden-ps5-alias-current-tick-fastpath.patch"
apply=(root/"tools/apply-eden-backports.sh").read_text()
assert apply.count('apply_one "$root/'+patch_rel+'"')==1
with tempfile.TemporaryDirectory(prefix="eden-r321-alias-tick-") as tmp:
    d=Path(tmp)
    p=d/rel
    p.parent.mkdir(parents=True)
    with urlopen(Request(f"https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{rel}",
                         headers={"User-Agent":"Eden-Encore-R321-pinned-source"}),timeout=25) as r:
        blob=r.read(220000)
    actual=hashlib.sha1(b"blob "+str(len(blob)).encode()+b"\0"+blob).hexdigest()
    assert actual==sha,(actual,sha)
    p.write_bytes(blob)
    patch=root/patch_rel
    subprocess.run(["git","apply","--check",str(patch)],cwd=d,check=True,timeout=10)
    subprocess.run(["git","apply",str(patch)],cwd=d,check=True,timeout=10)
    s=p.read_text()
    a=s.index("void TextureCache<P>::SynchronizeAliases(")
    b=s.index("\ntemplate <class P>",a)
    body=s[a:b]
    assert body.index("if (image.modification_tick == modification_tick)") < body.index("for (const AliasedImage& aliased")
    assert body.index("if (image.modification_tick == modification_tick)") < body.index("boost::container::small_vector<const AliasedImage*, 8> aliased_images;")
    assert body.index("boost::container::small_vector<const AliasedImage*, 8> aliased_images;") < body.index("for (const AliasedImage& aliased")
    native=(root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
    generator=(root/"tools/prepare-vulkan-port.py").read_text()
    assert "F07 skip singleton native alias sort while preserving multi-alias order" in generator
    native_body=native[native.index("void TextureCache<P>::SynchronizeAliases("):]
    native_body=native_body[:native_body.index("\ntemplate <class P>")]
    sort_guard="#ifdef PS5_NATIVE\n    // Most alias refreshes have only one newer source."
    assert native_body.count(sort_guard)==1
    assert native_body.index("if (aliased_images.size() > 1)") < native_body.index("std::ranges::sort(aliased_images,")
    assert native_body.index("std::ranges::sort(aliased_images,") < native_body.index("for (const AliasedImage* const aliased")
    cpp=d/"alias.cpp"
    cpp.write_text(r"""
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <ranges>
#include <vector>
#include <boost/container/small_vector.hpp>
using u64=std::uint64_t;
using ImageId=int;
enum class ImageFlagBits : unsigned { Rescaled=1u, GpuModified=2u };
struct Flags {
 unsigned bits{};
 Flags operator&(ImageFlagBits bit) const {return Flags{bits&static_cast<unsigned>(bit)};}
 Flags& operator|=(ImageFlagBits bit) {bits|=static_cast<unsigned>(bit);return *this;}
};
inline bool True(Flags v){return v.bits!=0;}
struct AliasedImage { ImageId id{}; std::vector<int> copies{}; };
struct ImageBase {
 Flags flags{};
 u64 modification_tick{};
 std::vector<AliasedImage> aliased_images{};
};
using Image=ImageBase;
struct ResolutionInfo {bool active{};};
namespace Settings {
 struct Values {ResolutionInfo resolution_info{};};
 inline Values values{};
}
struct Dummy {};
template<class P> struct TextureCache {
 std::vector<Image> slot_images{3};
 u64 modification_tick{};
 int copies=0,upscales=0,downscales=0;
 bool ImageCanRescale(Image&) {return true;}
 void ScaleUp(Image&){++upscales;}
 void ScaleDown(Image&){++downscales;}
 void CopyImage(ImageId,ImageId,std::vector<int>){++copies;}
 void SynchronizeAliases(ImageId);
};
template<class P>
"""+body+r"""
int main() {
 TextureCache<Dummy> c;
 c.modification_tick=7;
 c.slot_images[0].aliased_images.push_back({1,{1}});
 c.slot_images[0].modification_tick=7;
 c.slot_images[1].modification_tick=7;
 c.SynchronizeAliases(0);
 assert(c.copies==0); // own latest tick means no newer alias
 // A strictly newer alias must still be synchronized exactly once.
 c.modification_tick=8;
 c.slot_images[1].modification_tick=8;
 c.slot_images[1].flags |= ImageFlagBits::GpuModified;
 c.SynchronizeAliases(0);
 assert(c.copies==1 && c.slot_images[0].modification_tick==8);
 c.SynchronizeAliases(0);
 assert(c.copies==1);
 // Even with a new unrelated write, an alias with an old tick stays untouched.
 c.modification_tick=9;
 c.SynchronizeAliases(0);
 assert(c.copies==1);
}
""")
    for name,flags in (("ps5",["-DPS5_NATIVE"]),("upstream",[])):
        exe=d/name
        subprocess.run(["c++","-std=c++20","-O2","-Wall","-Wextra","-Werror",
                        *flags,str(cpp),"-o",str(exe)],check=True,timeout=30)
        subprocess.run([str(exe)],check=True,timeout=10)
        print("PASS R321 pinned real SynchronizeAliases",name)
    # Exercise the selected active F07 implementation, including native-only
    # singleton fast-path and ordered multi-alias uploads at -O0 and -O2.
    native_fixture=cpp.read_text().replace(body,native_body)
    assert native_fixture != cpp.read_text()
    native_fixture=native_fixture.replace(
        "using u64=std::uint64_t;",
        "namespace Eden::Performance { "
        "enum class CachePhase { TextureAliasScan, TextureAliasCopy }; "
        "struct CachePhaseTimer { explicit CachePhaseTimer(CachePhase) {} "
        "void Stop() {} }; }\nusing u64=std::uint64_t;"
    )
    # A second source modified in the opposite order must be copied first
    # only after the sort has restored increasing modification ticks.
    native_fixture=native_fixture.replace(
        "int copies=0,upscales=0,downscales=0;",
        "int copies=0,upscales=0,downscales=0; std::vector<int> copy_order{};"
    ).replace(
        "void CopyImage(ImageId,ImageId,std::vector<int>){++copies;}",
        "void CopyImage(ImageId,ImageId id,std::vector<int>){++copies;copy_order.push_back(id);}"
    )
    native_fixture=native_fixture.replace(
        " c.SynchronizeAliases(0);\n assert(c.copies==1);\n}",
        " c.SynchronizeAliases(0);\n assert(c.copies==1);\n"
        " TextureCache<Dummy> two;\n two.modification_tick=11;\n"
        " two.slot_images[0].modification_tick=1;\n"
        " two.slot_images[0].aliased_images.push_back({2,{2}});\n"
        " two.slot_images[0].aliased_images.push_back({1,{1}});\n"
        " two.slot_images[1].modification_tick=9;\n"
        " two.slot_images[2].modification_tick=10;\n"
        " two.SynchronizeAliases(0);\n"
        " assert(two.copy_order.size()==2 && two.copy_order[0]==1 && two.copy_order[1]==2);\n}"
    )
    assert "assert(two.copy_order.size()==2" in native_fixture
    native_cpp=d/"active-alias.cpp"
    native_cpp.write_text(native_fixture)
    for name,flags in (("ps5",["-DPS5_NATIVE"]),("desktop",[])):
        for opt in ("-O0","-O2"):
            exe=d/("active-"+name+opt[2:])
            subprocess.run(["c++","-std=c++20",opt,"-Wall","-Wextra","-Werror",
                            *flags,str(native_cpp),"-o",str(exe)],check=True,timeout=40)
            subprocess.run([str(exe)],check=True,timeout=10)
            print("PASS F07 source-extracted singleton + ordered aliases",name,opt)
print("PASS R321 monotonic alias tick source patch and regression")
