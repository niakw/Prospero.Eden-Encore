#!/usr/bin/env python3
"""Host replay of native HardwareComposer full acquire/release/compose loop.

Uses the exact four C++ method bodies and swap-interval helper from the active,
pinned-source-reproduced translation unit. Only external display, producer,
GPU surface and graphic buffer classes are mocked. Never claims a PS5 FPS win.
"""
from pathlib import Path
import subprocess
import tempfile
import shutil
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "tools"))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "lifecycle_installer", root / "tools/install-vendored-surface-lifecycle.py")
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
pinned, active = installer.check_composer()
source = active.decode()
assert pinned != active

def extract_from(source_text: str, marker: str) -> str:
    assert source_text.count(marker) == 1, marker
    begin = source_text.index(marker)
    open_brace = source_text.index("{", begin)
    depth = 0
    for offset in range(open_brace, len(source_text)):
        if source_text[offset] == "{":
            depth += 1
        elif source_text[offset] == "}":
            depth -= 1
            if depth == 0:
                return source_text[begin:offset + 1]
    raise AssertionError("Unterminated native source: " + marker)


def extract(marker: str) -> str:
    return extract_from(source, marker)

helper = extract("s32 NormalizeSwapInterval(")
pinned_helper = extract_from(pinned.decode(), "s32 NormalizeSwapInterval(")
assert helper != pinned_helper
methods = "\n\n".join(extract(name) for name in (
    "u32 HardwareComposer::ComposeLocked(",
    "void HardwareComposer::ReleaseFramebuffersLocked(",
    "bool HardwareComposer::TryAcquireFramebufferLocked(",
    "HardwareComposer::CacheStatus HardwareComposer::CacheFramebufferLocked(",
))
# Verify the real native owner uses one lookup for the acquired-frame
# decision and cannot accidentally insert a missing consumer in the
# old ternary's second lookup.
compose = extract("u32 HardwareComposer::ComposeLocked(")
assert compose.count("m_framebuffers.find(consumer_id)") == 1
assert compose.index("if (!layer->is_overlay) {") < compose.index("m_framebuffers.find(consumer_id)")
assert "const auto result = reuse_held" in compose
assert "m_framebuffers[consumer_id].is_acquired" not in compose
assert "nvdisp.WaitForComposite();" in methods
assert "nvdisp.Composite(composition_stack);" in methods
assert "if (result == CacheStatus::NoBufferAvailable)" in methods
assert "return CacheStatus::NoBufferAvailable;" in methods
cache_marker = "HardwareComposer::CacheStatus HardwareComposer::CacheFramebufferLocked("
current_cache_method = extract(cache_marker)
pinned_cache_method = extract_from(pinned.decode(), cache_marker)
assert current_cache_method != pinned_cache_method
assert current_cache_method in methods
assert "return CacheStatus::CachedBufferReused;" in pinned_cache_method
# Produce a negative control by replacing ONLY the corrected method with the
# byte-exact historical one. The rest of the full composition is identical.

