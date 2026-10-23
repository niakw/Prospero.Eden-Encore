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
preflight = ("guest_descriptor_queue.PreflightGuestDraw([this] { scheduler.WaitWorker(); },\n"
             "                                                pipeline->DescriptorEntryReservation())")
select = "pipeline_cache.CurrentComputePipeline()"
locks = "std::scoped_lock lock{texture_cache.mutex, buffer_cache.mutex};"
assert compute.count(preflight) == 1
# The selected pipeline advertises an immutable descriptor count: select
# BEFORE preflight so an empty compute shader cannot wait for 1024 entries.
# Every real wait remains outside the paired guest buffer/texture mutexes.
first_select = compute.index("ComputePipeline* pipeline{" + select + "};")
first_preflight = compute.index(preflight)
first_lock = compute.index(locks)
assert compute.index("gpu_memory->FlushCaching();") < first_select < first_preflight < first_lock
assert ("if (pipeline->HasDescriptorEntries() &&\n        " + preflight) in compute
wait_guard_end = compute.index("#endif", first_preflight)
after = compute[first_preflight:wait_guard_end]
assert after.count("gpu_memory->FlushCaching();") == 1
assert after.count("pipeline = " + select + ";") == 1
assert "if (!pipeline) return;" in after
assert "if (!pipeline)" in compute[first_select:first_lock]
assert "ComputePipeline::Configure" not in after
# The generator must reproduce both the native guard and its oracle parity.
assert generator.count("Select first: descriptor-free compute dispatches") == 1
assert "Compute empty-descriptor native anchor changed" in generator
assert "python3 -B tools/check-ps5-compute-guest-descriptor-preflight-host.py" in workflow

start = "    template <typename WaitWorker>\n    [[nodiscard]] bool PreflightGuestDraw("
end = "    template <typename WaitWorker>\n    [[nodiscard]] bool PreflightExactGuestDraw("
assert header.count(start) == header.count(end) == 1
method = header[header.index(start):header.index(end)]
assert "wait_worker();" in method
assert "payload_cursor = payload_start;" in method
assert "size_t required_entries = 0x400" in method
assert "const size_t reserve = required_entries != 0 ? required_entries : 0x400;" in method
assert "pipeline->DescriptorEntryReservation()" in compute

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
    // The selected compute pipeline asks for its exact 8 entries rather
    // than 1024. A near-full but sufficient payload does NOT drain.
    queue.SetUsed(4096-9);
    assert(!queue.PreflightGuestDraw(wait_worker, 8));
    assert(queue.Used()==4096-9 && waits==1);
    // The 8-entry threshold drains exactly where Acquire would run out.
    queue.SetUsed(4096-8);
    assert(queue.PreflightGuestDraw(wait_worker, 8));
    assert(queue.Used()==0 && waits==2);
    // The default reservation remains available to other legacy callers.
    queue.SetUsed(4095);
    assert(queue.PreflightGuestDraw(wait_worker));
    assert(queue.Used()==0 && waits==3);
    // Reject invalid reservations without waiting or rewriting the cursor.
    queue.SetUsed(25);
    assert(!queue.PreflightGuestDraw(wait_worker,4096));
    assert(queue.Used()==25 && waits==3);
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
print("COMPUTE_DESCRIPTOR_PREFLIGHT_HOST_PASS ordinary_no_wait=1 boundary=1 outside_locks=1 select_before_preflight=1 reselection_after_wait=1")
