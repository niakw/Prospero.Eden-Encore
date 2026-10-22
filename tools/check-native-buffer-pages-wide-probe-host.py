#!/usr/bin/env python3
"""Source-selected buffer-page bitmap guard: two-word 256 KiB guest writes."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
head = (root / "headless/buffer_pages.h").read_text()
assert "size>256*1024" in head
assert "size>64*1024" not in head
assert "const auto first_word=first/64,last_word=last/64;" in head
assert "registered[first_word].load(std::memory_order_acquire)&first_mask" in head
assert "registered[last_word].load(std::memory_order_acquire)&Bits(0,last%64)" in head
assert "coverage_unknown.load(std::memory_order_acquire)" in head

code = r"""
#include "buffer_pages.h"
#include <cassert>
#include <cstdint>
int main() {
    using namespace Eden::BufferPages;
    constexpr std::uint64_t page = 4096;
    constexpr std::uint64_t span = 256 * 1024;
    // A 256 KiB unaligned query can cross a 64-page bitmap word boundary,
    // but may only cover two words. No owner means lock elision is valid.
    constexpr std::uint64_t cross = 63 * page + 17;
    assert(NeverRegistered(cross, span));
    assert(NeverRegistered(cross, 64 * 1024 + 1));
    // The immediately preceding byte is NOT part of the query.
    Mark(cross - page, 1);
    assert(NeverRegistered(cross, span));
    // A newly registered interior page must disable lock elision.
    Mark(64 * page + 48, 1);
    assert(!NeverRegistered(cross, span));
    // Unrelated ranges must keep the fast path.
    constexpr std::uint64_t empty = 512 * page + 29;
    assert(NeverRegistered(empty, span));
    Mark(empty + span - 1, 1);
    assert(!NeverRegistered(empty, span));
    assert(NeverRegistered(empty + span + page, 64 * 1024));
    // Check a near-maximum query whose final page is across the word split.
    constexpr std::uint64_t shifted = 1023 * page + 2;
    assert(NeverRegistered(shifted, span));
    Mark(shifted + span - 1, 1);
    assert(!NeverRegistered(shifted, span));
    assert(NeverRegistered(shifted + span, page));
    // Larger requests preserve the old conservative locking behavior.
    assert(!NeverRegistered(empty + 20 * span, span + 1));
    assert(!NeverRegistered(empty + 20 * span, 0));
    assert(!NeverRegistered(kSpace - 4096, 8192));
    assert(!NeverRegistered(kSpace, 1));
    assert(!coverage_unknown.load(std::memory_order_acquire));
}
"""
compiler=shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-buffer-probe-") as folder:
    path=Path(folder)/"probe.cpp"
    path.write_text(code)
    for mode in ("-O0", "-O2"):
        exe=Path(folder)/("probe"+mode)
        subprocess.run([compiler,"-std=c++20",mode,"-Wall","-Wextra","-Werror",
                        "-fsanitize=undefined", "-I"+str(root/"headless"),
                        str(path),"-o",str(exe)],check=True,timeout=40)
        subprocess.run([str(exe)],check=True,timeout=20)
        print("BUFFER_PAGES_WIDE_PROBE_HOST_PASS",mode)
