#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""R01 source-aware checks for the real Vulkan feature-branch frame counter.

Does not claim emulator guest FPS, GPU frame time, game latency or HDMI scanout.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
hdr = (ROOT / "headless/frame_metrics.h").read_text()
render = (ROOT / "vendor/encore-active/eden-vulkan/vulkan_renderer.cpp").read_text()
present = (ROOT / "vendor/encore-active/eden-vulkan/vulkan_present_manager.cpp").read_text()
perf = (ROOT / "headless/performance.cpp").read_text()
main = (ROOT / "headless/main.cpp").read_text()
cmake = (ROOT / "headless/vulkan.cmake").read_text()
for name,src in [("renderer",render),("presenter",present),("performance",perf),("app",main)]:
    assert '#include "frame_metrics.h"' in src, name
assert 'target_include_directories(video_core PRIVATE "${PORT_BUILD_DIR}" "${EDEN_PORT_DIR}")' in cmake
assert '"${PORT_BUILD_DIR}/vulkan_renderer.cpp"' in cmake
assert '"${PORT_BUILD_DIR}/vulkan_present_manager.cpp"' in cmake
composite = render.split("void RendererVulkan::Composite(", 1)[1].split("\nvoid RendererVulkan::PresentLoading()",1)[0]
assert composite.count("::Eden::FrameMetrics::OnSourceComposite();") == 1
assert composite.count("::Eden::FrameMetrics::OnSourceSkipped();") == 1
assert composite.count("::Eden::FrameMetrics::OnRealQueued();") == 1
assert composite.count("::Eden::FrameMetrics::OnGeneratedQueued();") == 1
assert composite.index("::Eden::Display::SkipFrame()") < composite.index("::Eden::FrameMetrics::OnSourceSkipped()")
assert composite.index("present_manager.Present(generated);") < composite.index("::Eden::FrameMetrics::OnGeneratedQueued()")
assert composite.index("present_manager.Present(frame);") < composite.index("::Eden::FrameMetrics::OnRealQueued()")
loading=render.split("void RendererVulkan::PresentLoading()",1)[1].split("void RendererVulkan::Report()",1)[0]
assert loading.index("present_manager.Present(frame);") < loading.index("::Eden::FrameMetrics::OnLoadingQueued();")
swap = present.split("void PresentManager::CopyToSwapchainImpl(",1)[1]
assert swap.index("swapchain.Present(render_semaphore);") < swap.index("::Eden::FrameMetrics::OnSwapchainPresentReturned();")
report=perf.split("void ReportGpuThread(unsigned frame)",1)[1]
assert report.index("if (!detailed_gpu_profile.load(std::memory_order_relaxed)) return;") < report.index("::Eden::FrameMetrics::Sample(")
assert 'scope=cpu_observed_not_guest_fps_not_scanout_not_latency' in report
assert main.count("Eden::FrameMetrics::ResetForTitle(deep_frame_profile,") == 1
assert 'Eden::Performance::detailed_gpu_profile.store(deep_frame_profile' in main
assert "if (Enabled())" in hdr and "if (!Enabled()) return {};" in hdr

src = ROOT / "extras/graphics/test_frame_metrics.cpp"
for opt in ("-O0","-O2"):
    with tempfile.TemporaryDirectory(prefix="encore-r01-metrics-") as temp:
        binary=Path(temp)/"frame_metrics"
        subprocess.run([os.environ.get("CXX","g++"), "-std=c++20",opt,
                        "-Wall","-Wextra","-Werror","-pthread",
                        "-fsanitize=undefined","-fno-sanitize-recover=all",
                        str(src),"-o",str(binary)],check=True)
        subprocess.run([str(binary)],check=True)
        print(f"R01_VULKAN_FRAME_METRICS_PASS {opt} sample_30_to_60=1 "
              "source_queued_present_separate=1 non_simulation_fps=1 "
              "opt_in=1 session_reset=1", flush=True)
