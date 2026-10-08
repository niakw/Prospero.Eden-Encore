#!/usr/bin/env python3
"""Static contracts for OFF-by-default PS5 performance experiments.

This does not compile PS5 code or demonstrate FPS gains on hardware.
"""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
read = lambda name: (root / name).read_text()
header = read("headless/experimental_performance.h")
main = read("headless/main.cpp")
cmake = read("headless/CMakeLists.txt")
cpu = read("headless/performance.cpp")
graphics = read("headless/graphics.cpp")
graphics_h = read("headless/graphics.h")
guide = read("docs/FC27_EXPERIMENTS.md")

assert "jit_cache_tier{0}" in header
assert "vulkan_frame_probe{false}" in header
assert "if (core >= 3) return baseline;" in header
assert "224u * mib" in header and "320u : 256u" in header
assert "return baseline;" in header

assert 'ConfigFile("experiments.json")' in main
assert "if (!safe_launch && launch_title_id)" in main
assert 'jit == "balanced" ? 1u : jit == "expanded" ? 2u : 0u' in main
assert 'get("cpu_placement") == "logical"' in main
assert 'get("vulkan_pacing") == "trace"' in main
assert "EnableExperimentalLogicalPlacement();" in main

assert "A64CacheBytes(m_core_index" in cmake
assert 'string(PREPEND wrapper "#include' in cmake
assert "experimental_performance.h" in cmake
assert 'option(EDEN_SHARED_JIT "Enable the experimental cross-core A64 JIT" OFF)' in cmake
assert 'option(EDEN_JIT_COMPILE_BATCH "Compile bounded A64 successor chains on a cache miss" OFF)' in cmake

assert "EnableExperimentalLogicalPlacementImpl" in cpu
assert "if (count < 7)" in cpu and "physical_verified=0" in cpu
assert "secondary_cpus = secondary;" in cpu

assert 'EDEN_EXPERIMENT_PRESENT' in graphics
assert "vulkan_frame_probe.load(std::memory_order_relaxed)" in graphics
assert "experimental_pacing_bins" in graphics_h
present = graphics.split("void GraphicsWindow::OnFrameDisplayed()", 1)[1].split(
    "void GraphicsWindow::CheckPresentation(", 1)[0]
assert "std::this_thread::sleep" not in present

assert "0100C49025D3E000" in guide
assert '"jit_cache": "balanced"' in guide
assert '"cpu_placement": "off"' in guide
assert "Safe Launch ignores" in guide
print("PS5 experimental JIT budgets, CPU fallback and Vulkan histogram: static contracts PASS")
