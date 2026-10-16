#!/usr/bin/env python3
"""Host regression for native memory GetSpan's exclusive-end page boundary.

Compile the actual two pinned GetSpan methods as the negative control and
the exact native CMake replacement as the positive control. No console build.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
memory = (root / "vendor/sources/eden/src/core/memory.cpp").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()

begin = "    [[nodiscard]] inline const u8* GetSpan("
end = "    bool WriteBlockImpl("
assert memory.count(begin) == 1 and memory.count(end) == 1
methods = begin + memory.split(begin, 1)[1].split(end, 1)[0]
old = (
    "        return (current_page_table->entries[addr >> YUZU_PAGEBITS].Block() "
    "== current_page_table->entries[(addr + size) >> YUZU_PAGEBITS].Block()) "
    "? GetPointerSilent(addr) : nullptr;"
)
assert methods.count(old) == 2
native_span_anchor = 'string(REPLACE "${eden_span_original}" [=['
assert cmake.count(native_span_anchor) == 1
span_start = cmake.index(native_span_anchor) + len(native_span_anchor)
span_end = cmake.index(']=] eden_cpu_memory "${eden_cpu_memory}")', span_start)
fixed = cmake[span_start:span_end]
assert cmake.count("Pinned native guest span page-boundary contract changed") == 1
assert "if (size == 0 || addr + (size - 1) < addr)" in fixed
assert "start_page >= entries.size() || end_page >= entries.size()" in fixed
assert cmake.count('set(eden_span_original [=[') == 1
assert "python3 -B tools/check-native-guest-span-host.py" in workflow

cpp = r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
using VAddr = std::uint64_t;
using u8 = std::uint8_t;
static constexpr auto YUZU_PAGEBITS = 12;
struct Entry {
    int block{};
    int Block() const { return block; }
};
struct PageTable {
    std::array<Entry, 2> entries{};
};
struct MemoryFixture {
    PageTable* current_page_table{};
    u8 dummy{};
    u8* GetPointerSilent(VAddr) const {
        return const_cast<u8*>(&dummy);
    }
@@METHODS@@
};
int main(int argc, char**) {
    PageTable pages;
    pages.entries[0].block = 11;
    pages.entries[1].block = 22;
    MemoryFixture fixture{&pages};
    const MemoryFixture& read = fixture;
    if (argc > 1) {
        // At exact end of page 0, original code consults page 1.
        assert(fixture.GetSpan(0, 4096) == nullptr);
        assert(read.GetSpan(0, 4096) == nullptr);
        return 0;
    }
    assert(fixture.GetSpan(0, 4096) != nullptr);
    assert(read.GetSpan(0, 4096) != nullptr);
    assert(fixture.GetSpan(4096, 4096) != nullptr);
    assert(read.GetSpan(4096, 4096) != nullptr);
    assert(fixture.GetSpan(4095, 1) != nullptr);
    assert(read.GetSpan(4095, 1) != nullptr);
    assert(fixture.GetSpan(4095, 2) == nullptr);
    assert(read.GetSpan(4095, 2) == nullptr);
    assert(fixture.GetSpan(0, 0) == nullptr);
    assert(read.GetSpan(0, 0) == nullptr);
    assert(fixture.GetSpan(8192, 1) == nullptr);
    assert(read.GetSpan(8192, 1) == nullptr);
    assert(fixture.GetSpan(UINT64_MAX, 2) == nullptr);
    assert(read.GetSpan(UINT64_MAX, 2) == nullptr);
}
"""
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang C++20 required"
with tempfile.TemporaryDirectory(prefix="encore-guest-span-") as tmp:
    work = Path(tmp)
    for label, text, negative in (
        ("pinned", methods, True),
        ("native", methods.replace(old, fixed), False),
    ):
        source = work / (label + ".cpp")
        binary = work / label
        source.write_text(cpp.replace("@@METHODS@@", text))
        subprocess.run(
            [clang, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
             "-Werror", "-D_GLIBCXX_ASSERTIONS", "-fsanitize=address,undefined",
             "-fno-sanitize-recover=all", str(source), "-o", str(binary)],
            check=True, timeout=45
        )
        command = [str(binary)] + (["--pinned"] if negative else [])
        subprocess.run(command, check=True, timeout=45)
print("NATIVE_GUEST_SPAN_HOST_PASS original_exact_boundary_false_negative=1 native_const_mutable=2 last_page=1 crossing=1 zero=1 overflow=1 out_of_bounds=1")