fixture = r"""
#include <algorithm>
#include <cassert>
#include <cmath>
#include <limits>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <map>
#include <memory>
#include <optional>
#include <vector>
#include <boost/container/small_vector.hpp>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s32 = std::int32_t;
using f32 = float;
using ConsumerId = s32;
namespace android {
enum class Status { NoError, NoBufferAvailable };
enum class BufferTransformFlags : int { Identity = 0 };
struct Fence { static Fence NoFence() { return {}; } };
struct GraphicBuffer {
    int id;
    int BufferId() const { return id; }
    int Offset() const { return 0; }
    int ExternalFormat() const { return 0; }
    int Width() const { return 1920; }
    int Height() const { return 1080; }
    int Stride() const { return 1920; }
};
struct BufferItem {
    std::shared_ptr<GraphicBuffer> graphic_buffer;
    int swap_interval{1};
    int transform{};
    int crop{};
    Fence fence{};
};
}
struct MockConsumer {
    std::deque<android::BufferItem> pending;
    unsigned acquires{}, releases{};
    android::Status AcquireBuffer(android::BufferItem* item,
                                  std::chrono::nanoseconds, bool) {
        ++acquires;
        if (pending.empty()) return android::Status::NoBufferAvailable;
        *item = std::move(pending.front());
        pending.pop_front();
        return android::Status::NoError;
    }
    android::Status ReleaseBuffer(const android::BufferItem& item, android::Fence) {
        assert(item.graphic_buffer);
        ++releases;
        return android::Status::NoError;
    }
};
struct Layer {
    ConsumerId consumer_id{};
    bool is_overlay{}, visible{true};
    int z_index{}, blending{}, layer_stack_mask{};
    std::shared_ptr<MockConsumer> buffer_item_consumer;
};
struct Display {
    struct Stack {
        std::vector<std::shared_ptr<Layer>> layers;
        std::shared_ptr<Layer> FindLayer(ConsumerId id) const {
            for (const auto& layer : layers)
                if (layer->consumer_id == id) return layer;
            return {};
        }
    } stack;
};
struct HwcLayer {
    int buffer_handle{}, offset{}, format{}, width{}, height{}, stride{};
    int z_index{}, blending{};
    android::BufferTransformFlags transform{};
    int crop_rect{};
    android::Fence acquire_fence{};
    int layer_stack_mask{};
};
namespace Nvidia::Devices {
struct nvdisp_disp0 {
    int wait_count{};
    std::vector<std::vector<int>> composed;
    void WaitForComposite() { ++wait_count; }
    template<class T> void Composite(const T& stack) {
        std::vector<int> ids;
        for (const auto& item : stack) ids.push_back(item.buffer_handle);
        composed.push_back(std::move(ids));
    }
};
}
class HardwareComposer {
public:
    enum class CacheStatus : u32 {
        NoBufferAvailable, BufferAcquired, CachedBufferReused
    };
    using ReleaseFrameNumber = u64;
    struct Framebuffer {
        android::BufferItem item{};
        ReleaseFrameNumber release_frame_number{};
        u64 last_acquire_frame{};
        bool is_acquired{};
    };
    std::map<ConsumerId, Framebuffer> m_framebuffers;
    u64 m_frame_number{};
    u32 ComposeLocked(f32*, Display&, Nvidia::Devices::nvdisp_disp0&);
    void ReleaseFramebuffersLocked(Display&);
    bool TryAcquireFramebufferLocked(Layer&, Framebuffer&);
    CacheStatus CacheFramebufferLocked(Layer&, ConsumerId);
};
""" + helper + "\n" + methods + r"""
static android::BufferItem frame(int id, int interval) {
    android::BufferItem item;
    item.graphic_buffer = std::make_shared<android::GraphicBuffer>(
        android::GraphicBuffer{id});
    item.swap_interval = interval;
    return item;
}
int main() {
    // Exact native swap-interval helper: the pinned 1 - INT_MIN expression
    // overflowed signed int in UBSan at both -O0 and -O2.
    volatile s32 minimum = std::numeric_limits<s32>::min();
    f32 edge_speed = 0;
    assert(NormalizeSwapInterval(&edge_speed, minimum) == 1);
    assert(std::isfinite(edge_speed) && edge_speed > 1.f);
    assert(NormalizeSwapInterval(&edge_speed, -1) == 1);
    assert(edge_speed == 4.f);
    assert(NormalizeSwapInterval(&edge_speed, 0) == 1);
    assert(edge_speed == 2.f);
    HardwareComposer composer;
    Display display;
    Nvidia::Devices::nvdisp_disp0 display_gpu;
    auto game_consumer = std::make_shared<MockConsumer>();
    auto hud_consumer = std::make_shared<MockConsumer>();
    auto game = std::make_shared<Layer>();
    game->consumer_id = 7;
    game->z_index = 0;
    game->buffer_item_consumer = game_consumer;
    auto hud = std::make_shared<Layer>();
    hud->consumer_id = 8;
    hud->is_overlay = true;
    hud->z_index = 1;
    hud->buffer_item_consumer = hud_consumer;
    display.stack.layers = {game, hud};
    game_consumer->pending.push_back(frame(10,2));
    hud_consumer->pending.push_back(frame(20,1));
    f32 speed=0;
    assert(composer.ComposeLocked(&speed, display, display_gpu) == 1);
    assert((display_gpu.composed == std::vector<std::vector<int>>{{10,20}}));
    assert(speed == 1.0f);
    assert(composer.m_framebuffers[7].is_acquired);
    assert(composer.m_framebuffers[8].is_acquired);

    // No fresh game/HUD frame: game remains acquired at 2-vsync interval,
    // overlay is released and must never force stale composition.
    assert(composer.ComposeLocked(&speed, display, display_gpu) == 1);
    assert(display_gpu.composed.size() == 1);
    assert(game_consumer->releases == 0 && hud_consumer->releases == 1);

    // At game release frame, only the new HUD frame is available.
    // Never compose the previously released game buffer into the new HUD.
    hud_consumer->pending.push_back(frame(21,1));
    assert(composer.ComposeLocked(&speed, display, display_gpu) == 1);
    assert((display_gpu.composed == std::vector<std::vector<int>>{
        {10,20}, {21}}));
    assert(game_consumer->releases == 1);
    assert(!composer.m_framebuffers[7].is_acquired);
    assert(composer.m_framebuffers[8].is_acquired);

    // Now the game produces a new frame; previously released HUD buffer
    // must not reappear in the next composite.
    game_consumer->pending.push_back(frame(11,2));
    assert(composer.ComposeLocked(&speed, display, display_gpu) == 1);
    assert((display_gpu.composed == std::vector<std::vector<int>>{
        {10,20}, {21}, {11}}));
    assert(hud_consumer->releases == 2);

    // No new buffers: no hidden re-presentation of either released image.
    assert(composer.ComposeLocked(&speed, display, display_gpu) == 1);
    assert(display_gpu.composed.size() == 3);
    assert(display_gpu.wait_count == 5);

    // F05 sustained forward-progress: real source-extracted compositor,
    // one 30Hz guest game producer and one independent 60Hz HUD producer.
    // This is an ownership/cadence replay, not a PS5 timing measurement.
    HardwareComposer paced;
    Display paced_display;
    Nvidia::Devices::nvdisp_disp0 paced_gpu;
    auto paced_game_consumer = std::make_shared<MockConsumer>();
    auto paced_hud_consumer = std::make_shared<MockConsumer>();
    auto paced_game = std::make_shared<Layer>();
    paced_game->consumer_id = 37;
    paced_game->buffer_item_consumer = paced_game_consumer;
    auto paced_hud = std::make_shared<Layer>();
    paced_hud->consumer_id = 38;
    paced_hud->z_index = 1;
    paced_hud->is_overlay = true;
    paced_hud->buffer_item_consumer = paced_hud_consumer;
    paced_display.stack.layers = {paced_game, paced_hud};
    constexpr int steady_ticks = 240;
    int last_game = -1;
    for (int tick = 0; tick < steady_ticks; ++tick) {
        if (tick % 2 == 0) {
            last_game = 1000 + tick;
            paced_game_consumer->pending.push_back(frame(last_game, 2));
        }
        paced_hud_consumer->pending.push_back(frame(2000 + tick, 1));
        assert(paced.ComposeLocked(&speed, paced_display, paced_gpu) == 1);
        assert(paced_gpu.composed.size() == static_cast<std::size_t>(tick + 1));
        assert((paced_gpu.composed.back() ==
                std::vector<int>{last_game, 2000 + tick}));
        assert(paced_game_consumer->acquires == static_cast<unsigned>(tick / 2 + 1));
        assert(paced_game_consumer->releases == static_cast<unsigned>(tick / 2));
        assert(paced_hud_consumer->acquires == static_cast<unsigned>(tick + 1));
        assert(paced_hud_consumer->releases == static_cast<unsigned>(tick));
        assert(paced_gpu.wait_count == tick + 1);
        assert(paced.m_frame_number == static_cast<u64>(tick + 1));
    }
    assert(paced_game_consumer->pending.empty());
    assert(paced_hud_consumer->pending.empty());

    // The guest stops supplying new game images during pause/half-time.
    // One still-owned two-vsync game frame can be reused ONCE; after
    // release it must never reappear in an overlay-only composition.
    constexpr int no_game_ticks = 12;
    const int prior_game = last_game;
    const std::size_t prior_composites = paced_gpu.composed.size();
    for (int tick = 0; tick < no_game_ticks; ++tick) {
        paced_hud_consumer->pending.push_back(frame(3000 + tick, 1));
        assert(paced.ComposeLocked(&speed, paced_display, paced_gpu) == 1);
        assert(paced_gpu.composed.size() == prior_composites + tick + 1);
        const auto& layers = paced_gpu.composed.back();
        assert(layers.back() == 3000 + tick);
        for (int handle : layers)
            assert(handle != prior_game); // released at the first paused tick
        assert(paced_gpu.wait_count == steady_ticks + tick + 1);
    }
    assert(!paced.m_framebuffers[37].is_acquired);
    assert(paced_game_consumer->releases == steady_ticks / 2);
    assert(paced_hud_consumer->releases == steady_ticks + no_game_ticks - 1);

    // Recover after the pause without resurrecting the old scan or HUD.
    paced_game_consumer->pending.push_back(frame(9001, 2));
    paced_hud_consumer->pending.push_back(frame(9002, 1));
    assert(paced.ComposeLocked(&speed, paced_display, paced_gpu) == 1);
    assert((paced_gpu.composed.back() == std::vector<int>{9001, 9002}));
    // acquire attempts also count the twelve expected NoBufferAvailable
    // polls while the guest is paused; successful game frames do not.
    assert(paced_game_consumer->acquires ==
           steady_ticks / 2 + no_game_ticks + 1);
    assert(paced_hud_consumer->releases == steady_ticks + no_game_ticks);
    assert(paced_gpu.wait_count == steady_ticks + no_game_ticks + 1);
    std::printf("F05_COMPOSITOR_CADENCE_REPLAY_PASS game_success=%d "
                "game_poll_attempts=%u hud_success=%d paused_polls=%d "
                "recovery=1 scope=source_extracted_host\\n",
                steady_ticks / 2 + 1, paced_game_consumer->acquires,
                steady_ticks + no_game_ticks + 1, no_game_ticks);
    std::puts("HARDWARE_COMPOSER_FULL_LIVENESS_PASS");
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-composer-full-") as td:
    path = Path(td) / "composer.cpp"
    path.write_text(fixture)
    for opt in ("-O0", "-O2"):
        exe = Path(td) / ("composer" + opt)
        result = subprocess.run([compiler, "-std=c++20", opt, "-Wall",
                                 "-Wextra", "-Werror", "-fsanitize=undefined",
                                 "-fno-sanitize-recover=all", "-pthread",
                                 str(path), "-o", str(exe)], capture_output=True,
                                text=True, timeout=45)
        assert result.returncode == 0, (opt, result.stderr[-5000:])
        result = subprocess.run([str(exe)], capture_output=True, text=True,
                                timeout=15)
        assert result.returncode == 0, (opt, result.stderr[-3500:])
        print("NATIVE_FULL_COMPOSITOR_LIVENESS_HOST_PASS", opt)

        historical = fixture.replace(current_cache_method, pinned_cache_method)
        assert historical != fixture and historical.count(pinned_cache_method) == 1
        original_file = Path(td) / "composer_pinned.cpp"
        original_file.write_text(historical)
        original_bin = Path(td) / ("composer_pinned" + opt)
        built = subprocess.run([compiler, "-std=c++20", opt, "-Wall",
                                "-Wextra", "-Werror", "-fsanitize=undefined",
                                "-fno-sanitize-recover=all", "-pthread",
                                str(original_file), "-o", str(original_bin)],
                               capture_output=True, text=True, timeout=45)
        assert built.returncode == 0, (opt, built.stderr[-5000:])
        actual = subprocess.run([str(original_bin)], capture_output=True,
                                text=True, timeout=15)
        assert actual.returncode != 0 and "Assertion" in actual.stderr, (
            "The pinned original unexpectedly passed the released-buffer"
            " multi-layer regression", opt, actual.stdout, actual.stderr[-1500:])
        print("PINNED_COMPOSITOR_STALE_FRAME_EXPECTED_FAIL_PASS", opt)

        # Independent negative control for the previous signed-overflow path:
        # keep the corrected cache method, restore only the exact pinned
        # normalization helper, then require UBSan to reject INT32_MIN.
        old_speed = fixture.replace(helper, pinned_helper)
        assert old_speed != fixture and old_speed.count(pinned_helper) == 1
        old_speed_path = Path(td) / "composer_old_speed.cpp"
        old_speed_path.write_text(old_speed)
        old_speed_bin = Path(td) / ("composer_old_speed" + opt)
        old_speed_build = subprocess.run(
            [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
             "-fsanitize=undefined", "-fno-sanitize-recover=all", "-pthread",
             str(old_speed_path), "-o", str(old_speed_bin)],
            capture_output=True, text=True, timeout=45)
        assert old_speed_build.returncode == 0, (opt, old_speed_build.stderr[-5000:])
        old_speed_run = subprocess.run([str(old_speed_bin)], capture_output=True,
                                       text=True, timeout=15)
        assert old_speed_run.returncode != 0 and "signed integer overflow" in old_speed_run.stderr, (
            "Pinned compositor signed-overflow regression unexpectedly passed",
            opt, old_speed_run.stdout, old_speed_run.stderr[-2000:])
        print("PINNED_COMPOSITOR_SWAP_OVERFLOW_EXPECTED_FAIL_PASS", opt)
