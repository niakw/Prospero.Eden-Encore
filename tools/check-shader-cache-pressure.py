#!/usr/bin/env python3
"""Host C++ test: preserve compiled shaders unless storage is short.

This tests the real header without invoking native PS5 filesystem calls.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
if compiler is None:
    raise SystemExit("Missing C++20 compiler for shader cache storage gate")

source = r"""
#include <cassert>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <system_error>
#include <vector>
#include "cache_budget.h"

int main(int argc, char** argv) {
    assert(argc == 2);
    namespace fs = std::filesystem;
    const fs::path dir = argv[1];
    fs::create_directories(dir);
    std::vector<fs::directory_entry> entries;

    // Only hex .bin records matching the native compiler naming convention
    // may be removed. Non-shader files are never touched.
    for (const char* name : {"abc.bin", "1234.bin", "notes.txt"}) {
        std::ofstream out(dir / name, std::ios::binary);
        out.seekp((4 * 1024 * 1024) - 1);
        out.put('X');
        out.close();
        entries.emplace_back(dir / name);
    }
    fs::last_write_time(dir / "abc.bin",
        fs::file_time_type::clock::now() - std::chrono::hours(24));

    constexpr auto mib = std::uintmax_t{1024} * 1024;
    // Plenty of free disk => no artificial 64 MiB shader cap / pruning.
    assert(Eden::TrimShaderCache(entries, 1024 * mib, 10 * 1024 * mib) == 0);
    assert(fs::exists(dir / "abc.bin") && fs::exists(dir / "1234.bin"));

    // Full-ish disk: leave 1 GiB free on a large filesystem. Only the
    // oldest cache file should be removed to cover a 4 MiB deficit.
    assert(Eden::TrimShaderCache(entries, 1020 * mib, 10 * 1024 * mib) == 1);
    assert(!fs::exists(dir / "abc.bin"));
    assert(fs::exists(dir / "1234.bin"));
    assert(fs::exists(dir / "notes.txt"));

    // Unknown space => never delete shader caches on an untrusted estimate.
    assert(Eden::TrimShaderCache(entries, std::uintmax_t(-1), std::uintmax_t(-1)) == 0);
}
"""

with tempfile.TemporaryDirectory(prefix="eden-shader-storage-") as temp:
    temp = Path(temp)
    cpp, exe = temp / "check.cpp", temp / "cache-test"
    cpp.write_text(source)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra",
                    "-Werror", "-I", str(root / "headless"),
                    str(cpp), "-o", str(exe)], check=True)
    subprocess.run([str(exe), str(temp / "records")], check=True)

print("PASS shader cache on-disk pressure: preserve, prune oldest, protect non-cache, fallback")
print("Native PS5 storage/syscall validation: NOT RUN")
