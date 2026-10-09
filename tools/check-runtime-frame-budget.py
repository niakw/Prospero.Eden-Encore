#!/usr/bin/env python3
"""Universal shipping hot-path guards: no hidden work each presentation.

This checks important source-level contracts, not actual PS5 FPS. Real hardware
measurements remain necessary before claiming any freeze or lag is solved.
"""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
def read(p): return (root / p).read_text()

graphics = read("headless/graphics.cpp")
display = read("headless/display_refresh.h")
main = read("headless/main.cpp")
header = read("headless/graphics.h")
textures = read("headless/prosperoeden/pe/ui/textures.cpp")
texture_header = read("headless/prosperoeden/pe/ui/textures.hpp")
widgets = read("headless/prosperoeden/pe/ui/widgets.cpp")
home = read("headless/prosperoeden/pe/ui/home.cpp")
nav = read("headless/prosperoeden/pe/ui/launcher.cpp")
widgets_header = read("headless/prosperoeden/pe/ui/widgets.hpp")

# Both renderers only query system perf statistics and format HUD glyphs when
# users actually turned on the FPS overlay. Game presentation still counts.
assert graphics.count("if (hud_enabled.load(std::memory_order_relaxed)) {") >= 2
assert graphics.count("GetAndResetPerfStats()") >= 2
assert "vulkan_hud = MakeHudSnapshot(vulkan_hud_clock, vulkan_hud_speed);" in graphics
assert "const auto text = FormatHudText(clock, speed_percent, \"OGL\");" in graphics
assert "No periodic performance-stat reset" in graphics

# A denied PS5 HideSplashScreen call cannot re-run/log once per frame.
assert "bool splash_hide_attempted{};" in header
assert "if (vulkan && !splash_hide_attempted)" in graphics
assert "splash_hide_attempted = true;" in graphics
assert "if (vulkan && !splash_hidden)" not in graphics

# Every image load attempt spends budget, even missing downloads/invalid files.
# This prevents an arbitrary number of file probes in one Home frame.
pump = textures[textures.index("void Textures::pump("):]
assert pump.index("--budget;") < pump.index("services_.load_image(entry.path, &image)")
assert pump.count("--budget;") == 1
assert "failed_loads = std::min(entry.failed_loads + 1u, 4u)" in textures
assert "retry_after = it->second.failed_loads <= 1 ? 0.45f" in textures
assert "unsigned failed_loads = 0;" in texture_header

# Both controller symbols use the same PS5-inspired shape; settings is a cog
# in the Home utility card and the top navigation.
assert "void settings_gear(" in widgets_header
assert "void dualsense_icon(" in widgets_header
assert "void settings_gear(Canvas &c" in widgets
assert "void dualsense_icon(Canvas &c" in widgets
assert "dualsense_icon(c, r, ink" in widgets
assert "dualsense_icon(c, {left - 2.0f" in home
assert "settings_gear(c, left + 12.0f" in home
assert "settings_gear(c, gx, gy" in nav

# A 120/240fps game on a 60/120Hz PS5 output may skip a frame, but
# that timestamp must be per-session and safe across renderer workers.
assert "inline std::atomic<long long> last_shown_frame_ns{0};" in display
assert "inline void ResetSkipFrameTracking() noexcept" in display
assert "last_shown_frame_ns.store(0, std::memory_order_relaxed);" in display
assert "last_shown_frame_ns.compare_exchange_weak(" in display
assert "previous > now_ns" in display
assert "static long long last_shown_ns" not in display
assert "Eden::Display::ResetSkipFrameTracking();" in main
assert "Eden::Display::skipped_frames.store(0);" not in main

print("All-game GPU/HUD hotpath, PS5 splash one-shot, Nlib frame budget, native icons and atomic frame-skip tracking: SOURCE PASS")
