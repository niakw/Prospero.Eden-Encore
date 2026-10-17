#!/usr/bin/env python3
"""Host regression: actual pinned A32/A64 read callbacks must honor abort checks."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
helper = root / "headless/native_jit_memory_read_guard.cmake"
cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert 'native_jit_memory_read_guard.cmake")' in cmake
assert "python3 -B tools/check-native-jit-memory-read-guard-host.py" in workflow
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler and shutil.which("cmake")

def method(src, token):
    assert src.count(token) == 1, token
    start = src.index(token)
    brace = src.index("{", start)
    depth = 0
    for i in range(brace, len(src)):
        if src[i] == "{":
            depth += 1
        if src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i+1]
    raise AssertionError(token)

prelude = """
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
using u8=std::uint8_t; using u16=std::uint16_t;
using u32=std::uint32_t; using u64=std::uint64_t;
namespace Kernel { enum class DebugWatchpointType {Read,Write}; }
namespace Dynarmic { namespace A64 { using Vector=std::array<u64,2>; } }
struct Memory {
    unsigned reads{};
    u8 Read8(u64) { ++reads; return 8; }
    u16 Read16(u64) { ++reads; return 16; }
    u32 Read32(u64) { ++reads; return 32; }
    u64 Read64(u64) { ++reads; return 64; }
};
namespace Core {
"""
with tempfile.TemporaryDirectory(prefix="encore-jit-reads-") as tmp:
    directory = Path(tmp)
    for bits in (32, 64):
        pinned = root / f"vendor/sources/eden/src/core/arm/dynarmic/arm_dynarmic_{bits}.cpp"
        original = pinned.read_text()
        derived = directory / f"derived-{bits}.cpp"
        cmake_script = directory / f"derive-{bits}.cmake"
        cmake_script.write_text(
            f'set(PS5_NATIVE ON)\nset(bits {bits})\n'
            f'file(READ "{pinned.as_posix()}" wrapper)\n'
            f'include("{helper.as_posix()}")\n'
            + f'file(WRITE "{derived.as_posix()}" "' + '$' + '{wrapper}' + '")\n'
        )
        subprocess.run(["cmake", "-P", str(cmake_script)], check=True, timeout=25)
        corrected = derived.read_text()
        widths = (8,16,32,64,128) if bits == 64 else (8,16,32,64)
        assert corrected.count("if (!CheckMemoryAccess(vaddr") == len(widths)
        for label, source, fixed in (("pinned",original,False),("fixed",corrected,True)):
            guest_addr = "u64" if bits == 64 else "u32"
            declarations = []
            definitions = []
            for width in widths:
                typ = "Dynarmic::A64::Vector" if width == 128 else f"u{width}"
                declarations.append(f"    {typ} MemoryRead{width}({guest_addr});")
                token = f"{typ} DynarmicCallbacks{bits}::MemoryRead{width}({guest_addr} vaddr) {{"
                definitions.append(method(source,token))
            cl = f"""struct DynarmicCallbacks{bits} {{
    bool allow{{true}}; unsigned checks{{}};
    Memory m_memory;
    bool CheckMemoryAccess(u64,u64,Kernel::DebugWatchpointType) {{
        ++checks; return allow;
    }}
""" + "\n".join(declarations) + "\n};\n"
            main = f"""
}} // namespace Core
int main() {{
    Core::DynarmicCallbacks{bits} c;
    assert(c.MemoryRead8(0)==8 && c.MemoryRead16(0)==16);
    assert(c.MemoryRead32(0)==32 && c.MemoryRead64(0)==64);
"""
            if bits == 64:
                main += "    auto good = c.MemoryRead128(0); assert(good[0]==64 && good[1]==64);\n"
            main += f"""
    unsigned before=c.m_memory.reads;
    assert(before=={6 if bits == 64 else 4});
    c.allow=false;
    auto r8=c.MemoryRead8(0); auto r16=c.MemoryRead16(0);
    auto r32=c.MemoryRead32(0); auto r64=c.MemoryRead64(0);
"""
            if bits == 64:
                main += "    auto r128=c.MemoryRead128(0);\n"
            main += f"""
    assert(c.checks=={10 if bits == 64 else 8});
#if EXPECT_FIXED
    assert(r8==0 && r16==0 && r32==0 && r64==0);
    assert(c.m_memory.reads==before);
"""
            if bits == 64:
                main += "    assert(r128[0]==0 && r128[1]==0);\n"
            main += """
#else
    assert(r8==8 && r16==16 && r32==32 && r64==64);
    assert(c.m_memory.reads==2*before);
    #if GUEST_BITS == 64
    assert(r128[0]==64 && r128[1]==64);
#endif
#endif
    std::puts(EXPECT_FIXED ? "PINNED_JIT_READ_ABORT_GUARD_PASS" :
                             "PINNED_JIT_READ_IGNORED_ABORT_NEGATIVE_PASS");
}
"""
            cpp = directory / f"{bits}-{label}.cpp"
            exe = directory / f"{bits}-{label}"
            cpp.write_text(prelude + cl + "\n".join(definitions) + main)
            subprocess.run(
                [compiler,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                 "-DEXPECT_FIXED="+str(int(fixed)), "-DGUEST_BITS="+str(bits),str(cpp),"-o",str(exe)],
                check=True,timeout=30)
            result=subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=10)
            print(f"A{bits}: "+result.stdout,end="")
print("NATIVE_JIT_READ_GUARD_HOST_ONLY_NOT_GAME_PROVEN")
