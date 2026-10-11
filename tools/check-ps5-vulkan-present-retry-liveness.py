#!/usr/bin/env python3
"""R335: actual pinned present retry source replay with bounded-surface-loss behavior."""
from pathlib import Path
import ast
import hashlib
import os
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PIN = '5f142c7926d0c7fcbbd0ce30794d72f638a43b2a'
CPP = 'src/video_core/renderer_vulkan/vk_present_manager.cpp'
HEADER = 'src/video_core/renderer_vulkan/vk_present_manager.h'
BLOB = '3491f8fb7563f2557a476fec8edb4f220f5d27fc'

def read(rel):
    if len(sys.argv) > 1:
        return (Path(sys.argv[1]) / rel).read_bytes()
    req = Request(f'https://raw.githubusercontent.com/eden-emulator/mirror/{PIN}/{rel}',
                  headers={'User-Agent': 'EdenEncore-R335'})
    with urlopen(req, timeout=40) as stream:
        return stream.read()

def replay(rel):
    original = read(rel)
    if rel == CPP:
        git_blob = hashlib.sha1(b'blob ' + str(len(original)).encode() + b'\0' + original).hexdigest()
        assert git_blob == BLOB, ('pinned source changed', git_blob)
    tree = ast.parse((ROOT / 'tools/prepare-vulkan-port.py').read_text())
    calls = [node.value for node in tree.body if isinstance(node, ast.Expr)
             and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
             and node.value.func.id == 'adapt' and len(node.value.args) == 3
             and isinstance(node.value.args[0], ast.Constant) and node.value.args[0].value == rel]
    assert len(calls) == 1, rel
    patches = ast.literal_eval(calls[0].args[2])
    updated = original.decode()
    for before, after in patches:
        assert updated.count(before) == 1, before[:80]
        updated = updated.replace(before, after)
    return original.decode(), updated

original, patched = replay(CPP)
_, header = replay(HEADER)
assert 'void DiscardFrame(Frame* frame);' in header
assert 'constexpr u32 MAX_PRESENT_ATTEMPTS = 3;' in patched
start = 'void PresentManager::CopyToSwapchain(Frame* frame) {'
stop = '\nvoid PresentManager::CopyToSwapchainImpl(Frame* frame) {'
old_loop = original[original.index(start):original.index(stop, original.index(start))]
new_loop = patched[patched.index(start):patched.index(stop, patched.index(start))]
assert 'while (true)' in old_loop and 'DiscardFrame(frame)' not in old_loop
assert 'while (true)' not in new_loop
assert 'for (u32 attempt = 0; attempt < MAX_PRESENT_ATTEMPTS; ++attempt)' in new_loop
assert new_loop.rstrip().endswith('DiscardFrame(frame);\n}')
release = patched[patched.index('void PresentManager::DiscardFrame(Frame* frame) {'):patched.index(start)]
for term in ['.waitSemaphoreCount = 1U', '.pWaitSemaphores = &render_ready',
             '.commandBufferCount = 0U', 'std::scoped_lock submit_lock{scheduler.submit_mutex}',
             'Submit(submit_info, *frame->present_done)']:
    assert term in release, term

mock = r'''
#include <cassert>
#include <exception>
#include <cstdio>
#include <cstdint>
using u32 = std::uint32_t;
constexpr int VK_ERROR_SURFACE_LOST_KHR = -1000000000;
[[maybe_unused]] constexpr u32 MAX_PRESENT_ATTEMPTS = 3;
namespace vk {
struct Exception : std::exception {
  int status;
  explicit Exception(int s) : status(s) {}
  int GetResult() const { return status; }
};
}
struct Frame {};
struct PresentManager {
  int errors = 0, attempts = 0, recreations = 0, discards = 0;
  void RecreateSwapchain(Frame*) { ++recreations; }
  void CopyToSwapchainImpl(Frame*) {
    ++attempts;
    if (errors) { --errors; throw vk::Exception(VK_ERROR_SURFACE_LOST_KHR); }
  }
  void DiscardFrame(Frame*) { ++discards; }
  void CopyToSwapchain(Frame*);
};
'''
test = r'''
int main() {
  Frame f;
  PresentManager all_failed;
  all_failed.errors = 4;
  all_failed.CopyToSwapchain(&f);
  assert(all_failed.attempts == 3 && all_failed.recreations == 2 && all_failed.discards == 1);
  PresentManager transient;
  transient.errors = 2;
  transient.CopyToSwapchain(&f);
  assert(transient.attempts == 3 && transient.recreations == 2 && transient.discards == 0);
  PresentManager healthy;
  healthy.CopyToSwapchain(&f);
  assert(healthy.attempts == 1 && healthy.recreations == 0 && healthy.discards == 0);
  std::puts("R335 PASS: bounded terminal loss, two retries recover, healthy one-shot unchanged");
}
'''

def exercise(name, function, expected_success):
    with tempfile.TemporaryDirectory(prefix='eden-r335-present-') as dir:
        p=Path(dir)
        (p/'test.cpp').write_text(mock+function+test)
        env=os.environ.copy()
        if sys.platform=='darwin' and not env.get('SDKROOT'):
            sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
            if sdk.is_dir(): env['SDKROOT']=str(sdk)
        subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror',
                        str(p/'test.cpp'),'-o',str(p/'test')],check=True,timeout=30,env=env)
        result=subprocess.run([str(p/'test')],capture_output=True,text=True,timeout=15)
        if expected_success:
            assert result.returncode==0,(name,result.stderr)
            print(result.stdout.strip())
        else:
            assert result.returncode!=0,(name,'original unexpectedly bounded surface losses')
            print('R335 original: EXPECTED FAILURE (4 surface losses result in >3 present attempts)')

exercise('corrected',new_loop,True)
exercise('original',old_loop,False)
print('R335 PASS: pinned source replay, Vulkan semaphore/fence discard, no ordinary-present change')
