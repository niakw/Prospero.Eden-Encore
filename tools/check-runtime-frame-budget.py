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
frontend = read("headless/prosperoeden/frontend.cpp")
radio = read("headless/prosperoeden/radio_input.c")

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

# Async Nlib cover pipeline: never decode or scale on the navigation thread.
# One in-flight worker, at most one completed upload, bounded queue probes
# and bounded GPU texture reclamation on each frame.
pump = textures[textures.index("void Textures::pump("):]
assert "if (decode_.valid() &&" in pump
assert "decode_.wait_for(std::chrono::seconds(0)) == std::future_status::ready" in pump
assert "DecodedCover result = decode_.get();" in pump
assert "if (budget > 0 && !decode_.valid())" in pump
assert "inspected < kMaxCoverQueueLookupsPerFrame" in pump
assert "std::async(std::launch::async," in pump
assert "decoded.ok = services_.load_image(path, &decoded.image);" in pump
assert pump.index("std::async(std::launch::async,") < pump.index("decoded.ok = services_.load_image(path, &decoded.image);")
assert "entry.texture = create(result.image);" in pump
assert "deleted_this_frame < kMaxTextureReclaimsPerFrame" in pump
assert "failed_loads = std::min(entry.failed_loads + 1u, 4u)" in textures
assert "unsigned failed_loads = 0;" in texture_header
assert "std::future<DecodedCover> decode_;" in texture_header

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

# Native menu button events remain per-frame, but decorative controller
# connection probes are no longer repeated 60+ times per second.
assert "const int count = scePadRead(pad_handle, samples, PAD_SAMPLE_CAPACITY);" in radio
assert "#define CONNECTION_SCAN_MS UINT64_C(100)" in radio
connection_status = radio.split("static void poll_players(void)", 1)[1].split("#ifdef EDEN_DEV_ROM_ID", 1)[0]
assert "if(now < connection_scan_at) return;" in connection_status
assert connection_status.index("if(now < connection_scan_at) return;") < connection_status.index("scePadReadState(")
assert "connection_scan_at = 0;" in radio

# A held D-pad must not synchronously read game+global preferences JSON
# for every newly highlighted ROM. Worker snapshots are refreshed after
# preferences changes or an explicit title-mode save.
services_h = read("headless/prosperoeden/pe/ui/services.hpp")
library = read("headless/prosperoeden/pe/ui/library.cpp")
assert "bool docked = true; // effective mode precomputed on library worker" in services_h
worker = library.split("void Launcher::start_scan()", 1)[1].split("void Launcher::finish_scan(", 1)[0]
assert "game.docked = services_.docked(game.title_id);" in worker
selected = library.split("void Launcher::refresh_selected_game()", 1)[1].split("void Launcher::press_library(", 1)[0]
assert "games_[static_cast<std::size_t>(library_.selected)].docked" in selected
assert "services_.docked(" not in selected
assert "docked_refresh_after_scan_" in library
assert "docked_refresh_after_scan_" in nav
assert "if (scan_.valid()) docked_refresh_after_scan_ = true;" in library
assert "if (scan_.valid()) docked_refresh_after_scan_ = true;" in home
assert "installed.docked = home_game_docked_;" in home

# Native five-second frame reports execute inside graphics.cpp's render worker.
# An expensive sceKernelDirectMemoryQuery full ownership walk in this callback
# is itself a recurrent hitch. Preserve that work only at explicit lifecycle
# checkpoints in main.cpp, and read the cached direct-memory headroom here.
gpu_performance = read("headless/performance.cpp")
gpu_periodic = gpu_performance.split("void ReportGpuThread(unsigned frame)", 1)[1].split(
    "const auto load = [](const Totals& totals, bool calls)", 1)[0]
assert 'ReportDirectMemoryState("dev-profile")' not in gpu_periodic
assert "EDEN_MEMORY_LIVE frame=%u largest_last_confirmed=" in gpu_periodic
assert "largest_free_block.load(std::memory_order_relaxed)" in gpu_periodic
assert "sceKernelDirectMemoryQuery" not in gpu_periodic
assert 'ReportDirectMemoryState(name);' in read("headless/main.cpp")
assert "regions < 8192" in gpu_performance

# Repeated D-pad input must not let the highlight fall several rows behind
# the selected item, but single-step springs and approved artwork stay intact.
assert "const float scroll_backlog = std::fabs(scroll_.target - scroll_.value);" in widgets
assert "const float cursor_backlog = std::fabs(cursor_.target - cursor_.value);" in widgets
assert "theme::kScrollSpring * 2.0f" in widgets
assert "theme::kCursorSpring * 1.5f" in widgets
assert "scroll_.update(dt, scroll_omega);" in widgets
assert "cursor_.update(dt, cursor_omega);" in widgets
# One line per 5s in development, never per-frame debug logging in shipping.
assert "auto next_development_poll = Clock::now();" in frontend
assert "if (frame_start >= next_development_poll)" in frontend
assert "next_development_poll = frame_start +" in frontend
assert "development_input.active ? std::chrono::milliseconds(160)" in frontend
assert ": std::chrono::seconds(1)" in frontend
assert "development_poll++" not in frontend
assert "EDEN_UI_FRAMES frames=%u elapsed_ms=%lld late_20=%u late_33=%u late_50=%u" in frontend
assert "max_update_us=%lld max_draw_us=%lld max_present_us=%lld" in frontend
assert "const long long update_us = std::chrono::duration_cast<std::chrono::microseconds>" in frontend
assert "const long long draw_us = std::chrono::duration_cast<std::chrono::microseconds>" in frontend
assert "#ifdef EDEN_DEV_ROM_ID" in frontend
print("All-game GPU/HUD hotpath, PS5 splash one-shot, Nlib frame budget, native icons and atomic frame-skip tracking: SOURCE PASS")
