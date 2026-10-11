#!/usr/bin/env python3
"""R324 verify exact pinned Fermi2D Bilinear implementation with non-square textures."""
from pathlib import Path
from urllib.request import urlopen,Request
import hashlib,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
pin="5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"
rel="src/video_core/engines/sw_blitter/blitter.cpp"
sha="8bcc2f7a763c210172edd58b079983e25c046936"
patch=root/"headless/backports/eden-ps5-software-bilinear-source-coordinates.patch"
assert (root/"tools/apply-eden-backports.sh").read_text().count(
 'apply_one "$root/headless/backports/eden-ps5-software-bilinear-source-coordinates.patch"')==1
with tempfile.TemporaryDirectory(prefix="eden-r324-f2d-") as td:
 d=Path(td);p=d/rel;p.parent.mkdir(parents=True)
 with urlopen(Request(f"https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{rel}",
                      headers={"User-Agent":"Eden-R324-pinned"}),timeout=25) as f:
  data=f.read(200000)
 actual=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
 assert actual==sha,(actual,sha)
 p.write_bytes(data)
 subprocess.run(["git","apply","--check",str(patch)],cwd=d,check=True,timeout=10)
 subprocess.run(["git","apply",str(patch)],cwd=d,check=True,timeout=10)
 s=p.read_text();a=s.index("void Bilinear(");b=s.index("\ntemplate <bool unpack>",a)
 fn=s[a:b]
 assert ">> 32" not in fn
 assert "(static_cast<size_t>(in_y) * src_width + static_cast<size_t>(in_x))" in fn
 cpp=d/"bilinear.cpp"
 cpp.write_text(r"""
#include <array>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>
using f32=float;
using u32=std::uint32_t;
constexpr size_t ir_components=4;
""" + fn + r"""
int main(){
 std::array<f32,24> src{};
 for(size_t y=0;y<2;++y)for(size_t x=0;x<3;++x)for(size_t c=0;c<4;++c)
  src[(y*3+x)*4+c]=static_cast<f32>(y*100+x*10+c);
 std::array<f32,24> copy{};
 Bilinear(src,copy,3,2,3,2);
 for(size_t i=0;i<src.size();++i)assert(src[i]==copy[i]);
 std::array<f32,60> scaled{};
 Bilinear(src,scaled,3,2,5,3);
 const auto px=[&](size_t x,size_t y,size_t c){return scaled[(y*5+x)*4+c];};
 for(size_t c=0;c<4;++c){
  assert(std::abs(px(0,0,c)-(0.f+c))<0.001f);
  assert(std::abs(px(1,0,c)-(5.f+c))<0.001f);
  assert(std::abs(px(4,0,c)-(20.f+c))<0.001f);
  assert(std::abs(px(0,1,c)-(50.f+c))<0.001f);
  assert(std::abs(px(2,1,c)-(60.f+c))<0.001f);
  assert(std::abs(px(4,2,c)-(120.f+c))<0.001f);
 }
 std::array<f32,4> single{{7,8,9,10}};
 std::array<f32,48> solid{};
 Bilinear(single,solid,1,1,4,3);
 for(size_t i=0;i<solid.size();++i)assert(solid[i]==single[i%4]);
}
""")
 exe=d/"bilinear"
 subprocess.run(["c++","-std=c++20","-O2","-Wall","-Wextra","-Werror",
                 str(cpp),"-o",str(exe)],check=True,timeout=30)
 subprocess.run([str(exe)],check=True,timeout=10)
print("PASS R324 real Eden bilinear 3x2 identity, 5x3 interpolation, 1x1 border")
