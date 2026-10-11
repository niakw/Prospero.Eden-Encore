#!/usr/bin/env python3
"""R334: original pinned PresentManager recreates VkImage before its dependent views/FBO."""
import ast
import hashlib
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PIN = '5f142c7926d0c7fcbbd0ce30794d72f638a43b2a'
REL = 'src/video_core/renderer_vulkan/vk_present_manager.cpp'
BLOB = '3491f8fb7563f2557a476fec8edb4f220f5d27fc'
if len(sys.argv) > 1:
    raw = (Path(sys.argv[1]) / REL).read_bytes()
else:
    req = Request(f'https://raw.githubusercontent.com/eden-emulator/mirror/{PIN}/{REL}',
                  headers={'User-Agent': 'EdenEncore-R334'})
    with urlopen(req, timeout=40) as handle:
        raw = handle.read()
actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
assert actual == BLOB, (actual, BLOB)
pinned = raw.decode()
tree = ast.parse((ROOT / 'tools/prepare-vulkan-port.py').read_text())
calls = [node.value for node in tree.body
         if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
         and isinstance(node.value.func, ast.Name) and node.value.func.id == 'adapt'
         and len(node.value.args) == 3 and isinstance(node.value.args[0], ast.Constant)
         and node.value.args[0].value == REL]
assert len(calls) == 1
assert ast.literal_eval(calls[0].args[1]) == 'vulkan_present_manager.cpp'
patches = ast.literal_eval(calls[0].args[2])
assert len(patches) >= 10
patched = pinned
for old, new in patches:
    assert patched.count(old) == 1, old[:90]
    patched = patched.replace(old, new)

START = 'void PresentManager::RecreateFrame(Frame* frame,'
STOP = 'void PresentManager::WaitPresent()'
def function(text):
    return text[text.index(START):text.index(STOP, text.index(START))]
old = function(pinned)
new = function(patched)
first_image = '    frame->image = memory_allocator.CreateImage({'
release = ['    frame->framebuffer = vk::Framebuffer{};',
           '    frame->storage_view = vk::ImageView{};',
           '    frame->image_view = vk::ImageView{};']
assert old.count(first_image) == new.count(first_image) == 1
assert all(part not in old.split(first_image, 1)[0] for part in release)
assert all(new.count(part) == 1 for part in release)
assert new.index(release[0]) < new.index(release[1]) < new.index(release[2]) < new.index(first_image)
assert new.index(first_image) < new.index('    frame->image_view = dld.CreateImageView({')
assert new.index('    frame->image_view = dld.CreateImageView({') < new.index('    frame->framebuffer = dld.CreateFramebuffer({')

# The exact lifecycle statements extracted from the real compiled source are
# replayed with host RAII stand-ins. Production's full Vk aggregate method is
# verified separately with clang targeting x86_64-sie-ps5.
def release_sequence(text):
    out = [statement for statement in release if statement in text.split(first_image, 1)[0]]
    assert len(out) in (0, 3)
    return '\n'.join(out + ['    frame->image = memory_allocator.CreateImage();'])

prologue = r'''
#include <cassert>
#include <cstdio>
#include <memory>
int live_images=0, live_views=0, live_fbos=0, hazards=0;
struct Image {
  Image(){++live_images;}
  ~Image(){if(live_views || live_fbos) ++hazards;--live_images;}
};
struct ImageView {
  ImageView(){++live_views;}
  ~ImageView(){if(live_fbos) ++hazards;--live_views;}
};
struct Framebuffer {
  Framebuffer(){++live_fbos;}
  ~Framebuffer(){--live_fbos;}
};
namespace vk {using ImageView=std::unique_ptr<::ImageView>;using Framebuffer=std::unique_ptr<::Framebuffer>;}
struct Frame {
  std::unique_ptr<Image> image;
  vk::ImageView image_view, storage_view;
  vk::Framebuffer framebuffer;
};
struct Allocator {std::unique_ptr<Image> CreateImage(){return std::make_unique<Image>();}};
int main() {
  Frame object;
  Frame* frame = &object;
  Allocator memory_allocator;
  frame->image=std::make_unique<Image>();
  frame->image_view=std::make_unique<ImageView>();
  frame->storage_view=std::make_unique<ImageView>();
  frame->framebuffer=std::make_unique<Framebuffer>();
'''
end = r'''
  assert(hazards == 0); // the pinned original fails: image dies while its views/FBO live
  frame->framebuffer.reset(); frame->storage_view.reset(); frame->image_view.reset(); frame->image.reset();
  assert(live_images == 0 && live_views == 0 && live_fbos == 0);
  std::puts("R334 PASS: frame framebuffer/views released before replaced image");
}
'''
def exercise(name, body, success):
    with tempfile.TemporaryDirectory(prefix='eden-r334-frame-') as tmp:
        d = Path(tmp)
        (d/'test.cpp').write_text(prologue + body + end)
        env = os.environ.copy()
        if sys.platform == 'darwin' and not env.get('SDKROOT'):
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
            if sdk.is_dir(): env['SDKROOT']=str(sdk)
        subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror',
                        str(d/'test.cpp'),'-o',str(d/'test')], check=True,timeout=45,env=env)
        p=subprocess.run([str(d/'test')],capture_output=True,text=True,timeout=10)
        if success:
            assert p.returncode==0,(name,p.stderr)
            print(name,p.stdout.strip())
        else:
            assert p.returncode!=0,(name,'original unexpectedly kept child resource validity')
            print(name,'EXPECTED FAILURE (VkImage replaced while views/FBO live)')
exercise('R334 corrected:',release_sequence(new),True)
exercise('Pinned original:',release_sequence(old),False)
print('R334 source SHA verified, all generator patches replayed; full native C++ compile separate')
