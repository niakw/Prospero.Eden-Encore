#!/usr/bin/env python3
"""R424: source/ownership contract for PS5 Vulkan presentation wait phases.

No new instrumentation in normal mode. This test complements the full
check-vendored-vulkan-fork.py source-equivalence generator preflight.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
header = (root / "headless/performance.h").read_text()
report = (root / "headless/performance.cpp").read_text()
presenter = (root / "vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()

for field in ("gpu_present_wait", "gpu_present_free_wait", "gpu_present_fence_wait"):
    assert field in header
assert "EDEN_PRESENT_WAIT_PHASE" in report
assert report.count("load(gpu_present_free_wait,") == 2
assert report.count("load(gpu_present_fence_wait,") == 2
assert "DiagnosticTimer present_wait_timer(::Eden::Performance::gpu_present_wait)" in presenter
assert "DiagnosticTimer free_wait(" in presenter
assert "DiagnosticTimer fence_wait(" in presenter
assert "gpu_present_free_wait" in generator
assert "gpu_present_fence_wait" in generator

begin = presenter.index("Frame* PresentManager::GetRenderFrame() {")
end = presenter.index("void PresentManager::Present(Frame* frame)", begin)
method = presenter[begin:end]
queue_start = method.index("std::unique_lock lock{free_mutex};")
queue_pop = method.index("free_queue.pop_front();")
queue_exit = method.index("\n    }\n", queue_pop)
fence_start = method.index("frame->present_done.Wait();")
fence_reset = method.index("frame->present_done.Reset();")
assert queue_start < queue_pop < queue_exit < fence_start < fence_reset
assert method.count("free_cv.wait(") == 1
assert method.count("frame->present_done.Wait();") == 1
assert method.count("frame->present_done.Reset();") == 1
assert method.count("if (present_failure) std::rethrow_exception(present_failure);") == 1
assert method.count("return frame;") == 1
assert "std::unique_lock lock{free_mutex};" in method
assert "free_queue.pop_front();" in method
assert "std::atomic" not in method
assert "std::this_thread::sleep_for" not in method
assert "while (" not in method
assert "if (!totals) return;" in header  # detail-only timer avoids quiet clocks
print("R424 present queue/fence diagnostic split: ownership and source contracts PASS")
