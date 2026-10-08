#!/usr/bin/env python3
"""Shared PS5 performance policy and development-only tracing contracts.

The completed A/B/C/D campaign is preserved as history; user-facing runtime
no longer selects those experimental JIT tiers.
This source contract does NOT validate firmware performance.
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

assert "ChooseJitMemoryPlan(" in header
assert "ApplyJitMemoryPlan(" in header
assert "A64CacheBytes(" in header and "A32CacheBytes(" in header
assert "kSingleArenaAddressingLimit" in header
assert "kHostReserve" in header
assert "std::array<std::atomic<std::uint32_t>,4>" in header
assert "jit_cache_tier{0}" not in header

assert 'ConfigFile("experiments.json")' in main
assert "if (!safe_launch && launch_title_id)" in main
assert 'get("cpu_placement") == "logical"' in main
assert 'get("vulkan_pacing") == "trace"' in main
assert "EnableExperimentalLogicalPlacement();" in main
assert 'jit == "balanced"' not in main and 'jit == "expanded"' not in main
assert "ChooseJitMemoryPlan(" in main and "ApplyJitMemoryPlan(" in main

assert "A64CacheBytes(m_core_index" in cmake
assert "A32CacheBytes(m_core_index" in cmake
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

assert "0100C49025D3E000" in guide  # historical benchmark identifier only
assert "developer-build only" in guide
assert "Safe Launch" in guide
print("PS5 universal A64/A32 JIT budget and dev-only trace controls: source contracts PASS")
