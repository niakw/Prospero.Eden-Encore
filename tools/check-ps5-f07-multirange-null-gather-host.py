#!/usr/bin/env python3
"""F07 source-extracted PS5 null gathered-buffer fallback and BDA safety.

The allocator may return an empty buffer without throwing. On PS5 the Get
path must return an empty ref before querying a null Vulkan buffer device
address or inserting an invalid cache entry. Desktop remains unchanged.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "vendor/encore-active/eden-vulkan/vk_multi_range_buffer_cost.cpp").read_text()
GEN = (ROOT / "tools/prepare-vulkan-port.py").read_text()
FAST = (ROOT / ".github/workflows/encore-core-fast-gate.yml").read_text()
PRE = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()
SELF = "python3 -B tools/check-ps5-f07-multirange-null-gather-host.py"
assert SELF in FAST and SELF in PRE
assert "F07 reject null native multirange gather before device-address query" in GEN

begin = SOURCE.index("MultiRangeRef MultiRangeBufferCache::Get(")
end = SOURCE.index("\nvoid MultiRangeBufferCache::MarkGathered(", begin)
body = SOURCE[begin:end]
guard = "#ifdef PS5_NATIVE\n    // A failed gathered fallback"
query = "    if (device.IsBufferDeviceAddressSupported()) {"
finish = "    MultiRangeRef ref{"
assert body.count(guard) == 1 and body.count(finish) == 2  # cache-hit and new-entry refs
assert body.count(query) == 2  # usage flags before allocation, then BDA
first = body.index(guard)
last = body.index(finish, first)
fragment = body[first:last]
assert "if (!entry.sparse_handle && !entry.gathered)" in fragment
assert fragment.index("return MultiRangeRef{};") < fragment.index(query)
assert body.index("entries.emplace(key, std::move(entry));") > last
assert body.index("entry.gathered = memory_allocator.CreateBuffer(") < first

program = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
using u64 = std::uint64_t;
using VkBuffer = u64;
struct Buffer {
    VkBuffer value{};
    explicit operator bool() const { return value != 0; }
    VkBuffer operator*() const { return value; }
};
struct MultiRangeRef { VkBuffer handle{}; };
struct Entry { Buffer sparse_handle{}, gathered{}; u64 address{}; };
struct Logical {
    int calls{};
    VkBuffer last{};
    u64 GetBufferDeviceAddress(VkBuffer h) {
        ++calls;
        last = h;
        return h + 100;
    }
};
struct Device {
    bool bda{};
    Logical logical{};
    bool IsBufferDeviceAddressSupported() const { return bda; }
    Logical& GetLogical() { return logical; }
};
MultiRangeRef Probe(Device& device, Entry& entry) {
__FRAGMENT__
    return MultiRangeRef{
        entry.sparse_handle ? *entry.sparse_handle : *entry.gathered
    };
}
int main() {
    Device d{true};
    Entry e{};
    auto r = Probe(d, e);
    assert(r.handle == 0);
#ifdef PS5_NATIVE
    assert(d.logical.calls == 0);
#else
    assert(d.logical.calls == 1 && d.logical.last == 0);
#endif
    Device g{true};
    Entry f{};
    f.gathered.value = 37;
    r = Probe(g, f);
    assert(r.handle == 37 && g.logical.calls == 1 &&
           g.logical.last == 37 && f.address == 137);
    Device s{true};
    Entry z{};
    z.sparse_handle.value = 83;
    r = Probe(s, z);
    assert(r.handle == 83 && s.logical.calls == 1 &&
           s.logical.last == 83 && z.address == 183);
    Device no{false};
    Entry none{};
    r = Probe(no, none);
    assert(r.handle == 0 && no.logical.calls == 0);
    std::puts("F07_MULTIRANGE_NULL_GATHER_FALLBACK_PASS");
}
""".replace("__FRAGMENT__", fragment)
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-multirange-null-") as folder:
    root = Path(folder)
    source = root / "fixture.cpp"
    source.write_text(program)
    for native in (False, True):
        for opt in ("-O0", "-O2"):
            exe = root / ("test" + opt + str(int(native)))
            build = subprocess.run(
                [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 *(["-DPS5_NATIVE=1"] if native else []),
                 str(source), "-o", str(exe)],
                capture_output=True, text=True, timeout=60)
            assert build.returncode == 0, (native, opt, build.stderr[-4000:])
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
            assert run.returncode == 0, (native, opt, run.stderr[-4000:])
print("F07_MULTIRANGE_NULL_GATHER_SOURCE_PASS PS5_desktop=1 O0_O2=1")
print("NO_PS5_FPS_PROOF")
