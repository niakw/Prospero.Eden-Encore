#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-only, sanitizer-backed regressions for conservative registered-buffer write ahead.

No console binary, guest memory or graphics pipeline is touched by this test.
"""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = root / 'headless/buffer_write_ahead.h'
generator = (root / 'tools/prepare-vulkan-port.py').read_text()
policy = (root / 'headless/performance.h').read_text()
settings = (root / 'headless/main.cpp').read_text()
assert header.is_file()
assert 'BufferWriteAhead::MarkFollowingPages' in generator
assert 'buffer_cache.IsRegionRegistered' in generator
assert 'buffer_cache.OnCPUWrite' in generator
assert 'cpu_write_ahead' in policy and 'cpu_write_ahead' in settings
assert 'cpu_write_ahead{0}' in policy  # Unproven on the actual title: default off.

code = r'''
#include "buffer_write_ahead.h"
#include <cassert>
#include <cstdint>
#include <set>
#include <vector>
using Eden::BufferWriteAhead::MarkFollowingPages;
int main() {
    std::set<std::uint64_t> registered{4096,8192,12288,16384,20480,24576};
    std::set<std::uint64_t> gpu_modified{16384};
    std::vector<std::uint64_t> touched;
    auto covers = [&](std::uint64_t a, std::uint64_t n) {
        assert(n == 4096);
        return registered.contains(a);
    };
    auto write = [&](std::uint64_t a, std::uint64_t n) {
        assert(n == 4096);
        touched.push_back(a);
        return gpu_modified.contains(a);  // true: GPU owns the page, stop.
    };
    assert(MarkFollowingPages(64, 128, 0, covers, write) == 0 && touched.empty());
    assert(MarkFollowingPages(64, 128, 64, covers, write) == 3);
    assert((touched == std::vector<std::uint64_t>{4096,8192,12288,16384}));
    touched.clear();
    assert(MarkFollowingPages(64, 4096, 64, covers, write) == 2);
    assert((touched == std::vector<std::uint64_t>{8192,12288,16384}));
    touched.clear();
    assert(MarkFollowingPages(24576, 2, 64, covers, write) == 0 && touched.empty());
    assert(MarkFollowingPages(0, 0, 64, covers, write) == 0 && touched.empty());
    assert(MarkFollowingPages(UINT64_MAX-1, 20, 64, covers, write) == 0 && touched.empty());
    assert(MarkFollowingPages(UINT64_MAX-4097, 2, 64, covers, write) == 0 && touched.empty());
    registered.clear(); gpu_modified.clear();
    for(unsigned i=1;i<200;++i) registered.insert(std::uint64_t(i)*4096);
    assert(MarkFollowingPages(0, 1, 500, covers, write) == 64); // hard cap
    assert(touched.size() == 64);
    touched.clear();
    registered.erase(8192);
    assert(MarkFollowingPages(0, 1, 64, covers, write) == 1);
    assert((touched == std::vector<std::uint64_t>{4096}));
}
'''
with tempfile.TemporaryDirectory(prefix='encore-buffer-write-') as directory:
    cpp = Path(directory) / 'check.cpp'
    binary = Path(directory) / 'check'
    cpp.write_text(code)
    compiler = os.getenv('CXX', 'clang++')
    subprocess.run([compiler, '-std=c++20', '-O1', '-g', '-Wall', '-Wextra',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-I', str(header.parent), str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('BUFFER_WRITE_AHEAD_HOST_PASS default_off=1 page_alignment=1 stop_at_gpu_owned=1 overflow=1 cap=64')
