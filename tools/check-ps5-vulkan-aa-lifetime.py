#!/usr/bin/env python3
"""R328: replay the two exact pinned Vulkan Layer AA transitions and C++ mock GPU lifetime."""
import ast
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

root = Path(__file__).resolve().parents[1]
pin = '5f142c7926d0c7fcbbd0ce30794d72f638a43b2a'
rel = 'src/video_core/renderer_vulkan/present/layer.cpp'
sha = '14935f92bb450973e85237fed52f8dea6d172688'
if len(sys.argv) > 1:
    data = (Path(sys.argv[1]) / rel).read_bytes()
else:
    with urlopen(Request(f'https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{rel}',
                         headers={'User-Agent':'Encore-R328-pinned-layer'}), timeout=30) as response:
        data = response.read()
actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
assert actual == sha, (actual, sha)
source = data.decode()
tree = ast.parse((root / 'tools/prepare-vulkan-port.py').read_text())
calls = [n.value for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
         and isinstance(n.value.func, ast.Name) and n.value.func.id == 'adapt'
         and len(n.value.args) == 3 and isinstance(n.value.args[0], ast.Constant)
         and n.value.args[0].value == rel]
assert len(calls) == 1
assert ast.literal_eval(calls[0].args[1]) == 'vulkan_present_layer.cpp'
# R329 introduces an independent stride-capacity guard in the same generated
# translation unit. This fixture isolates R328 AA lifetime, while the separate
# R329 exact-source fixture tests all three production generator edits.
all_pairs = ast.literal_eval(calls[0].args[2]); assert len(all_pairs) == 4
pairs = [(old, new) for old, new in all_pairs
         if 'buffer.Mapped().size()' not in new and 'raw_image_views.clear()' not in new]
assert len(pairs) == 2
patched = source
for old, new in pairs:
    assert patched.count(old) == 1
    patched = patched.replace(old, new)

cmake=(root/'headless/vulkan.cmake').read_text()
assert 'renderer_vulkan/present/layer.cpp' in cmake
assert '"${PORT_BUILD_DIR}/vulkan_present_layer.cpp"' in cmake
assert cmake.count('"${PORT_BUILD_DIR}/vulkan_present_layer.cpp"') >= 2
assert 'list(REMOVE_ITEM video_sources' in cmake

def methods(text):
    a=text.index('void Layer::RefreshResources(')
    b=text.index('void Layer::SetAntiAliasPass(', a)
    c=text.index('void Layer::ReleaseRawImages(', b)
    return text[a:c]
