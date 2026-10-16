#!/usr/bin/env python3
"""Source-backed PS5 compute GPU descriptor overflow wait must precede guest cache mutexes."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
raster = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_update_descriptor.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()

compute = raster.split("void RasterizerVulkan::DispatchCompute() {", 1)[1].split(
    "\nvoid RasterizerVulkan::ResetCounter(", 1)[0]
preflight = "guest_descriptor_queue.PreflightGuestDraw([this] { scheduler.WaitWorker(); })"
select = "pipeline_cache.CurrentComputePipeline()"
locks = "std::scoped_lock lock{texture_cache.mutex, buffer_cache.mutex};"
assert compute.count(preflight) == 1
assert compute.index("gpu_memory->FlushCaching();") < compute.index(preflight)
assert compute.index(preflight) < compute.index(select) < compute.index(locks)
after = compute[compute.index(preflight):compute.index(select)]
assert after.count("gpu_memory->FlushCaching();") == 1
assert "if (" + preflight in compute
assert "ComputePipeline::Configure" not in after
assert "if (!pipeline)" in compute[compute.index(select):compute.index(locks)]
assert "Compute Configure runs under both guest cache locks" in generator
assert generator.count("Compute Configure runs under both guest cache locks") == 1
assert "python3 -B tools/check-ps5-compute-guest-descriptor-preflight-host.py" in workflow

start = "    template <typename WaitWorker>\n    [[nodiscard]] bool PreflightGuestDraw("
end = "    template <typename WaitWorker>\n    [[nodiscard]] bool PreflightLargeGuestDraw("
assert header.count(start) == header.count(end) == 1
method = header[header.index(start):header.index(end)]
assert "wait_worker();" in method
assert "payload_cursor = payload_start;" in method

cpp = r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
struct Queue {
    static constexpr size_t frame_payload_size=4096;
    std::array<uint64_t,frame_payload_size> entries{};
    uint64_t* payload_start=entries.data();
    uint64_t* payload_cursor=entries.data();
__METHOD__
    void SetUsed(size_t n) { assert(n < frame_payload_size); payload_cursor=payload_start+n; }
    size_t Used() const { return size_t(payload_cursor-payload_start); }
};
int main() {
    Queue queue;
    int waits=0;
    bool cache_locks_held=false;
    auto wait_worker=[&] { assert(!cache_locks_held); ++waits; };
    // Common dispatch with plenty of descriptor space adds no GPU wait.
    queue.SetUsed(100);
    assert(!queue.PreflightGuestDraw(wait_worker));
    assert(queue.Used()==100 && waits==0);
    // The exact 0x400 reservation threshold must drain before lock acquire.
    queue.SetUsed(4096-0x400);
    assert(queue.PreflightGuestDraw(wait_worker));
    assert(queue.Used()==0 && waits==1);
    cache_locks_held=true;
    assert(queue.Used()+0x400<queue.frame_payload_size);
    cache_locks_held=false;
    // Repeated ordinary dispatches do not introduce new drains.
    assert(!queue.PreflightGuestDraw(wait_worker));
    assert(waits==1);
    // Close to the end also drains; no double wait in the simulated Acquire.
    queue.SetUsed(4095);
    assert(queue.PreflightGuestDraw(wait_worker));
    assert(queue.Used()==0 && waits==2);
}
""".replace("__METHOD__", method)
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler, "Clang is required for sanitizer regression"
with tempfile.TemporaryDirectory(prefix="encore-compute-descriptor-") as folder:
    source=Path(folder)/"compute.cpp"
    binary=Path(folder)/"compute"
    source.write_text(cpp)
    subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(source),"-o",str(binary)],check=True,timeout=45)
    subprocess.run([str(binary)],check=True,timeout=30)
print("COMPUTE_DESCRIPTOR_PREFLIGHT_HOST_PASS ordinary_no_wait=1 boundary=1 outside_locks=1 refresh_before_selection=1")
