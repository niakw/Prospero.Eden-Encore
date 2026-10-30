#!/usr/bin/env python3
"""Source-extracted FindImage: native single-scan max and desktop parity."""
from pathlib import Path
import shutil,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
native=(root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
fast=(root/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(root/".github/workflows/encore-core-preflight.yml").read_text()
assert "F07 select native texture-image candidates in one region pass" in gen
assert "python3 -B tools/check-ps5-f07-find-image-single-pass-host.py" in fast and "python3 -B tools/check-ps5-f07-find-image-single-pass-host.py" in pre
start="ImageId TextureCache<P>::FindImage(const ImageInfo& info, GPUVAddr gpu_addr,"
a=native.index(start)
body=native[a:native.index("\ntemplate <class P>",a)]
assert body.count("SelectCandidate(existing_image_id, existing_image);")==2
assert "std::ranges::max_element" in body
assert body.index("return image_id;\n#else")>body.index("ForEachImageInRegion")
cpp=r"""
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <ranges>
#include <vector>
#include <boost/container/small_vector.hpp>
using u64=std::uint64_t;using u32=std::uint32_t;
using GPUVAddr=u64;using DAddr=u64;using ImageId=u32;
enum class ImageType {e2D,Linear};
enum class RelaxedOptions:unsigned {None=0,Size=1,Format=2,ForceBrokenViews=4};
RelaxedOptions operator&(RelaxedOptions a,RelaxedOptions b){
 return static_cast<RelaxedOptions>(static_cast<unsigned>(a)&static_cast<unsigned>(b));
}
bool True(RelaxedOptions v){return v!=RelaxedOptions::None;}
bool False(RelaxedOptions v){return !True(v);}
enum class ImageFlagBits:unsigned {Remapped=1,Strong=2};
struct Flags{
 unsigned bits{};
 Flags operator&(ImageFlagBits b)const{return {bits&static_cast<unsigned>(b)};}
};
bool True(Flags f){return f.bits!=0;}
struct ImageInfo{ImageType type{ImageType::e2D};unsigned pitch{},format{1};};
struct ImageBase{
 ImageInfo info{};GPUVAddr gpu_addr{5};Flags flags{};u64 modification_tick{};
};
struct MockMemory {
 std::optional<DAddr> GpuToCpuAddress(GPUVAddr a){if(!a)return {};return a;}
 std::optional<DAddr> GpuToCpuAddress(GPUVAddr a,size_t){return GpuToCpuAddress(a);}
};
size_t CalculateGuestSizeInBytes(const ImageInfo&){return 8;}
bool IsPitchLinearSameSize(const ImageInfo&,const ImageInfo&,bool){return true;}
bool IsViewCompatible(unsigned a,unsigned b,bool,bool){return a==b;}
bool IsSubresource(const ImageInfo& info,const ImageBase& image,GPUVAddr address,
                   RelaxedOptions options,bool,bool){
 return image.gpu_addr==address &&
  (info.format==image.info.format || True(options&RelaxedOptions::Format));
}
struct MockRuntime{
 bool HasBrokenTextureViewFormats()const{return false;}
 bool HasNativeBgr()const{return false;}
};
template<class P>struct TextureCache {
 MockRuntime runtime{};MockMemory memory{};MockMemory* gpu_memory{&memory};
 std::vector<ImageBase> slot_images{4};
 std::vector<ImageId> visit_order{1,2,3};
 unsigned visits{};
 template<class F>void ForEachImageInRegion(DAddr,std::size_t,F&& f){
  for(auto id:visit_order){++visits;if(f(id,slot_images[id]))break;}
 }
 ImageId FindImage(const ImageInfo&,GPUVAddr,RelaxedOptions);
};
template<class P>
__BODY__
int main(){
 ImageInfo info{};
 {TextureCache<int> c;
  c.slot_images[1].modification_tick=2;
  c.slot_images[2].modification_tick=9;
  c.slot_images[3].modification_tick=9;
  assert(c.FindImage(info,5,RelaxedOptions::Format)==2);
  assert(c.visits==3);}
 {TextureCache<int> c;
  c.slot_images[1].modification_tick=1;
  c.slot_images[2].modification_tick=100;
  assert(c.FindImage(info,5,RelaxedOptions::None)==1);
  assert(c.visits==1);}
 {TextureCache<int> c;
  c.slot_images[1].flags.bits=1;c.slot_images[1].modification_tick=400;
  c.slot_images[2].modification_tick=11;c.slot_images[3].modification_tick=7;
  assert(c.FindImage(info,5,RelaxedOptions::Format)==2);}
 {TextureCache<int> c;
  for(auto id:c.visit_order)c.slot_images[id].gpu_addr=999;
  assert(c.FindImage(info,5,RelaxedOptions::Format)==0);
  assert(c.FindImage(info,0,RelaxedOptions::None)==0);}
 {TextureCache<int> c;
  info.type=ImageType::Linear;
  for(auto id:c.visit_order)c.slot_images[id].info.type=ImageType::Linear;
  c.slot_images[1].modification_tick=3;c.slot_images[2].modification_tick=6;
  c.slot_images[3].modification_tick=5;
  assert(c.FindImage(info,5,RelaxedOptions::Format)==2);}
}
""".replace("__BODY__",body)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-find-image-") as tmp:
 src=Path(tmp)/"find.cpp";src.write_text(cpp)
 for native_on in (False,True):
  for opt in ("-O0","-O2"):
   exe=Path(tmp)/("find"+opt+str(int(native_on)))
   cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
        "-fsanitize=undefined","-fno-sanitize-recover=all",
        *(["-DPS5_NATIVE=1"] if native_on else []),str(src),"-o",str(exe)]
   build=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
   assert build.returncode==0,(native_on,opt,build.stderr[-5000:])
   run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
   assert run.returncode==0,(native_on,opt,run.stderr[-5000:])
print("F07_FIND_IMAGE_SINGLE_SCAN_PASS native=1 desktop=1 ties=1 exact_stop=1 remapped=1 linear=1 O0_O2=1")
print("NO_REAL_PS5_FPS_PROOF")
