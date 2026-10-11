#!/usr/bin/env python3
"""R337: pinned Vulkan present source, bounded vkAcquireNextImageKHR recreation regression."""
from pathlib import Path
import ast, hashlib, os, subprocess, sys, tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REL = 'src/video_core/renderer_vulkan/vk_present_manager.cpp'
PIN = '5f142c7926d0c7fcbbd0ce30794d72f638a43b2a'
BLOB = '3491f8fb7563f2557a476fec8edb4f220f5d27fc'
if len(sys.argv) > 1:
    raw=(Path(sys.argv[1])/REL).read_bytes()
else:
    req=Request(f'https://raw.githubusercontent.com/eden-emulator/mirror/{PIN}/{REL}',
                headers={'User-Agent':'EdenEncore-R337'})
    with urlopen(req,timeout=40) as stream:raw=stream.read()
assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() == BLOB
original=raw.decode()
tree=ast.parse((ROOT/'tools/prepare-vulkan-port.py').read_text())
calls=[n.value for n in tree.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
       and isinstance(n.value.func,ast.Name) and n.value.func.id=='adapt'
       and len(n.value.args)==3 and isinstance(n.value.args[0],ast.Constant)
       and n.value.args[0].value==REL]
assert len(calls)==1
replayed=original
for before,after in ast.literal_eval(calls[0].args[2]):
    assert replayed.count(before)==1,before[:110]
    replayed=replayed.replace(before,after)
start='void PresentManager::CopyToSwapchainImpl(Frame* frame) {'
end='    const vk::CommandBuffer cmdbuf{frame->cmdbuf};'
def extract(text):
    fragment=text[text.index(start):text.index(end,text.index(start))]
    first=fragment.index('    while (swapchain.AcquireNextImage()) {') if '    while (swapchain.AcquireNextImage()) {' in fragment else fragment.index('    for (u32 acquire_attempt = 0;')
    return fragment[first:fragment.rindex('    }')+6]
old,corrected=extract(original),extract(replayed)
assert 'while (swapchain.AcquireNextImage())' in old
assert 'for (u32 acquire_attempt = 0; swapchain.AcquireNextImage(); ++acquire_attempt)' in corrected
assert 'if (acquire_attempt >= MAX_PRESENT_ATTEMPTS - 1)' in corrected
assert 'throw vk::Exception(VK_ERROR_SURFACE_LOST_KHR)' in corrected
assert 'RecreateSwapchain(frame);' in corrected
outer=replayed[replayed.index('void PresentManager::CopyToSwapchain(Frame* frame) {'):replayed.index(start)]
assert 'for (u32 attempt = 0; attempt < MAX_PRESENT_ATTEMPTS; ++attempt)' in outer
assert 'DiscardFrame(frame);' in outer

prologue=r'''
#include <cassert>
#include <cstdio>
#include <stdexcept>
#include <cstdint>
using u32=std::uint32_t;
[[maybe_unused]] constexpr u32 MAX_PRESENT_ATTEMPTS=3;
[[maybe_unused]] constexpr int VK_ERROR_SURFACE_LOST_KHR=-1000000000;
namespace vk {struct Exception {int status;explicit Exception(int code):status(code){}};}
struct Frame {};
struct Swapchain {
  int bad=0, acquisitions=0;
  bool AcquireNextImage() {
    ++acquisitions;
    if(acquisitions>16) throw std::runtime_error("persistent stale swapchain: missing bound");
    if(bad>0) {--bad;return true;}
    return false;
  }
};
struct PresentManager {
  Swapchain swapchain;
  int recreations=0;
  void RecreateSwapchain(Frame*) {++recreations;}
  void CopyToSwapchainImpl(Frame*);
};
void PresentManager::CopyToSwapchainImpl(Frame* frame) {
'''
corrected_tail=r'''
}
int main() {
  Frame frame;
  PresentManager healthy;
  healthy.CopyToSwapchainImpl(&frame);
  assert(healthy.swapchain.acquisitions==1 && healthy.recreations==0);
  PresentManager temporary;
  temporary.swapchain.bad=2;
  temporary.CopyToSwapchainImpl(&frame);
  assert(temporary.swapchain.acquisitions==3 && temporary.recreations==2);
  PresentManager terminal;
  terminal.swapchain.bad=100;
  bool loss=false;
  try {terminal.CopyToSwapchainImpl(&frame);} catch(const vk::Exception& ex) {loss=ex.status==VK_ERROR_SURFACE_LOST_KHR;}
  assert(loss && terminal.swapchain.acquisitions==3 && terminal.recreations==2);
  std::puts("R337 PASS: healthy=1, 2 transient acquisitions recover, persistent error <=3 attempts");
}
'''
original_tail=r'''
}
int main() {
  Frame frame; PresentManager bad; bad.swapchain.bad=100;
  bool caught=false;
  try {bad.CopyToSwapchainImpl(&frame);} catch(const std::runtime_error&) {caught=true;}
  assert(caught && bad.swapchain.acquisitions>16);
  std::puts("R337 expected original defect: more than 16 unbounded acquire retries");
}
'''
def run(body,tail):
    with tempfile.TemporaryDirectory(prefix='eden-r337-acquire-') as d:
        d=Path(d);(d/'test.cpp').write_text(prologue+body+tail)
        env=os.environ.copy()
        if sys.platform=='darwin' and not env.get('SDKROOT'):
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
            if sdk.is_dir():env['SDKROOT']=str(sdk)
        subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror',
                        str(d/'test.cpp'),'-o',str(d/'test')],check=True,timeout=30,env=env)
        res=subprocess.run([str(d/'test')],capture_output=True,text=True,timeout=12)
        assert res.returncode==0,res.stderr
        print(res.stdout.strip())
run(old,original_tail)
run(corrected,corrected_tail)
print('R337 PASS: source SHA, all generator patches, outer existing discard path')
