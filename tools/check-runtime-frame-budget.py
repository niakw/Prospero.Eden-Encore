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
assert "const Preferences docked_preferences = services_.preferences();" in worker
assert "game.docked = services_.docked_for_scan(game.title_id, docked_preferences);" in worker
assert worker.count("services_.preferences()") == 1
assert "services_.docked(game.title_id)" not in worker
native_docked = read("headless/prosperoeden/eden_services.cpp").split(
    "bool EdenServices::docked_for_scan(", 1)[1].split(
    "bool EdenServices::set_docked(", 1)[0]
assert "Eden::LoadGameSettings(title_id)" in native_docked
assert "Eden::LoadPreferences()" not in native_docked
assert "snapshot.performance_profile" in native_docked
assert "EffectiveDockedMode(title_id, game, snapshot.performance_profile)" in native_docked
live_docked = read("headless/prosperoeden/eden_services.cpp").split(
    "bool EdenServices::docked(std::uint64_t title_id)", 1)[1].split(
    "bool EdenServices::docked_for_scan(", 1)[0]
assert "EffectiveDockedMode(title_id, game, Eden::LoadPreferences().performance_profile)" in live_docked
effective = read("headless/prosperoeden/eden_services.cpp").split(
    "bool EffectiveDockedMode(", 1)[1].split("} // namespace", 1)[0]
assert "game.console_mode >= 0" in effective
assert "game.performance_profile >= 0" in effective
assert "EncoreOverridesRuntime::ProfileForTitle(title_id, tier).docked" in effective
assert "docked_for_scan(std::uint64_t title_id, const Preferences&)" in read("headless/prosperoeden/pe/ui/services.hpp")
selected = library.split("void Launcher::refresh_selected_game()", 1)[1].split("void Launcher::press_library(", 1)[0]
assert "games_[static_cast<std::size_t>(library_.selected)].docked" in selected
assert "services_.docked(" not in selected
assert "const bool has_selected = library_.selected >= 0 &&" in selected
assert "library_.selected < static_cast<int>(games_.size());" in selected
assert "selected_docked_ = !has_selected ||" in selected
assert "mods_switch_.snap(has_selected &&" in selected
assert "const Game *game = library_.selected >= 0 && library_.selected < count ?" in library
assert "docked_refresh_after_scan_" in library
assert "docked_refresh_after_scan_" in nav
assert "if (scan_.valid()) docked_refresh_after_scan_ = true;" in library
assert "if (scan_.valid()) docked_refresh_after_scan_ = true;" in home
assert "installed.docked = home_game_docked_;" in home

# The 500 Hz guest PC sampler formerly exhausted its 65536 slots,
# stopped forever, and used a detached sampling thread across title exit.
# Ring entries are atomic (signal-safe, concurrent GPU reader), snapshots
# account explicitly for overwritten samples, caller-chain special mode
# remains bounded, and fast worker ends with its guest CPU thread.
pc_source = read("headless/performance.cpp")
assert "std::array<std::atomic<uintptr_t>, 8192> sampled_pcs{};" in pc_source
assert "std::array<std::atomic<uintptr_t>, 65536> sampled_core_pcs{};" in pc_source
assert "sampled_core_pcs[core_index % sampled_core_pcs.size()].store(" in pc_source
assert "sampled_pcs[slot].store(" in pc_source
assert "EDEN_PERF_PC_SAMPLES_LOST source=gpu count=%u" in pc_source
assert "EDEN_PERF_PC_SAMPLES_LOST source=guest count=%u" in pc_source
assert "static thread_local std::jthread fast_sampler;" in pc_source
assert "std::thread([] {" not in pc_source.split('dev-settings pc_fast=on', 1)[1].split("worker.clock_error", 1)[0]
assert "core_pc_count.load() < sampled_core_pcs.size()" not in pc_source
assert "pc_core_registration.active = true;" in pc_source
assert "const bool gpu_capacity = true;" in pc_source
pc_poll = pc_source.split("void PollGpuPc() {", 1)[1].split(
    'extern "C" unsigned eden_heap_arenas_created', 1)[0]
assert "pthread_t gpu_target{};" in pc_poll
assert "const std::lock_guard lock(workers_mutex);" in pc_poll
assert pc_poll.index("const std::lock_guard lock(workers_mutex);") < pc_poll.index(
    "if (gpu_ready && pthread_kill(gpu_target, SIGUSR2))")
assert "pthread_kill(workers[4].thread, SIGUSR2)" not in pc_source
assert "struct WorkerRegistration {" in pc_source
assert "thread_local WorkerRegistration owned_worker;" in pc_source
assert "if (entry.registered && pthread_equal(entry.thread, owner))" in pc_source
assert "entry.registered = false;" in pc_source
assert "owned_worker.owner = worker.thread;" in pc_source
assert "owned_worker.index = i;" in pc_source
assert pc_source.index("owned_worker.owner = worker.thread;") < pc_source.index(
    "pc_core_registration.active = true;")
assert pc_source.index("pc_core_registration.active = true;") < pc_source.index(
    "static thread_local std::jthread fast_sampler;")


# Native GPU Snapshot() may process thousands of development PC samples.
# The CPU cores' SampleCpu() publication mutex must be held only for an
# immutable snapshot COPY, not the map/hex/printf/syscall reporting itself.
perf_snapshot = read("headless/performance.cpp").split("void Snapshot()", 1)[1].split(
    '#ifndef EDEN_DEV_PROFILE\n// Release builds:', 1)[0]
assert "const std::lock_guard snapshot_guard(snapshot_mutex);" in perf_snapshot
assert "const std::lock_guard worker_guard(workers_mutex);" in perf_snapshot
assert perf_snapshot.index("const std::lock_guard worker_guard(workers_mutex);") > perf_snapshot.index(
    "std::array<Worker, names.size()> worker_snapshot{};")
assert "worker_snapshot = workers;" in perf_snapshot
assert "cpu_snapshot = cpu_samples;" in perf_snapshot
assert "const auto& sample = cpu_snapshot[i];" in perf_snapshot
assert "EDEN_DEV_SNAPSHOT_COST mono_ns=%lld elapsed_ns=%lld" in perf_snapshot
assert perf_snapshot.count("worker_guard(workers_mutex)") == 1

# Development PC sampler may dump six new guest+host blocks per 5s
# while the GPU thread is presenting. Eliminate thousands of snprintf calls
# and repeated std::string reallocations WITHOUT changing existing log fields.
perf_dump = read("headless/performance.cpp").split(
    'std::printf("EDEN_PERF_BLOCK_GUEST', 1)[0].split(
    'constexpr char hex[] = "0123456789abcdef";', 1)[1]
assert "std::array<char, 64 * 8 + 1> guest{};" in perf_dump
assert "std::snprintf(" not in perf_dump
assert "std::string guest" not in perf_dump
gpu_dump = read("headless/performance.cpp").split(
    'std::printf("EDEN_PERF_BLOCK_HOST', 1)[0].split(
    'std::array<char, 4096 * 2 + 1> host{};', 1)[1]
assert "std::snprintf(" not in gpu_dump
assert "std::string host" not in gpu_dump
assert "host[2 * byte_count] = '\\0';" in gpu_dump

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
assert "::Common::SparseJitUsageFast(&jit_reserved_live, &jit_committed_live);" in gpu_periodic
assert "EDEN_JIT_SPARSE_MEMORY phase=dev-profile reserved=%zu committed=%zu" in gpu_periodic
assert "SparseJitUsage(&" not in gpu_periodic
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
