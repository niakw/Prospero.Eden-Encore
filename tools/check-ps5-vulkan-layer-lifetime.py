#!/usr/bin/env python3
"""R327: exact generated Vulkan layer-rebuild source, executed under a fake busy GPU.

A shrinking/growing layer collection must not free Vulkan image/view/descriptors
until work referencing the OLD layers has drained. Normal frames never drain.
"""
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
module = ast.parse((root / 'tools/prepare-vulkan-port.py').read_text())
adapters = []
for node in module.body:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        continue
    call = node.value
    if (isinstance(call.func, ast.Name) and call.func.id == 'adapt'
            and len(call.args) == 3 and isinstance(call.args[0], ast.Constant)
            and call.args[0].value == 'src/video_core/renderer_vulkan/vk_blit_screen.cpp'):
        adapters.append(call)
assert len(adapters) == 1
pairs = ast.literal_eval(adapters[0].args[2])
matching = [(old, new) for old, new in pairs
            if 'if (layers.size() != framebuffers.size())' in old]
assert len(matching) == 1
old, changed = matching[0]
assert 'layers.clear();' in old and 'WaitIdle' not in old
assert changed.count('WaitIdle(device);') == 1
assert changed.index('if (!layers.empty())') < changed.index('WaitIdle(device);') < changed.index('layers.clear();')
assert '#ifdef PS5_NATIVE' in changed and '#endif' in changed
assert changed.endswith('layers.clear();')
# Verify existing (distinct) drain paths are preserved and still used for filter changes.
source = (root / 'tools/prepare-vulkan-port.py').read_text()
assert "adapt('src/video_core/renderer_vulkan/vk_blit_screen.cpp', 'vulkan_blit_screen.cpp'" in source
# Exact generated replacement plus the original, unchanged suffix of the
# pinned loop; the generator changes only the first two source lines.
original_suffix = '''
        for (size_t i = 0; i < framebuffers.size(); ++i) {
            layers.emplace_back(device, memory_allocator, scheduler, device_memory, image_count,
                                window_size, window_adapt->GetDescriptorSetLayout(), filters);
        }
    }
'''
# Exact updated generator's replacement is the portion under test.
header = r'''
#include <cassert>
#include <cstdio>
#include <cstddef>
#include <vector>
struct Device {};
struct MemoryAllocator {};
struct Scheduler {};
struct MemoryManager {};
struct Filters {};
struct Extent { unsigned width{}, height{}; };
int busy{}, hazards{}, drains{};
struct Layer {
    bool owns{true};
    Layer(Device&, MemoryAllocator&, Scheduler&, MemoryManager&, std::size_t, Extent, int, Filters&) {}
    Layer(Layer&& other) noexcept : owns(other.owns) { other.owns = false; }
    Layer(const Layer&) = delete;
    ~Layer() { if (owns && busy) ++hazards; }
};
struct Adapt { int GetDescriptorSetLayout() const { return 1; } };
struct Mock {
    Device device;
    MemoryAllocator memory_allocator;
    Scheduler scheduler;
    MemoryManager device_memory;
    std::size_t image_count{3};
    Extent window_size{2560,1440};
    Adapt adapt;
    Adapt* window_adapt{&adapt};
    Filters filters;
    std::vector<Layer> layers;
    std::vector<int> framebuffers;
    void WaitIdle(const Device&) { ++drains; busy = 0; }
    void Resize(unsigned count) {
        framebuffers.resize(count);
'''
tail = r'''
    }
};
int main() {
    {
        Mock mock;
        mock.layers.reserve(8);
        mock.Resize(1); // Initial creation: nothing to destroy or wait for.
        assert(drains==0 && hazards==0 && mock.layers.size()==1);
        busy = 1;
        mock.Resize(1); // Common per-frame path: no changes, no waits.
        assert(drains==0 && hazards==0);
        mock.Resize(2); // Must drain BEFORE destroying the previous live layer.
        assert(drains==1 && hazards==0 && mock.layers.size()==2);
        busy = 1;
        mock.Resize(0); // Removal of all HUD layers must also drain.
        assert(drains==2 && hazards==0 && mock.layers.empty());
        mock.Resize(3); // Constructing from empty again is nonblocking.
        assert(drains==2 && hazards==0 && mock.layers.size()==3);
    }
    assert(hazards==0);
    std::puts("PASS R327 Vulkan layer count changes drain only before deleting GPU-live resources");
}
'''

def run(label: str, fragment: str, expected: int):
    with tempfile.TemporaryDirectory(prefix='eden-layer-lifetime-') as tmp:
        file = Path(tmp) / 'layer.cpp'
        binary = Path(tmp) / 'layer'
        file.write_text(header + fragment + tail)
        env = os.environ.copy()
        if sys.platform == 'darwin' and not env.get('SDKROOT'):
            sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
            if sdk.exists(): env['SDKROOT'] = str(sdk)
        subprocess.run(['c++', '-std=c++20', '-DPS5_NATIVE', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(file), '-o', str(binary)], check=True, timeout=40, env=env)
        result = subprocess.run([str(binary)], timeout=10, capture_output=True, text=True)
        if expected is None:
            assert result.returncode != 0, (label, 'original branch unexpectedly passed')
            print(label, 'EXPECTED FAIL: released resource while GPU still in flight')
        else:
            assert result.returncode == expected, (label, result.returncode, result.stderr)
            print(label, result.stdout.strip())

# Use NDEBUG-independent checks for the negative control to avoid an abort signal.
run('PS5 fixed:', changed + original_suffix, 0)
# The native branch is precisely the one that lacked a drain. Verify its source ordering.
run('Unfixed pinned:', old + original_suffix, None)
print('PASS R327 negative-control source and corrected branch')
