#!/usr/bin/env python3
"""Host replay of release glyph signed distance 2D transform with TLS scratch."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/"headless/prosperoeden/pe/gfx/system_fonts.cpp").read_text()
cm=(root/"headless/CMakeLists.txt").read_text()
assert "pe/gfx/system_fonts.cpp" in cm
beg="constexpr float kFar = 1e20f;"
end="\n} // namespace\n\nstd::vector<std::string> system_font_folders()"
assert s.count(beg)==1 and s.count(end)==1
impl=beg+s.split(beg,1)[1].split(end,1)[0]
assert impl.count("thread_local DistanceScratch scratch;")==1
assert impl.count("f.resize(static_cast<std::size_t>(longest));")==1
assert "std::vector<float> f(static_cast<std::size_t>(longest));" not in impl
cpp=r"""
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <thread>
#include <vector>
namespace pe::gfx {
namespace {
""" + impl + r"""
}
void check(int w,int h,int seed) {
 std::vector<float> grid(std::size_t(w*h),kFar);
 for(int y=0;y<h;++y)for(int x=0;x<w;++x)
  if((x*7+y*3+seed)%11==0) grid[std::size_t(y*w+x)]=0;
 auto src=grid;
 distances(grid,w,h);
 for(int y=0;y<h;++y)for(int x=0;x<w;++x) {
  float closest=kFar;
  for(int q=0;q<h;++q)for(int p=0;p<w;++p)
   if(src[std::size_t(q*w+p)]==0)closest=std::min(closest,float((x-p)*(x-p)+(y-q)*(y-q)));
  assert(std::fabs(grid[std::size_t(y*w+x)]-closest)<0.001f || closest==kFar);
 }
}
}
int main(){
 for(int w=1;w<=15;++w)for(int h=1;h<=12;++h)
  pe::gfx::check(w,h,w+h);
 std::thread a([]{for(int i=0;i<50;++i)pe::gfx::check(7+i%6,9+i%5,i);});
 std::thread b([]{for(int i=0;i<50;++i)pe::gfx::check(12+i%4,5+i%7,i+1);});
 a.join();b.join();
}
""";
with tempfile.TemporaryDirectory(prefix="encore-release-sdf-") as d:
 p=Path(d)/"sdf.cpp";p.write_text(cpp)
 for opt in ("-O0","-O2"):
  exe=Path(d)/("sdf"+opt[2:])
  subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror","-pthread",opt,
                  str(p),"-o",str(exe)],check=True,capture_output=True,text=True)
  subprocess.run([str(exe)],check=True,capture_output=True,text=True)
print("ENCORE_RELEASE_FONT_SDF_SCRATCH_PASS source_transform=1 O0=1 O2=1 tls_isolated=1 brute_reference=1")
