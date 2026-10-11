#!/usr/bin/env python3
"""R331: exact pinned ReleaseRawImages C++ checks dependent Vulkan view/image destruction order."""
import ast
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

root=Path(__file__).resolve().parents[1]
pin='5f142c7926d0c7fcbbd0ce30794d72f638a43b2a'
rel='src/video_core/renderer_vulkan/present/layer.cpp'
expected_blob='14935f92bb450973e85237fed52f8dea6d172688'
if len(sys.argv)>1:
    raw=(Path(sys.argv[1])/rel).read_bytes()
else:
    with urlopen(Request(f'https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{rel}',
                         headers={'User-Agent':'EdenEncore-R331'}), timeout=35) as response:
        raw=response.read()
blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
assert blob==expected_blob,(blob,expected_blob)
original=raw.decode()
program=ast.parse((root/'tools/prepare-vulkan-port.py').read_text())
calls=[n.value for n in program.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
       and isinstance(n.value.func,ast.Name) and n.value.func.id=='adapt'
       and len(n.value.args)==3 and isinstance(n.value.args[0],ast.Constant)
       and n.value.args[0].value==rel]
assert len(calls)==1
assert ast.literal_eval(calls[0].args[1])=='vulkan_present_layer.cpp'
pairs=ast.literal_eval(calls[0].args[2])
assert len(pairs)==4
patched=original
for before,after in pairs:
    assert patched.count(before)==1,before[:100]
    patched=patched.replace(before,after)

def extract(text):
    start=text.index('void Layer::ReleaseRawImages() {')
    end=text.index('u64 Layer::CalculateBufferSize(',start)
    return text[start:end]
assert extract(original).count('raw_images.clear();')==1
assert 'raw_image_views.clear();' not in extract(original)
assert extract(patched).index('raw_image_views.clear();')<extract(patched).index('raw_images.clear();')
assert extract(patched).index('raw_images.clear();')<extract(patched).index('buffer.reset();')
assert extract(patched).index('scheduler.Wait(tick);')<extract(patched).index('raw_image_views.clear();')

prefix=r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <set>
#include <vector>
using u64=std::uint64_t;
std::set<int> live_images;
std::set<int> live_views;
int hazards{}, waits{}, buffer_resets{};
struct Scheduler { void Wait(u64 tick) { assert(tick);++waits; } };
struct Image {
    int id{};
    explicit Image(int i):id(i){assert(live_images.insert(id).second);}
    Image(Image&& other) noexcept:id(other.id){other.id=0;}
    Image(const Image&)=delete;
    ~Image(){if(id){if(live_views.count(id)) ++hazards;live_images.erase(id);}}
};
struct ImageView {
    int image_id{};
    explicit ImageView(int i):image_id(i){assert(live_images.count(i));assert(live_views.insert(i).second);}
    ImageView(ImageView&& other) noexcept:image_id(other.image_id){other.image_id=0;}
    ImageView(const ImageView&)=delete;
    ~ImageView(){if(image_id){live_views.erase(image_id);}}
};
struct Buffer { void reset() {++buffer_resets;} };
struct Layer {
    Scheduler scheduler;
    std::vector<u64> resource_ticks{1,2,3};
    std::vector<Image> raw_images;
    std::vector<ImageView> raw_image_views;
    Buffer buffer;
    void ReleaseRawImages();
};
'''
suffix=r'''
int main(){
    Layer layer;
    layer.raw_images.reserve(3);
    layer.raw_image_views.reserve(3);
    for(int id=1;id<=3;++id){
        layer.raw_images.emplace_back(id);
        layer.raw_image_views.emplace_back(id);
    }
    layer.ReleaseRawImages();
    assert(hazards==0); // Unfixed pinned code fails here (image freed with live image view).
    assert(live_images.empty() && live_views.empty());
    assert(waits==3 && buffer_resets==1);
    layer.ReleaseRawImages(); // Safe on empty state and repeated shutdown.
    assert(hazards==0 && buffer_resets==2);
    std::puts("PASS R331 exact Vulkan layer: image views die before backing images");
}
'''
def compile_run(name,body,should_pass):
    with tempfile.TemporaryDirectory(prefix='eden-r331-view-') as td:
        d=Path(td);src=d/'test.cpp';exe=d/'test';src.write_text(prefix+body+suffix)
        env=os.environ.copy()
        if sys.platform=='darwin' and not env.get('SDKROOT'):
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
            if sdk.is_dir():env['SDKROOT']=str(sdk)
        subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror',str(src),'-o',str(exe)],
                       check=True,env=env,timeout=45)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
        if should_pass:
            assert result.returncode==0,(name,result.returncode,result.stderr)
            print(name,result.stdout.strip())
        else:
            assert result.returncode!=0,(name,'original unexpectedly passed')
            print(name,'EXPECTED FAILURE - freed VkImage before live VkImageView')
compile_run('R331 corrected:',extract(patched),True)
compile_run('Pinned original:',extract(original),False)
