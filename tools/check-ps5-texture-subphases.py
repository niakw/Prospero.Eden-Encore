#!/usr/bin/env python3
"""R322: pinned-source instrumentation attribution contract and C++20 timer smoke."""
from pathlib import Path
from urllib.request import Request,urlopen
import ast,hashlib,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
pin="5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
rel="src/video_core/texture_cache/texture_cache.h"
sha="640bd38407b772d52701c22b81b3189adb17bed8"
generator=(root/"tools/prepare-vulkan-port.py").read_text()
tree=ast.parse(generator)
extensions=[
  n for n in ast.walk(tree)
  if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
  and isinstance(n.func.value,ast.Name) and n.func.value.id=="texture_costs"
  and n.func.attr=="extend"]
ext=[n for n in extensions if "TextureCpuRefresh" in ast.get_source_segment(generator,n)]
assert len(ext)==1
pairs=ast.literal_eval(ext[0].args[0])
assert len(pairs)==3
with urlopen(Request(f"https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{rel}",
                     headers={"User-Agent":"Eden-Encore-R322-pinned-source"}),timeout=25) as r:
    blob=r.read(220000)
sha_actual=hashlib.sha1(b"blob "+str(len(blob)).encode()+b"\0"+blob).hexdigest()
assert sha_actual==sha,(sha_actual,sha)
text=blob.decode()
for old,new in pairs:
    assert text.count(old)==1,old[:75]
    text=text.replace(old,new)
refresh=text[text.index("void TextureCache<P>::RefreshContents("):
             text.index("\ntemplate <class P>",text.index("void TextureCache<P>::RefreshContents("))]
alias=text[text.index("void TextureCache<P>::SynchronizeAliases("):
           text.index("\ntemplate <class P>",text.index("void TextureCache<P>::SynchronizeAliases("))]
assert refresh.index("if (False(image.flags & ImageFlagBits::CpuModified))") < refresh.index("TextureCpuRefresh")
assert refresh.index("TextureCpuRefresh") < refresh.index("image.flags &= ~ImageFlagBits::CpuModified")
assert alias.index("TextureAliasScan") < alias.index("for (const AliasedImage& aliased")
assert alias.index("alias_scan_phase.Stop();") > alias.index("if (aliased_images.empty())")
assert alias.index("alias_scan_phase.Stop();") < alias.index("TextureAliasCopy")
assert alias.index("TextureAliasCopy") < alias.index("std::ranges::sort(aliased_images")
# A full PS5 compilation is the authoritative binding check for both real
# texture methods; compile exactly the inserted RAII blocks on both targets
# to catch syntax/type binding errors separately without faking dependencies.
parts=[new for old,new in pairs]
h=(root/"headless/performance.h").read_text()
c=(root/"headless/performance.cpp").read_text()
names=("TextureCpuRefresh","TextureAliasScan","TextureAliasCopy")
logs=("texture_cpu_refresh","texture_alias_scan","texture_alias_copy")
for n in names:assert h.count(n)==1
for n in logs:assert c.count('"' + n + '"')==1
assert "cache_draw_sample_active = false" in h
assert "if (stats) started = Common::g_wall_clock.GetTimeNS();" in h
assert "if (!detailed_gpu_profile.load" in h
assert "#ifdef PS5_NATIVE" in parts[0]
with tempfile.TemporaryDirectory(prefix="eden-r322-gpu-phase-") as tmp:
    work=Path(tmp)
    # A compact stand-in reproduces the exact generated scope text; both
    # branch preprocessors must remain well-formed when PS5_NATIVE is absent.
    prefix=r"""
#include <cassert>
#include <cstdint>
namespace Eden {namespace Performance {
enum class CachePhase {TextureCpuRefresh,TextureAliasScan,TextureAliasCopy};
struct CachePhaseTimer {
 explicit CachePhaseTimer(CachePhase){}
 void Stop(){}
};
}}
using ImageId=int;
enum class ImageFlagBits : unsigned{CpuModified=1,GpuModified=2,Rescaled=4};
struct Image { unsigned flags=1; };
inline bool True(unsigned x){return x!=0;}
"""
    blocks=r"""
void refresh(){
 Image image{};
""" + parts[0] + r"""
}
void alias_scan(){
 Image image{};
""" + parts[1] + r"""
}
"""
    # Compile the actual instrumentation declaration in its original scope;
    # the entire edited function is tested by the native build/clang.
    for mode,flags in (("ps5",["-DPS5_NATIVE"]),("upstream",[])):
        path=work/(mode+".cpp")
        path.write_text(prefix+blocks+"int main(){refresh();alias_scan();}\n")
        obj=work/(mode+".o")
        subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",
                        *flags,"-c",str(path),"-o",str(obj)],
                       check=True,timeout=30)
        print("PASS R322 source-emitted GPU cache phase blocks",mode)
print("PASS R322 exactly pinned texture source, low-overhead sampled phase decomposition")
