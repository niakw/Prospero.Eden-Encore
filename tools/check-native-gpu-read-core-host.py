#!/usr/bin/env python3
"""Native GPU-read host-slot regression, without a console or full core build.

Compile the real pinned HandleRasterizerDownload function before and after
the exact CMake source patch, with minimal host-index and GPU callback stubs.
The original must fail under sanitizers for an auxiliary host ID; the native
variant must preserve guest-core caching and isolate scratch across threads.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
upstream = (root / "vendor/sources/eden/src/core/memory.cpp").read_text()
kernel = (root / "vendor/sources/eden/src/core/hle/kernel/kernel.cpp").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()

old = """        const size_t core = system.GetCurrentHostThreadID();
        auto& current_area = rasterizer_read_areas[core];
        gpu_device_memory->ApplyOpOnPointer(p, scratch_buffers[core], [&](DAddr address) {"""
native = """        const size_t host_core = system.GetCurrentHostThreadID();
        thread_local Common::ScratchBuffer<u32> read_scratch;
        VideoCore::RasterizerDownloadArea auxiliary_read_area{};
        auto& current_area = host_core < Core::Hardware::NUM_CPU_CORES
            ? rasterizer_read_areas[host_core] : auxiliary_read_area;
        gpu_device_memory->ApplyOpOnPointer(p, read_scratch, [&](DAddr address) {"""
method_start = "    void HandleRasterizerDownload(VAddr v_address, size_t size) {"
method_end = "    void HandleRasterizerWrite(VAddr v_address, size_t size) {"
assert upstream.count(method_start) == 1 and upstream.count(method_end) == 1
method = method_start + upstream.split(method_start, 1)[1].split(method_end, 1)[0]
assert method.count(old) == 1
assert cmake.count("set(eden_read_original [=[") == 1
assert cmake.count("set(eden_read_native [=[") == 1
assert cmake.count('string(REPLACE "${eden_read_original}" "${eden_read_native}"') == 1
assert cmake.count("Pinned native guest CPU read scratch/slot contract changed") == 1
assert native in cmake and old in cmake
assert 'return tls_data.host_thread_id;' in kernel
assert 'tls_data.host_thread_id = u8(core_id);' in kernel
assert 'if (core_id >= Core::Hardware::NUM_CPU_CORES)' in kernel
assert "python3 -B tools/check-native-gpu-read-core-host.py" in workflow

cpp = r"""
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <thread>
#include <vector>

using u8 = std::uint8_t;
using u32 = std::uint32_t;
using VAddr = std::uint64_t;
using DAddr = std::uint64_t;
namespace Core::Hardware { constexpr std::size_t NUM_CPU_CORES = 4; }
namespace VideoCore {
struct RasterizerDownloadArea {
    DAddr start_address{};
    DAddr end_address{};
    bool preemtive{};
};
}
namespace Common {
template <class T> struct ScratchBuffer {
    std::atomic<unsigned> active{};
};
}
static thread_local std::size_t tls_host_core = 255;
struct FakeGpu {
    std::atomic<unsigned> downloads{};
    VideoCore::RasterizerDownloadArea OnCPURead(DAddr address, std::size_t) {
        downloads.fetch_add(1, std::memory_order_relaxed);
        return {address, address + 64, true};
    }
};
struct FakeDeviceMemory {
    template <class Callback>
    void ApplyOpOnPointer(const u8*, Common::ScratchBuffer<u32>& scratch, Callback&& cb) {
        assert(scratch.active.fetch_add(1, std::memory_order_acq_rel) == 0);
        std::this_thread::yield();
        cb(0x12000);
        assert(scratch.active.fetch_sub(1, std::memory_order_release) == 1);
    }
};
struct FakeHost1x {
    FakeDeviceMemory manager;
    FakeDeviceMemory& MemoryManager() { return manager; }
};
struct FakeSystem {
    FakeHost1x host;
    FakeGpu gpu;
    std::size_t GetCurrentHostThreadID() const { return tls_host_core; }
    FakeHost1x& Host1x() { return host; }
    FakeGpu& GPU() { return gpu; }
};
struct Fixture {
    FakeSystem& system;
    FakeDeviceMemory* gpu_device_memory;
    std::array<VideoCore::RasterizerDownloadArea, Core::Hardware::NUM_CPU_CORES>
        rasterizer_read_areas{};
    std::array<Common::ScratchBuffer<u32>, Core::Hardware::NUM_CPU_CORES>
        scratch_buffers{};
    u8 data{};
    explicit Fixture(FakeSystem& s) : system(s), gpu_device_memory(&s.host.manager) {}
    template<class Miss, class Cached>
    const u8* GetPointerImpl(VAddr, Miss&&, Cached&&) { return &data; }
@@METHOD@@
};

int main(int argc, char**) {
    FakeSystem sys;
    Fixture memory{sys};
    if (argc > 1) {
        tls_host_core = 255;  // Auxiliary host thread, outside four guest slots.
        memory.HandleRasterizerDownload(0x2000, 4);
        return 0;
    }
    tls_host_core = 2;
    memory.HandleRasterizerDownload(0x2000, 4);
    memory.HandleRasterizerDownload(0x2000, 4);
    assert(sys.gpu.downloads.load() == 1); // Guest core 2 cache preserved.
    tls_host_core = 3;
    memory.HandleRasterizerDownload(0x2000, 4);
    memory.HandleRasterizerDownload(0x2000, 4);
    assert(sys.gpu.downloads.load() == 2); // System guest core preserved.

    // Eight foreign host threads may all read while guest-core 3 uses its
    // separate slot. Each auxiliary must perform its OWN GPU read fence:
    // a cached flush range from another host thread is never inherited.
    std::vector<std::thread> threads;
    for (unsigned i = 0; i < 8; ++i) {
        threads.emplace_back([&, i] {
            tls_host_core = (i % 2 == 0) ? 4 : 255;
            memory.HandleRasterizerDownload(0x2000, 4);
            memory.HandleRasterizerDownload(0x2000, 4);
        });
    }
    for (auto& worker : threads) worker.join();
    assert(sys.gpu.downloads.load() == 18);
}
"""
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang C++20 is required"
with tempfile.TemporaryDirectory(prefix="encore-guest-gpu-read-") as tmp:
    root_dir = Path(tmp)
    for label, body, fixed in (
        ("pinned", method, False),
        ("native", method.replace(old, native), True),
    ):
        unit = root_dir / (label + ".cpp")
        binary = root_dir / label
        unit.write_text(cpp.replace("@@METHOD@@", body))
        subprocess.run(
            [clang, "-std=c++20", "-D_GLIBCXX_ASSERTIONS", "-O1", "-g", "-Wall", "-Wextra",
             "-Werror", "-pthread", "-fsanitize=address,undefined",
             "-fno-sanitize-recover=all", str(unit), "-o", str(binary)],
            check=True, timeout=45
        )
        if fixed:
            subprocess.run([str(binary)], check=True, timeout=45)
        else:
            bad = subprocess.run(
                [str(binary), "--foreign-host"], capture_output=True,
                text=True, timeout=45
            )
            assert bad.returncode != 0, "Pinned auxiliary read unexpectedly succeeded"
            assert ("Assertion" in bad.stderr or "runtime error" in bad.stderr
                    or "AddressSanitizer" in bad.stderr), bad.stderr

print("NATIVE_GPU_READ_CORE_HOST_PASS pinned_foreign_index_checked=1 native_aux_isolated=8 guest_core_cache=2 gpu_fence_no_shared_scratch=1")
