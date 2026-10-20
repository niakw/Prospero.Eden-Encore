#!/usr/bin/env python3
"""Source-extracted A32 window page bounds, including overflowing input spans."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "src/host_memory.cpp").read_text()
for constant in (
    "constexpr std::size_t GuestPage = 0x1000;",
    "constexpr std::size_t GuestPages = std::size_t{1} << 20;",
    "constexpr std::size_t WindowBytes = GuestPages * GuestPage;",
):
    assert constant in source, "requalify changed fastmem window dimensions"
begin = "    static bool Pages("
end = "\n    bool Aliasable("
assert source.count(begin) == source.count(end) == 1
method = begin + source.split(begin, 1)[1].split(end, 1)[0]
fixed = "last = (offset + std::min(length, WindowBytes - offset) - 1) / GuestPage;"
old = "last = (std::min(offset + length, WindowBytes) - 1) / GuestPage;"
assert method.count(fixed) == 1 and old not in method
baseline = method.replace(fixed, old)
cmake = (ROOT / "headless/CMakeLists.txt").read_text()
assert '"${PORT_ROOT}/src/host_memory.cpp"' in cmake
for name in ("Map", "Unmap", "Protect"):
    body = source.split("    void " + name + "(", 1)[1].split("\n    }", 1)[0]
    assert "if (!Pages(offset, length, first, last)) return;" in body
assert "python3 -B tools/check-fastmem-window-bounds-host.py" in (
    ROOT / ".github/workflows/encore-core-preflight.yml").read_text()

cpp = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <limits>
struct Window {
    static constexpr std::size_t GuestPage = 0x1000;
    static constexpr std::size_t GuestPages = std::size_t{1} << 20;
    static constexpr std::size_t WindowBytes = GuestPage * GuestPages;
METHOD
};
int main() {
    using W = Window;
    constexpr auto max = std::numeric_limits<std::size_t>::max();
    std::size_t first = 0, last = 0;
    assert(W::Pages(1, max, first, last));
    assert(first == 0 && last == W::GuestPages - 1);
    unsigned cases = 0;
    for (const auto offset : std::array<std::size_t, 10>{
             0, 1, 4095, 4096, 4097, W::WindowBytes - 4096,
             W::WindowBytes - 1, W::WindowBytes, W::WindowBytes + 1, max}) {
        for (const auto length : std::array<std::size_t, 9>{
                 0, 1, 2, 4095, 4096, 4097, W::WindowBytes, max - offset, max}) {
            first = last = 123;
            const bool valid = W::Pages(offset, length, first, last);
            assert(valid == (offset < W::WindowBytes && length != 0));
            if (valid) {
                assert(first == offset / W::GuestPage);
                assert(first <= last && last < W::GuestPages);
                // Independent oracle: clamp to the final page without adding
                // until the requested final byte is known to be in range.
                const auto expected = length - 1 >= W::WindowBytes - 1 - offset
                    ? W::GuestPages - 1 : (offset + length - 1) / W::GuestPage;
                assert(last == expected);
            } else {
                assert(first == 123 && last == 123);
            }
            ++cases;
        }
    }
    std::printf("FASTMEM_WINDOW_BOUNDS_PASS cases=%u full_span_no_overflow=1\n", cases);
}
"""
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-fastmem-bounds-") as temp:
    folder = Path(temp)
    for name, body in (("original", baseline), ("maintained", method)):
        path, executable = folder / (name + ".cpp"), folder / name
        path.write_text(cpp.replace("METHOD", body))
        subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        str(path), "-o", str(executable)], check=True, timeout=60)
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
        if name == "original":
            assert result.returncode != 0 and "Assertion" in result.stderr, result.stderr
            print("ORIGINAL_FASTMEM_WRAPPED_PAGE_WITNESS_PASS")
        else:
            assert result.returncode == 0, result.stderr
            print(result.stdout, end="")
print("FASTMEM_WINDOW_HOST_ONLY native_PS5=unverified")

# Execute the real Own/Refresh methods against distinct access/map arrays.
# The production caller holds the window mutex across these stable arrays.
own = '    std::uint8_t Own(' + source.split('    std::uint8_t Own(', 1)[1].split(
    "    // A page's byte", 1)[0]
own = own.replace('const {\n', 'const {\n        ++calls;\n', 1)
refresh_source = (ROOT / 'src/host_memory.cpp').read_text()
refresh = '    void Refresh(' + refresh_source.split('    void Refresh(', 1)[1].split(
    '    void Block(', 1)[0]
previous_refresh = '''    void Before(std::size_t first, std::size_t last) {
        for (std::size_t page = first ? first - 1 : 0; page <= last; ++page)
            map[page] = Own(page) | Own(page + 1);
    }
'''
constants = refresh_source.split('namespace {\nconstexpr std::size_t GuestPage', 1)[1].split(
    'constexpr std::uint64_t ProbeMarker', 1)[0]
constants = 'constexpr std::size_t GuestPage' + constants
constants = '\n'.join(line for line in constants.splitlines() if not line.startswith(
    ('constexpr std::size_t WindowBytes', 'constexpr std::size_t MapBytes', 'constexpr std::size_t ReserveBytes')))
refresh_cpp = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <utility>
#include <vector>
CONSTANTS
struct TestWindow {
    std::vector<std::uint8_t> chunk_aliased, page_access, bytes;
    std::uint8_t* map;
    mutable std::size_t calls = 0;
    TestWindow() : chunk_aliased(Chunks), page_access(GuestPages),
                   bytes(GuestPages, 0xa5), map(bytes.data()) {
        for (std::size_t c = 0; c < Chunks; ++c) chunk_aliased[c] = (c % 3) != 0;
        for (std::size_t p = 0; p < GuestPages; ++p) page_access[p] = p % 4;
    }
OWN
BEFORE
AFTER
};
int main() {
    TestWindow old, current;
    const std::array<std::pair<std::size_t, std::size_t>, 6> ranges{{
        {0, 0}, {1, 1}, {3, 12}, {GuestPages-1, GuestPages-1},
        {GuestPages-8, GuestPages-1}, {0, GuestPages-1}}};
    for (const auto& [first, last] : ranges) {
        std::fill(old.bytes.begin(), old.bytes.end(), 0xa5);
        std::fill(current.bytes.begin(), current.bytes.end(), 0xa5);
        old.calls = current.calls = 0;
        old.Before(first, last);
        current.Refresh(first, last);
        assert(old.bytes == current.bytes);
        const auto begin = first ? first - 1 : 0;
        const auto n = last - begin + 1;
        assert(old.calls == 2*n && current.calls == n+1);
        for (std::size_t p = begin; p <= last; ++p) {
            const auto expected = old.Own(p) | old.Own(p+1);
            assert(current.bytes[p] == expected);
        }
    }
    std::printf("FASTMEM_REFRESH_PASS whole_window_before=%zu after=%zu "
                "output_bytes_identical=1\n", 2*GuestPages, GuestPages+1);
}
'''.replace('CONSTANTS', constants).replace('OWN', own).replace(
    'BEFORE', previous_refresh).replace('AFTER', refresh)
with tempfile.TemporaryDirectory(prefix='encore-fastmem-refresh-') as temp:
    path, executable = Path(temp)/'refresh.cpp', Path(temp)/'refresh'
    path.write_text(refresh_cpp)
    subprocess.run([compiler, '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    str(path), '-o', str(executable)], check=True, timeout=60)
    subprocess.run([str(executable)], check=True, timeout=15)
