#!/usr/bin/env python3
"""R336: PS5 Vulkan presenter/render metadata source-race regression gate."""
from pathlib import Path
import ast
import os
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
PIN='5f142c7926d0c7fcbbd0ce30794d72f638a43b2a'
files={
  'src/video_core/renderer_vulkan/vk_present_manager.h': 'include/video_core/renderer_vulkan/vk_present_manager.h',
  'src/video_core/renderer_vulkan/vk_present_manager.cpp': 'vulkan_present_manager.cpp',
  'src/video_core/renderer_vulkan/renderer_vulkan.cpp': 'vulkan_renderer.cpp',
}
tree=ast.parse((ROOT/'tools/prepare-vulkan-port.py').read_text())
calls=[node.value for node in tree.body if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call)
       and isinstance(node.value.func,ast.Name) and node.value.func.id=='adapt']
generated={}
original={}
for path,target in files.items():
    if len(sys.argv)>1:
        blob=(Path(sys.argv[1])/path).read_bytes()
    else:
        req=Request(f'https://raw.githubusercontent.com/eden-emulator/mirror/{PIN}/{path}',
                    headers={'User-Agent':'EdenEncore-R336'})
        with urlopen(req,timeout=40) as stream:blob=stream.read()
    original[path]=blob.decode()
    related=[node for node in calls if len(node.args)==3 and isinstance(node.args[0],ast.Constant)
             and node.args[0].value==path]
    assert len(related)==1,path
    assert ast.literal_eval(related[0].args[1])==target
    def patch_literal(node):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return patch_literal(node.left) + patch_literal(node.right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'read_text':
            target=node.func.value
            assert isinstance(target, ast.BinOp) and isinstance(target.op, ast.Div)
            assert isinstance(target.left, ast.Name) and target.left.id in {'port', 'vulkan_oracle'}
            path_to_read=ast.literal_eval(target.right)
            base=(ROOT/'headless' if target.left.id == 'port'
                  else ROOT/'vendor/encore-active/eden-vulkan-oracles')
            return (base/path_to_read).read_text()
        return ast.literal_eval(node)
    patches=[(patch_literal(pair.elts[0]),patch_literal(pair.elts[1]))
             for pair in related[0].args[2].elts]
    out=original[path]
    for before,after in patches:
        assert out.count(before)==1,(path,before[:85])
        out=out.replace(before,after)
    generated[path]=out

header=generated['src/video_core/renderer_vulkan/vk_present_manager.h']
present=generated['src/video_core/renderer_vulkan/vk_present_manager.cpp']
render=generated['src/video_core/renderer_vulkan/renderer_vulkan.cpp']
for name,typ in [('image_count','std::size_t'),('swapchain_image_count','std::size_t'),
                 ('swapchain_image_format','VkFormat'),('swapchain_image_view_format','VkFormat')]:
    assert f'std::atomic<{typ}> {name}{{}};' in header
for label,field in [('SwapchainImageCount','swapchain_image_count'),
                     ('SwapchainImageFormat','swapchain_image_format'),
                     ('SwapchainImageViewFormat','swapchain_image_view_format')]:
    assert f'{label}() const {{ return {field}.load(); }}' in header
for field,expr in [('swapchain_image_count','GetImageCount'),
                   ('swapchain_image_format','GetImageFormat'),
                   ('swapchain_image_view_format','GetImageViewFormat')]:
    assert f'{field}.store(swapchain.{expr}());' in present
assert 'render_window.GetFramebufferLayout(), present_manager.SwapchainImageCount(),' in render
assert 'present_manager.SwapchainImageViewFormat(), true);' in render
assert 'frame_gen.Process(device, frame, present_manager.SwapchainImageFormat(),' in render
composite=render[render.index('void RendererVulkan::Composite('):render.index('void RendererVulkan::Report()')]
assert 'swapchain.GetImageCount()' not in composite
assert 'swapchain.GetImageViewFormat()' not in composite
assert 'swapchain.GetImageFormat()' not in composite
loading=(ROOT/'vendor/encore-active/eden-vulkan-oracles/vulkan_loading.inc').read_text()
assert 'present_manager.SwapchainImageCount()' in loading
assert 'present_manager.SwapchainImageViewFormat()' in loading
assert 'swapchain.GetImageCount()' not in loading
assert 'swapchain.GetImageViewFormat()' not in loading
old=original['src/video_core/renderer_vulkan/renderer_vulkan.cpp']
assert 'render_window.GetFramebufferLayout(), swapchain.GetImageCount(),' in old
assert 'frame_gen.Process(device, frame, swapchain.GetImageFormat(),' in old

fixture=r'''
#include <atomic>
#include <cassert>
#include <cstddef>
#include <thread>
#include <vector>
#include <cstdio>
using VkFormat = int;
struct Presenter {
  std::atomic<std::size_t> image_count{3}, swapchain_image_count{3};
  std::atomic<VkFormat> swapchain_image_format{44}, swapchain_image_view_format{44};
  std::size_t SwapchainImageCount() const {return swapchain_image_count.load();}
  VkFormat SwapchainImageFormat() const {return swapchain_image_format.load();}
  VkFormat SwapchainImageViewFormat() const {return swapchain_image_view_format.load();}
  void Recreate(unsigned count, int format) {
    image_count.store(count);
    swapchain_image_count.store(count);
    swapchain_image_format.store(format);
    swapchain_image_view_format.store(format);
  }
};
int main() {
  Presenter p;
  std::thread writer([&]{for(int i=0;i<100000;++i)p.Recreate(i%2?3:4,i%2?44:50);});
  std::thread reader([&]{for(int i=0;i<100000;++i){auto c=p.SwapchainImageCount();auto f=p.SwapchainImageFormat();auto v=p.SwapchainImageViewFormat();assert(c==3 || c==4);assert(f==44 || f==50);assert(v==44 || v==50);}});
  writer.join();reader.join();
  std::puts("R336 PASS: lock-free concurrent swapchain count/format/view-format atomics");
}
'''
with tempfile.TemporaryDirectory(prefix='eden-r336-swapchain-') as d:
    dir=Path(d);(dir/'test.cpp').write_text(fixture)
    env=os.environ.copy()
    if sys.platform=='darwin' and not env.get('SDKROOT'):
        sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
        if sdk.is_dir(): env['SDKROOT']=str(sdk)
    subprocess.run(['c++','-std=c++20','-O2','-pthread','-Wall','-Wextra','-Werror',
                    str(dir/'test.cpp'),'-o',str(dir/'test')],check=True,timeout=30,env=env)
    result=subprocess.run([str(dir/'test')],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    print(result.stdout.strip())
print('R336 PASS: exact pinned generator replay and PS5 render/presenter ownership contract')
