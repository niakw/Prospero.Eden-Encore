#!/usr/bin/env python3
"""Host-compile the exact A64/A32 startup allocation-retry header.

Use a minimal Xbyak v7-compatible exception shim, so this test works before
the pinned Eden/Xbyak vendor source is downloaded by native CI preparation.
Real PS5 direct-memory allocation and emulation are NOT exercised.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CXX = next((v for v in ("clang++-18", "clang++", "g++") if shutil.which(v)), None)
if not CXX:
    raise SystemExit("Missing C++20 compiler for startup fallback test")

XBYAK = r"""
#pragma once
#include <exception>
namespace Xbyak {
enum { ERR_CANT_ALLOC = 5, ERR_CODE_IS_TOO_BIG = 6 };
struct Error : std::exception {
    int code;
    explicit Error(int c) : code(c) {}
    operator int() const { return code; }
    const char* what() const noexcept override { return "test Xbyak error"; }
};
}
"""
CPP = r"""
#include <cassert>
#include <cstdint>
#include <stdexcept>
#include <vector>
#include "jit-startup-retry.h"
using Eden::JitStartup::ConstructWithCapacityFallback;
using Eden::JitStartup::NextCapacity;
constexpr std::uint32_t mib=1024u*1024u;
int main() {
    std::uint32_t size=1024u*mib;
    std::vector<std::uint32_t> attempts;
    ConstructWithCapacityFallback(size,256u*mib,64,0,[&] {
        attempts.push_back(size);
        if(size>256u*mib) throw Xbyak::Error(Xbyak::ERR_CANT_ALLOC);
    });
    assert((attempts==std::vector<std::uint32_t>{
        1024u*mib,768u*mib,576u*mib,432u*mib,324u*mib,256u*mib}));
    assert(size==256u*mib);
    std::uint32_t a32=512u*mib;
    int n=0;
    ConstructWithCapacityFallback(a32,64u*mib,32,1,[&] {
        ++n; if(a32>128u*mib) throw std::bad_alloc{};
    });
    assert(a32==128u*mib && n==6);
    // Close-to-baseline failure cannot loop or shrink below 2MiB floor.
    assert(NextCapacity(258u*mib,256u*mib)==256u*mib);
    assert(NextCapacity(320u*mib,192u*mib)==240u*mib);
    std::uint32_t unrelated=512u*mib;
    n=0;
    bool caught=false;
    try {
        ConstructWithCapacityFallback(unrelated,64u*mib,64,2,[&] {
            ++n; throw Xbyak::Error(Xbyak::ERR_CODE_IS_TOO_BIG);
        });
    } catch (const Xbyak::Error&) { caught=true; }
    assert(caught && n==1 && unrelated==512u*mib);
    caught=false;
    try {
        ConstructWithCapacityFallback(unrelated,64u*mib,64,2,[&] {
            throw std::runtime_error("not an allocator failure");
        });
    } catch (const std::runtime_error&) { caught=true; }
    assert(caught);
    // Null-JIT, already below its per-core fallback floor, must never retry.
    std::uint32_t small=8u*mib;
    n=0; caught=false;
    try {
        ConstructWithCapacityFallback(small,256u*mib,64,0,[&] {
            ++n; throw std::bad_alloc{};
        });
    } catch (const std::bad_alloc&) { caught=true; }
    assert(caught && n==1 && small==8u*mib);
    assert(NextCapacity(16u*mib,16u*mib)==16u*mib);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-jit-startup-") as directory:
    tmp=Path(directory)
    (tmp / "xbyak").mkdir()
    (tmp / "xbyak" / "xbyak.h").write_text(XBYAK)
    cpp=tmp / "check.cpp"
    exe=tmp / "check"
    cpp.write_text(CPP)
    subprocess.run([CXX,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
                    "-I",str(tmp),"-I",str(ROOT/"headless"),
                    str(cpp),"-o",str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("PASS Dynarmic JIT startup: quarter-step A64/A32 allocation fallback, fatal errors, null-JIT")
print("Full PS5 native build/hardware: NOT RUN")
