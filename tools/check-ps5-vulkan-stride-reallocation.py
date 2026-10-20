#!/usr/bin/env python3
"""R329: compile pinned actual Layer::RefreshResources and prove stride resize safety."""
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
expected_sha = '14935f92bb450973e85237fed52f8dea6d172688'
if len(sys.argv) > 1:
    content = (Path(sys.argv[1]) / rel).read_bytes()
else:
    with urlopen(Request(f'https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{rel}',
                         headers={'User-Agent':'EdenEncore-R329-source'}), timeout=35) as response:
        content = response.read()
blob_hash = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
assert blob_hash == expected_sha, (blob_hash, expected_sha)
original = content.decode()
program = ast.parse((root / 'tools/prepare-vulkan-port.py').read_text())
calls = [n.value for n in program.body if isinstance(n, ast.Expr)
         and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
         and n.value.func.id == 'adapt' and len(n.value.args) == 3
         and isinstance(n.value.args[0], ast.Constant)
         and n.value.args[0].value == rel]
assert len(calls) == 1
assert ast.literal_eval(calls[0].args[1]) == 'vulkan_present_layer.cpp'
pairs = ast.literal_eval(calls[0].args[2])
# Other independently verified layer transformations may be appended; require
# the exact stride-capacity guard, not an obsolete adapter count.
assert len(pairs) >= 4
assert len([x for x in pairs if 'buffer.Mapped().size() == CalculateBufferSize' in x[1]]) == 1
updated = original
for before, after in pairs:
    assert updated.count(before) == 1, before[:120]
    updated = updated.replace(before, after)

def refresh(text):
    start = text.index('void Layer::RefreshResources(')
    end = text.index('void Layer::SetAntiAliasPass(',start)
    return text[start:end]
assert 'buffer.Mapped().size()' not in refresh(original)
assert 'buffer.Mapped().size() == CalculateBufferSize(framebuffer)' in refresh(updated)
assert updated.index('buffer.Mapped().size() == CalculateBufferSize(framebuffer)') < updated.index('anti_alias.emplace<std::monostate>();')
# Check the pinned allocator Mapped span owns EXACT ci.size bytes. Unlike VMA
# reserved capacity, the exposed mapped span is the requested buffer size.
allocator = 'src/video_core/vulkan_common/vulkan_memory_allocator.cpp'
if len(sys.argv) > 1:
    memory_source = (Path(sys.argv[1]) / allocator).read_text()
else:
    with urlopen(Request(f'https://raw.githubusercontent.com/eden-emulator/mirror/{pin}/{allocator}',
                         headers={'User-Agent':'EdenEncore-R329-source'}), timeout=35) as response:
        memory_source = response.read().decode()
assert 'const std::span<u8> mapped_data = data ? std::span<u8>{data, ci.size}' in memory_source
assert 'GetSizeInBytes(framebuffer) * image_count' in original
assert 'static_cast<std::size_t>(framebuffer.stride)' in original
assert 'mapped_span.subspan(image_offset, linear_size)' in original
assert 'renderer_vulkan/present/layer.cpp' in (root/'headless/vulkan.cmake').read_text()
assert '"${PORT_BUILD_DIR}/vulkan_present_layer.cpp"' in (root/'headless/vulkan.cmake').read_text()

