#!/usr/bin/env python3
"""R325: host-compile the generated atypical descriptor reservation pre-drain.

Only PS5 pipelines needing more than 0x400 entries can take this path. It
must precede the paired guest cache locks and preserve the original fallback.
"""
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
generator = (root / 'tools/prepare-vulkan-port.py').read_text()
program = ast.parse(generator)
adapters = {}
for node in program.body:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        continue
    call = node.value
    if not isinstance(call.func, ast.Name) or call.func.id != 'adapt':
        continue
    if len(call.args) != 3 or not isinstance(call.args[0], ast.Constant):
        continue
    adapters.setdefault(call.args[0].value, []).append(call)

def pairs_for(rel):
    assert len(adapters[rel]) == 1, (rel, len(adapters[rel]))
    return [ast.literal_eval(n) for n in adapters[rel][0].args[2].elts
            if isinstance(n, ast.Tuple) and len(n.elts) == 2 and
            all(isinstance(item, ast.Constant) for item in n.elts)]

header_pairs = pairs_for('src/video_core/renderer_vulkan/vk_update_descriptor.h')
method_pairs = [(a,b) for a,b in header_pairs if 'PreflightLargeGuestDraw' in b]
assert len(method_pairs) == 1
header = method_pairs[0][1]
assert 'PreflightGuestDraw' in header
begin = header.index('    template <typename WaitWorker>')
end = header.index('\n#endif', begin)
methods = header[begin:end]
assert methods.count('wait_worker();') == 2
assert 'entries >= frame_payload_size' in methods
raster_pairs = pairs_for('src/video_core/renderer_vulkan/vk_rasterizer.cpp')
preflight_pairs = [(a,b) for a,b in raster_pairs if 'PreflightLargeGuestDraw(' in b]
assert len(preflight_pairs) == 1
raster = preflight_pairs[0][1]
assert 'std::scoped_lock' not in raster  # this preflight is added before the lock adapter
assert 'pipeline = pipeline_cache.CurrentGraphicsPipeline();' in raster
assert 'gpu_memory->FlushCaching();' in raster
# The next original adaptation applies the paired locks to this same function.
assert 'std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};' in generator
assert 'pipeline->DescriptorEntryReservation()' in raster
pipeline_pairs = pairs_for('src/video_core/renderer_vulkan/vk_graphics_pipeline.h')
getters = [(a,b) for a,b in pipeline_pairs if 'DescriptorEntryReservation() const noexcept' in b]
assert len(getters) == 1
assert 'num_descriptor_entries != 0 ? num_descriptor_entries : 0x400' in getters[0][1]
# Acquire remains the fall-through guard, so no invalid-sized descriptor gets silently accepted.
pinned = (root / 'tools/prepare-vulkan-port.py').read_text()
assert "src/video_core/renderer_vulkan/vk_update_descriptor.h" in pinned

cpp = '''#include <cassert>\n#include <cstddef>\n#include <vector>\nstruct Queue {\n    const size_t frame_payload_size=4096;\n    std::vector<int> backing = std::vector<int>(frame_payload_size);\n    int* payload_start=backing.data();\n    int* payload_cursor=payload_start;\n''' + methods + '''
    void set_used(size_t count) { assert(count<frame_payload_size); payload_cursor=payload_start+count; }
    size_t used() const { return size_t(payload_cursor-payload_start); }
};
int main() {
    Queue q;
    int waits=0;
    auto wait=[&] {++waits;};
    q.set_used(1000);
    assert(!q.PreflightGuestDraw(wait));
    assert(!q.PreflightLargeGuestDraw(wait,1024));
    assert(!q.PreflightLargeGuestDraw(wait,1500));
    assert(q.used()==1000 && waits==0);
    q.set_used(2596); // 2596 + 1500 = 4096, exactly full.
    assert(!q.PreflightGuestDraw(wait));
    assert(q.PreflightLargeGuestDraw(wait,1500));
    assert(q.used()==0 && waits==1);
    q.set_used(2500);
    assert(!q.PreflightLargeGuestDraw(wait,1500));
    assert(q.used()==2500 && waits==1);
    q.set_used(3072);
    assert(q.PreflightGuestDraw(wait));
    assert(q.used()==0 && waits==2);
    q.set_used(3096);
    assert(!q.PreflightLargeGuestDraw(wait,0));
    assert(!q.PreflightLargeGuestDraw(wait,4096));
    assert(!q.PreflightLargeGuestDraw(wait,100));
    assert(q.used()==3096 && waits==2);
}
'''
with tempfile.TemporaryDirectory(prefix='eden-r325-descriptor-') as tmp:
    path = Path(tmp)
    (path/'check.cpp').write_text(cpp)
    exe = path/'check'
    env=os.environ.copy()
    if sys.platform == 'darwin' and not env.get('SDKROOT'):
        old_sdk=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
        if old_sdk.exists(): env['SDKROOT']=str(old_sdk)
    subprocess.run(['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror',
                    str(path/'check.cpp'),'-o',str(exe)],check=True,env=env,timeout=40)
    subprocess.run([str(exe)],check=True,timeout=10)
print('PASS R325 exact host C++ descriptor preflight: small / large / boundary / fallback')
