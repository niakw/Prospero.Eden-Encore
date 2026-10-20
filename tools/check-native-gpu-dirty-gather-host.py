#!/usr/bin/env python3
"""Compare actual dirty collectors: exact ordered coverage and callback cost."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
active = ROOT / 'vendor/encore-active/eden-core/overrides/core/gpu_dirty_memory_manager.h'
pinned = (ROOT / 'vendor/sources/eden/src/core/gpu_dirty_memory_manager.h').read_text()
assert pinned.count('namespace Core {') == 1
for relative in ('vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp',
                 'vendor/encore-active/eden-core/src/video_core/renderer_opengl/gl_rasterizer.cpp'):
    callback = (ROOT / relative).read_text().split('::OnCacheInvalidation(', 1)[1]
    assert 'if (addr == 0 || size == 0)' in callback.split('\n}', 1)[0]
assert 'if (size > 256 * 1024) return false;' in (ROOT / 'headless/image_pages.h').read_text()
fixture = r'''
#include "core/gpu_dirty_memory_manager.h"
#include "previous.h"
#include <cassert>
#include <cstdio>
#include <utility>
#include <vector>
using Range = std::pair<PAddr, std::size_t>;
using Ranges = std::vector<Range>;
template<class Manager>
Ranges Gather(Manager& manager) {
    Ranges result;
    std::function<void(PAddr, std::size_t)> callback = [&](PAddr a, std::size_t n) {
        assert(n && a % 64 == 0 && n % 64 == 0);
        result.emplace_back(a, n);
    };
    manager.Gather(callback);
    return result;
}
std::vector<PAddr> Expand(const Ranges& ranges, bool rasterizer = false) {
    std::vector<PAddr> cells;
    for (const auto& [a, n] : ranges) {
        if (rasterizer && a == 0) continue;
        for (PAddr p = a; p < a + n; p += 64) cells.push_back(p);
    }
    return cells;
}
void Check(const Ranges& writes, bool linear = false) {
    PreviousCore::GPUDirtyMemoryManager previous;
    Core::GPUDirtyMemoryManager current;
    for (unsigned epoch = 0; epoch < 2; ++epoch) {
        for (const auto& [a, n] : writes) {
            previous.Collect(a, n); current.Collect(a, n);
        }
        const auto before = Gather(previous), after = Gather(current);
        // Exact sequence includes duplicates, backward ranges and every gap.
        assert(Expand(before) == Expand(after));
        // Both actual rasterizers ignore callbacks starting at address zero.
        // Such a range must never swallow a following nonzero invalidation.
        assert(Expand(before, true) == Expand(after, true));
        assert(after.size() <= before.size());
        for (const auto& [a, n] : after) { (void)a; assert(n <= 256 * 1024); }
        assert(Gather(previous).empty() && Gather(current).empty());
        if (linear) {
            assert(before.size() == 1024 && after.size() == 8);
            assert(after.front() == Range(0x100000, 256 * 1024));
            if (!epoch) std::printf("GPU_DIRTY_GATHER_HOST_PASS contiguous_bytes=2097152 callbacks=%zu->%zu\n",
                                    before.size(), after.size());
        }
    }
}
int main() {
    Ranges sequential;
    for (PAddr a = 0x100000; a < 0x300000; a += 2048) sequential.emplace_back(a, 2048);
    Check(sequential, true);
    Check({{0, 2048}, {2048, 2048}, {4096, 2048}});
    Check({{0x1000, 64}, {0x1080, 64}, {0x17c0, 64}, {0x1800, 64},
           {0x2000, 64}, {0x1000, 192}, {0x800, 2048}, {0x4000, 2048}});
    Ranges scattered;
    std::uint64_t state = 0x516784352;
    for (unsigned i = 0; i < 8192; ++i) {
        state ^= state << 13; state ^= state >> 7; state ^= state << 17;
        const PAddr base = ((state >> 11) % 64) * 2048;
        const auto offset = state % 2048;
        const auto size = 1 + (state >> 32) % (2048 - offset);
        scattered.emplace_back(base + offset, size);
    }
    Check(scattered);
    // Writes arriving from a callback belong to the next Gather epoch.
    Core::GPUDirtyMemoryManager current;
    current.Collect(0x2000, 2048); current.Collect(0x2800, 2048);
    unsigned calls = 0;
    std::function<void(PAddr, std::size_t)> callback = [&](PAddr a, std::size_t n) {
        assert(a == 0x2000 && n == 4096); ++calls;
        current.Collect(0x3000, 64);
    };
    current.Gather(callback);
    assert(calls == 1);
    assert((Gather(current) == Ranges{{0x3000, 64}}));
    assert(Gather(current).empty());
    std::puts("GPU_DIRTY_GATHER_COVERAGE_PASS randomized=8192 gaps=preserved order=preserved epochs=isolated");
}
'''
compiler = shutil.which('clang++-18') or shutil.which('clang++') or shutil.which('g++')
assert compiler, 'C++20 compiler needed'
with tempfile.TemporaryDirectory(prefix='encore-dirty-gather-') as temp:
    folder = Path(temp)
    (folder / 'core').mkdir()
    (folder / 'core/device_memory_manager.h').write_text(
        '#pragma once\n#include <cstddef>\n#include <cstdint>\n'
        'using PAddr=std::uint64_t; using u32=std::uint32_t; using u64=std::uint64_t;\n'
        'namespace Core { inline constexpr std::size_t DEVICE_PAGEBITS=12; }\n'
        'namespace PreviousCore { inline constexpr std::size_t DEVICE_PAGEBITS=12; }\n')
    (folder / 'core/gpu_dirty_memory_manager.h').write_bytes(active.read_bytes())
    (folder / 'previous.h').write_text(pinned.replace('namespace Core {', 'namespace PreviousCore {'))
    unit, binary = folder / 'main.cpp', folder / 'gather'
    unit.write_text(fixture)
    subprocess.run([compiler, '-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-I' + str(folder), str(unit), '-o', str(binary)], check=True, timeout=60)
    subprocess.run([str(binary)], check=True, timeout=30)
print('GPU_DIRTY_GATHER_HOST_ONLY console_timing=unverified')