prefix=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstddef>
#include <span>
#include <variant>
#include <vector>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
unsigned gpu_idles{}, gpu_finishes{}, gpu_tick_waits{};
namespace Tegra { struct FramebufferConfig { u32 width{}, height{}, stride{}; int pixel_format{}; }; }
struct LogicalDevice { void WaitIdle() const { ++gpu_idles; } };
struct Device { const LogicalDevice& GetLogical() const { static LogicalDevice x;return x;} };
struct Scheduler { void Finish() { ++gpu_finishes; } void Wait(u64) { ++gpu_tick_waits; } };
struct AA {};
struct Buffer {
    std::vector<unsigned char> allocation;
    std::span<unsigned char> Mapped(){return allocation;}
};
struct Layer {
    u32 raw_width{}, raw_height{};
    int pixel_format{};
    std::vector<int> raw_images;
    std::variant<std::monostate, AA> anti_alias;
    std::vector<u64> resource_ticks{1,2,3};
    Scheduler scheduler;
    Buffer buffer;
    std::size_t image_count{3};
    unsigned allocations{}, releases{};
    std::size_t CalculateBufferSize(const Tegra::FramebufferConfig& fb) const {
        return std::size_t(fb.stride)*fb.height*4*image_count;
    }
    void ReleaseRawImages(){ ++releases;raw_images.clear();buffer.allocation.clear(); }
    void CreateStagingBuffer(const Device&,const Tegra::FramebufferConfig& fb) {
        buffer.allocation.resize(CalculateBufferSize(fb)); ++allocations;
    }
    void CreateRawImages(const Device&,const Tegra::FramebufferConfig&) {raw_images.push_back(1);}
    void RefreshResources(const Device&, const Tegra::FramebufferConfig&);
};
'''
suffix=r'''
int main(){
    Device device;
    Layer layer;
    Tegra::FramebufferConfig fb{640,360,704,1};
    auto fits=[&]{
        const std::size_t stride_bytes=std::size_t(fb.stride)*fb.height*4;
        return layer.buffer.Mapped().size() >= 3*stride_bytes;
    };
    layer.RefreshResources(device,fb);
    assert(layer.allocations==1 && fits());
    layer.anti_alias.emplace<AA>();
    layer.RefreshResources(device,fb);
    assert(layer.allocations==1 && fits()); // No steady-frame realloc.
    fb.stride=768;
    layer.RefreshResources(device,fb); // Same resolution, different pitch.
    assert(layer.allocations==2 && fits()); // Old pinned branch fails HERE.
    assert(std::holds_alternative<AA>(layer.anti_alias)); // R330: no AA reset.
    assert(gpu_idles==0 && gpu_finishes==0 && gpu_tick_waits==3);
    layer.RefreshResources(device,fb);
    assert(layer.allocations==2 && fits());
    assert(gpu_tick_waits==3); // No extra waits on an unchanged frame.
    fb.stride=736;
    layer.RefreshResources(device,fb);
    assert(layer.allocations==3 && fits()); // Shrinking pitch also updates offsets.
    assert(std::holds_alternative<AA>(layer.anti_alias));
    assert(gpu_idles==0 && gpu_finishes==0 && gpu_tick_waits==6);
    fb.height=400;
    layer.RefreshResources(device,fb);
    assert(layer.allocations==4 && fits());
    assert(gpu_idles==1 && gpu_finishes==1); // Actual resize still guards AA destruction.
    assert(std::holds_alternative<std::monostate>(layer.anti_alias));
    fb.pixel_format=2;
    layer.RefreshResources(device,fb);
    assert(layer.allocations==5 && fits());
    std::puts("PASS R330 exact pinned Layer refresh: stride reallocates staging only; AA preserved; no GPU idle");
}
'''

def run(label, function, expected_success):
    with tempfile.TemporaryDirectory(prefix='eden-r329-stride-') as work:
        source = Path(work)/'test.cpp'
        exe = Path(work)/'test'
        source.write_text(prefix+function+suffix)
        env=os.environ.copy()
        if sys.platform=='darwin' and not env.get('SDKROOT'):
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
            if sdk.is_dir():env['SDKROOT']=str(sdk)
        subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror','-DPS5_NATIVE',
                        str(source),'-o',str(exe)],check=True,timeout=45,env=env)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
        if expected_success:
            assert result.returncode==0,(label,result.returncode,result.stderr)
            print(label+': '+result.stdout.strip())
        else:
            assert result.returncode!=0, (label,'original unexpectedly passed')
            print(label+': EXPECTED FAILURE, reused undersized stale buffer on stride increase')
run('R330 corrected',refresh(updated),True)
run('Pinned original',refresh(original),False)