new = methods(patched)
old = methods(source)
assert new.count('device.GetLogical().WaitIdle();') == 2
assert new.count('scheduler.Finish();') == 2
assert old.count('device.GetLogical().WaitIdle();') == 0
assert new.index('device.GetLogical().WaitIdle();') < new.index('anti_alias.emplace<std::monostate>();')
assert new.index('void Layer::SetAntiAliasPass') < new.rindex('device.GetLogical().WaitIdle();') < new.index('    anti_alias_setting = filters.get_anti_aliasing();')
header=r'''
#include <cassert>
#include <cstddef>
#include <cstdio>
#include <variant>
#include <vector>
struct MockGpu { bool busy{}; int hazards{}; int drains{}; int finishes{}; };
MockGpu g;
struct VkExtent2D { unsigned width{}, height{}; };
namespace Settings {
    enum class AntiAliasing { None,Fxaa,Smaa };
    struct ResolutionInfo { unsigned ScaleUp(unsigned x) const { return x; } };
    struct Values { ResolutionInfo resolution_info; };
    inline Values values{};
}
namespace Tegra { struct FramebufferConfig { unsigned width{}, height{}; int pixel_format{}; }; }
struct LogicalDevice { void WaitIdle() const { ++g.drains; g.busy=false; } };
struct Device { LogicalDevice logical{}; const LogicalDevice& GetLogical() const { return logical; } };
struct Scheduler { void Finish() { ++g.finishes; } };
struct MemoryAllocator {};
struct Filters { Settings::AntiAliasing aa{Settings::AntiAliasing::Fxaa};
    Settings::AntiAliasing get_anti_aliasing() const { return aa; } };
struct Resource {
    bool owns{true};
    Resource(const Device&, MemoryAllocator&, std::size_t, VkExtent2D) {}
    Resource(Resource&& other) noexcept : owns(other.owns) { other.owns=false; }
    Resource(const Resource&)=delete;
    ~Resource(){ if (owns && g.busy) ++g.hazards; }
};
struct FXAA:Resource { using Resource::Resource; };
struct SMAA:Resource { using Resource::Resource; };
struct Layer {
    Scheduler scheduler;
    MemoryAllocator memory_allocator;
    Filters filters;
    const std::size_t image_count{3};
    unsigned raw_width{}, raw_height{};
    int pixel_format{};
    Settings::AntiAliasing anti_alias_setting{Settings::AntiAliasing::None};
    std::variant<std::monostate,FXAA,SMAA> anti_alias{};
    std::vector<int> raw_images{};
    int raw_releases{};
    void ReleaseRawImages(){++raw_releases; raw_images.clear();}
    void CreateStagingBuffer(const Device&,const Tegra::FramebufferConfig&){}
    void CreateRawImages(const Device&,const Tegra::FramebufferConfig&){raw_images.push_back(1);}
    void RefreshResources(const Device&,const Tegra::FramebufferConfig&);
    void SetAntiAliasPass(const Device&);
};
'''
tail=r'''
int main() {
    Device d;
    Layer l;
    Tegra::FramebufferConfig fb{1280,720,1};
    l.RefreshResources(d,fb);
    assert(g.drains==0 && g.finishes==0 && l.raw_releases==1);
    l.SetAntiAliasPass(d);
    assert(std::holds_alternative<FXAA>(l.anti_alias) && g.drains==0);
    g.busy=true;
    l.RefreshResources(d,fb);
    l.SetAntiAliasPass(d);
    assert(g.drains==0 && g.hazards==0 && g.busy);
    fb.width=1920; fb.height=1080; // R328 actual framebuffer resolution change
    l.RefreshResources(d,fb);
    assert(g.drains==1 && g.finishes==1 && g.hazards==0);
    l.SetAntiAliasPass(d);
    assert(g.drains==1 && std::holds_alternative<FXAA>(l.anti_alias));
    g.busy=true;
    l.filters.aa=Settings::AntiAliasing::Smaa; // runtime FXAA -> SMAA
    l.SetAntiAliasPass(d);
    assert(g.drains==2 && g.finishes==2 && g.hazards==0);
    assert(std::holds_alternative<SMAA>(l.anti_alias));
    g.busy=true;
    l.filters.aa=Settings::AntiAliasing::None; // runtime SMAA -> disabled
    l.SetAntiAliasPass(d);
    assert(g.drains==3 && g.finishes==3 && g.hazards==0);
    l.filters.aa=Settings::AntiAliasing::Fxaa; // disabled -> FXAA needs no old drain
    l.SetAntiAliasPass(d);
    assert(g.drains==3 && g.hazards==0);
    g.busy=false;
    std::puts("PASS R328: AA GPU lifetime on resizing and filter transitions, steady frames never drain");
}
'''

def run(label, code, success):
    with tempfile.TemporaryDirectory(prefix='eden-r328-aa-') as tmp:
        path=Path(tmp)
        (path/'test.cpp').write_text(header+code+tail)
        exe=path/'test'
        env=os.environ.copy()
        if sys.platform=='darwin' and not env.get('SDKROOT'):
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
            if sdk.is_dir(): env['SDKROOT']=str(sdk)
        subprocess.run(['c++','-std=c++20','-O1','-Wall','-Wextra','-Werror',
                        '-DPS5_NATIVE',str(path/'test.cpp'),'-o',str(exe)],check=True,env=env,timeout=35)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
        if success:
            assert result.returncode==0, (label, result.returncode, result.stderr)
            print(label+': '+result.stdout.strip())
        else:
            assert result.returncode != 0, (label, 'baseline unexpectedly passed')
            print(label+': EXPECTED FAIL - destroyed GPU-live FXAA resources on resize')

run('R328 corrected',new,True)
run('Pinned original',old,False)
