#!/usr/bin/env python3
"""Validate actual maintained A32/A64 JIT invalidation bodies under ASan/UBSan.

A zero extent is a no-op; an unrepresentable end conservatively clears the cache.
Host contract only: this is not a game or native-console performance measurement.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / "vendor/encore-active/eden-core"
FILES = {
    "a32": OWNER / "src/dynarmic/backend/x64/a32_interface_native.cpp",
    "a64": OWNER / "src/dynarmic/backend/x64/a64_interface_standard.cpp",
    "shared": OWNER / "src/dynarmic/backend/x64/a64_interface_shared.cpp",
    "shared_owner": OWNER / "dynarmic/shared-jit/jit_impl.inc",
    "legacy_a32": ROOT / "vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64/a32_interface.cpp",
    "legacy_a64": ROOT / "vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64/a64_interface.cpp",
}

def extract_method(path):
    text = path.read_text()
    begin = text.index("    void InvalidateCacheRange(")
    opening = text.index("{", begin)
    depth = 0
    for end in range(opening, len(text)):
        if text[end] == "{":
            depth += 1
        elif text[end] == "}":
            depth -= 1
            if depth == 0:
                return text[begin:end + 1]
    raise AssertionError("Unclosed invalidation function: " + str(path))

CPP = r"""
#include <cstdint>
#include <cstddef>
#include <limits>
#include <mutex>
#include <utility>
#include <vector>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
namespace boost::icl {
template<class T> struct discrete_interval {
    T begin, end;
    static auto closed(T a, T b) { return discrete_interval{a, b}; }
};
}
template<class T> struct RangeStore {
    std::vector<std::pair<T,T>> values;
    void add(boost::icl::discrete_interval<T> v) { values.emplace_back(v.begin, v.end); }
};
enum class HaltReason { CacheInvalidation };
struct Probe {
    std::mutex invalidation_mutex;
    bool invalidate_entire_cache = false;
    unsigned halt_count = 0;
    RangeStore<ADDR> invalid_cache_ranges;
    void HaltExecution(HaltReason) { ++halt_count; }
METHOD
};
int main() {
    const ADDR max_address = std::numeric_limits<ADDR>::max();
    {
        Probe p;
        p.InvalidateCacheRange(ADDR(0), 0);
        p.InvalidateCacheRange(max_address, 0);
        if (p.halt_count || p.invalidate_entire_cache || !p.invalid_cache_ranges.values.empty()) return 1;
    }
    {
        Probe p;
        p.InvalidateCacheRange(ADDR(0x100), 4);
        if (p.halt_count != 1 || p.invalidate_entire_cache || p.invalid_cache_ranges.values.size() != 1 ||
            p.invalid_cache_ranges.values[0] != std::make_pair(ADDR(0x100), ADDR(0x103))) return 2;
    }
    {
        Probe p;
        p.InvalidateCacheRange(max_address - 1, 2);
        if (p.halt_count != 1 || p.invalidate_entire_cache || p.invalid_cache_ranges.values.size() != 1 ||
            p.invalid_cache_ranges.values[0] != std::make_pair(ADDR(max_address - 1), max_address)) return 3;
    }
    {
        Probe p;
        p.InvalidateCacheRange(max_address - 1, 3);
        if (p.halt_count != 1 || !p.invalidate_entire_cache || !p.invalid_cache_ranges.values.empty()) return 4;
    }
    {
        Probe p;
        p.InvalidateCacheRange(ADDR(2), std::numeric_limits<std::size_t>::max());
        if (p.halt_count != 1 || !p.invalidate_entire_cache || !p.invalid_cache_ranges.values.empty()) return 5;
    }
    {
        Probe p;
        p.invalidate_entire_cache = true;
        p.InvalidateCacheRange(ADDR(0x100), 4);
        p.InvalidateCacheRange(max_address - 1, 3);
        if (p.halt_count != 2 || !p.invalidate_entire_cache || !p.invalid_cache_ranges.values.empty()) return 6;
    }
    {
        Probe p;
        p.InvalidateCacheRange(ADDR(0x100), 4);
        p.InvalidateCacheRange(max_address - 1, 3);
        p.InvalidateCacheRange(ADDR(0x200), 4);
        if (p.halt_count != 3 || !p.invalidate_entire_cache ||
            p.invalid_cache_ranges.values.size() != 1 ||
            p.invalid_cache_ranges.values[0] != std::make_pair(ADDR(0x100), ADDR(0x103))) return 7;
    }
    return 0;
}
"""

def exercise(label, method, addr_type, folder, compiler, expected_success):
    code = CPP.replace("ADDR", addr_type).replace("METHOD", method)
    source = folder / (label + ".cpp")
    binary = folder / label
    source.write_text(code)
    subprocess.run(
        [compiler, "-std=c++20", "-O1", "-fsanitize=address,undefined",
         "-fno-sanitize-recover=all", "-fno-omit-frame-pointer", str(source), "-o", str(binary)],
        check=True, timeout=90, capture_output=True, text=True)
    result = subprocess.run([str(binary)], timeout=20, capture_output=True, text=True)
    assert (result.returncode == 0) == expected_success, (
        label, result.returncode, result.stdout[-500:], result.stderr[-500:])

def main():
    compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
    assert compiler, "A C++20 compiler with ASan/UBSan is required"
    methods = {name: extract_method(path) for name, path in FILES.items()}
    assert methods["shared"] == methods["shared_owner"], "Shared JIT Impl does not match maintained output"
    assert methods["a64"] == methods["shared"], "Normal and experimental JIT range policies diverged"
    with tempfile.TemporaryDirectory(prefix="encore-jit-invalidate-") as tmp:
        folder = Path(tmp)
        for label, kind in (("a32", "u32"), ("a64", "u64"), ("shared", "u64")):
            exercise(label, methods[label], kind, folder, compiler, True)
        for label, kind in (("legacy_a32", "u32"), ("legacy_a64", "u64")):
            exercise(label, methods[label], kind, folder, compiler, False)
    print("ENCORE_JIT_INVALIDATION_EXTENTS_PASS a32=1 a64=1 shared=1 legacy_fail=2 asan_ubsan=1")

if __name__ == "__main__":
    main()
