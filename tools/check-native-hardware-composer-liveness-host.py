#!/usr/bin/env python3
"""Host replay of native HardwareComposer full acquire/release/compose loop.

Uses the exact four C++ method bodies and swap-interval helper from the active,
pinned-source-reproduced translation unit. Executes the real BufferQueueConsumer Acquire/Release along with the maintained
compositor. Guest enqueue, GPU completion and display remain mocked. Never claims a PS5 FPS win.
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
# F05: real pinned BufferQueueConsumer Acquire/Release + maintained compositor
# compiled in ONE C++ fixture, not merely inspected independently.
# The enqueue/slot/fence publication and listener callback are copied
# verbatim out of the maintained QueueBuffer C++ (no Python model of either).
producer_text = (root / "vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
producer_start = producer_text.index("Status BufferQueueProducer::QueueBuffer(")
producer_stop = producer_text.index("\nvoid BufferQueueProducer::CancelBuffer(", producer_start)
producer_method = producer_text[producer_start:producer_stop]
publish_start = producer_method.index("        ++core->frame_counter;")
publish_stop = producer_method.index("        output->Inflate(", publish_start)
producer_publish = producer_method[publish_start:publish_stop]
listener_start = producer_method.index("    // Notify consumers with the actual queued item:", publish_stop)
producer_callback = producer_method[listener_start:]
assert producer_callback.endswith("return Status::NoError;\n}\n")
assert "recycled_queued_slot = true;" in producer_publish
assert "buffer_wait_event->Signal(service_context.kernel);" in producer_publish
for marker in ("slots[slot].fence = fence;", "item.fence = fence;",
               "core->SignalDequeueCondition();", "listener_available->OnFrameAvailable(item)",
               "listener_replaced->OnFrameReplaced(item)"):
    assert marker in producer_publish + producer_callback, ("QueueBuffer source drift", marker)

queue_source = (root / "vendor/sources/eden/src/core/hle/service/nvnflinger/buffer_queue_consumer.cpp").read_text()
consumer_methods = "\n\n".join(extract_from(queue_source, marker) for marker in (
    "Status BufferQueueConsumer::AcquireBuffer(",
    "Status BufferQueueConsumer::ReleaseBuffer(",
))
for marker in ("core->StillTracking(*front)", "core->SignalDequeueCondition();",
               "slots[slot].buffer_state = BufferState::Acquired;",
               "slots[slot].buffer_state = BufferState::Free;",
               "listener->OnBufferReleased();"):
    assert marker in consumer_methods, ("BufferQueue source drift", marker)

# Produce a negative control by replacing ONLY the corrected method with the
# byte-exact historical one. The rest of the full composition is identical.

fixture = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <limits>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <vector>
#include <boost/container/small_vector.hpp>
#pragma GCC diagnostic ignored "-Wunused-parameter"
#define LOG_DEBUG(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s64 = std::int64_t;
using s32 = std::int32_t;
using f32 = float;
using ConsumerId = s32;
enum NativeWindowTransform : int { None=0, InverseDisplay=1 };
namespace Common {
struct Clock { unsigned calls{}; struct Time { s64 count() const { return 0; } };
               Time GetTimeNS() { ++calls; return {}; } };
inline Clock g_wall_clock{};
}
namespace android {
enum class Status { NoError, NoBufferAvailable, PresentLater, InvalidOperation, BadValue, StaleBufferSlot };
enum class BufferTransformFlags : int { Identity = 0 };
struct Fence { int sequence{-1}; static Fence NoFence() { return {}; } };
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
    int transform{}, crop{};
    Fence fence{};
    s32 slot{-1};
    u64 frame_number{};
    std::int64_t timestamp{};
    bool is_auto_timestamp{}, acquire_called{}, is_droppable{};
    bool transform_to_display_inverse{};
    u32 scaling_mode{};
};
}
namespace android {
enum class BufferState { Free, Queued, Dequeued, Acquired };
struct BufferQueueDefs { static constexpr s32 NUM_BUFFER_SLOTS=8; };
struct BufferSlot {
    std::shared_ptr<GraphicBuffer> graphic_buffer{};
    BufferState buffer_state{BufferState::Free};
    u64 frame_number{};
    bool acquire_called{},needs_cleanup_on_release{};
    s64 queue_time{},presentation_time{};
    Fence fence{};
};
struct IProducerListener {
    unsigned releases{};
    void OnBufferReleased() { ++releases; }
};
struct IConsumerListener {
    unsigned available{}, replaced{};
    std::vector<u64> observed_frames;
    std::vector<int> observed_fences;
    void OnFrameAvailable(const BufferItem& item) {
        ++available;
        assert(item.graphic_buffer);
        observed_frames.push_back(item.frame_number);
        observed_fences.push_back(item.fence.sequence);
    }
    void OnFrameReplaced(const BufferItem& item) {
        ++replaced;
        assert(item.graphic_buffer);
        observed_frames.push_back(item.frame_number);
        observed_fences.push_back(item.fence.sequence);
    }
};
struct BufferQueueCore {
    std::mutex mutex;
    std::array<BufferSlot,BufferQueueDefs::NUM_BUFFER_SLOTS> slots{};
    std::deque<BufferItem> queue;
    s32 max_acquired_buffer_count{};
    u64 frame_counter{};
    unsigned notifications{};
    bool dequeue_buffer_cannot_block{},buffer_has_been_queued{};
    std::shared_ptr<IConsumerListener> consumer_listener{
        std::make_shared<IConsumerListener>()};
    void PushHistory(u64,s64,s64,BufferState) {}
    void UpdateHistory(u64,BufferState) {}
    std::shared_ptr<IProducerListener> connected_producer_listener{
        std::make_shared<IProducerListener>()};
    bool StillTracking(const BufferItem& item) const {
        return item.slot>=0 && item.slot<BufferQueueDefs::NUM_BUFFER_SLOTS &&
            item.graphic_buffer && slots[item.slot].graphic_buffer==item.graphic_buffer;
    }
    void SignalDequeueCondition(){++notifications;}
};
struct BufferQueueConsumer {
    std::shared_ptr<BufferQueueCore> core;
    std::array<BufferSlot,BufferQueueDefs::NUM_BUFFER_SLOTS>& slots;
    explicit BufferQueueConsumer(std::shared_ptr<BufferQueueCore> c)
        : core(std::move(c)),slots(core->slots){}
    Status AcquireBuffer(BufferItem*,std::chrono::nanoseconds);
    Status ReleaseBuffer(s32,u64,const Fence&);
};
__CONSUMER_METHODS__
} // namespace android
struct MockConsumer {
    std::deque<android::BufferItem> pending;
    std::shared_ptr<android::BufferQueueCore> queue{
        std::make_shared<android::BufferQueueCore>()};
    android::BufferQueueConsumer native{queue};
    unsigned acquires{},releases{},successful_acquires{};
    android::Status QueueNative(android::BufferItem queued);
    android::Status AcquireBuffer(android::BufferItem* item,
                                  std::chrono::nanoseconds expected,bool wait_for_fence) {
        assert(!wait_for_fence);
        ++acquires;
        // A deterministic guest producer is mocked; native consumer
        // supplies slot acquisition and release, including generation wake.
        if(!pending.empty()){
            auto pushed=std::move(pending.front());
            pending.pop_front();
            assert(QueueNative(std::move(pushed)) == android::Status::NoError);
        }
        const auto status=native.AcquireBuffer(item,expected);
        if(status==android::Status::NoError){
            // Real BufferItemConsumer restores its previously mapped backing.
            assert(item->slot>=0);
            item->graphic_buffer=queue->slots[item->slot].graphic_buffer;
            assert(item->graphic_buffer);
            ++successful_acquires;
        }
        return status;
    }
    android::Status ReleaseBuffer(const android::BufferItem& item,android::Fence fence){
        assert(item.graphic_buffer && item.frame_number>0);
        const auto status=native.ReleaseBuffer(item.slot,item.frame_number,fence);
        assert(status==android::Status::NoError);
        ++releases;
        return status;
    }
};
// This function runs actual source-extracted QueueBuffer slot/queue and
// callback statements. Only the incoming Binder call and guest frame
// allocation are fixture inputs.
android::Status MockConsumer::QueueNative(android::BufferItem queued) {
    using android::Status;
    using android::BufferState;
    auto core=queue;
    auto& slots=core->slots;
    s32 slot=-1;
    android::BufferItem item{};
    std::shared_ptr<android::IConsumerListener> listener_available,listener_replaced;
    const s64 timestamp=queued.timestamp;
    const bool is_auto_timestamp=queued.is_auto_timestamp;
    const int crop=queued.crop;
    const int transform=queued.transform;
    const int scaling_mode=0;
    const bool async=false;
    const s32 swap_interval=queued.swap_interval;
    const android::Fence fence=queued.fence;
    const bool record_buffer_history=false;
    // QueueBuffer now tracks discarded queued slots and signals the guest
    // Binder event. Keep those native dependencies in the composed mock.
    bool recycled_queued_slot = false;
    struct GuestKernel {};
    struct GuestServiceContext { GuestKernel kernel{}; } service_context;
    struct GuestWaitEvent {
        unsigned calls{};
        void Signal(GuestKernel&) { ++calls; }
    } guest_event;
    auto* buffer_wait_event = &guest_event;
    [[maybe_unused]] unsigned sticky_transform{};
    const unsigned sticky_transform_=0;
    {
        std::scoped_lock lock{core->mutex};
        for(s32 i=0;i<android::BufferQueueDefs::NUM_BUFFER_SLOTS;++i){
            if(slots[i].buffer_state==BufferState::Free){slot=i;break;}
        }
        assert(slot>=0 && queued.graphic_buffer);
        slots[slot].graphic_buffer=queued.graphic_buffer;
__PRODUCER_PUBLISH__
    }
__PRODUCER_CALLBACK__

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
    std::vector<std::vector<int>> fences;
    void WaitForComposite() { ++wait_count; }
    template<class T> void Composite(const T& stack) {
        std::vector<int> ids;
        std::vector<int> frame_fences;
        for (const auto& item : stack) {
            ids.push_back(item.buffer_handle);
            frame_fences.push_back(item.acquire_fence.sequence);
        }
        composed.push_back(std::move(ids));
        fences.push_back(std::move(frame_fences));
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
    item.fence.sequence = id;
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
    assert((display_gpu.fences == std::vector<std::vector<int>>{{10,20}}));
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
        assert(paced_gpu.fences.back() == paced_gpu.composed.back());
        assert(paced_game_consumer->acquires == static_cast<unsigned>(tick / 2 + 1));
        assert(paced_game_consumer->releases == static_cast<unsigned>(tick / 2));
        assert(paced_hud_consumer->acquires == static_cast<unsigned>(tick + 1));
        assert(paced_hud_consumer->releases == static_cast<unsigned>(tick));
        assert(paced_gpu.wait_count == tick + 1);
        assert(paced.m_frame_number == static_cast<u64>(tick + 1));
    }
    assert(paced_game_consumer->pending.empty());
    assert(paced_hud_consumer->pending.empty());
    assert(paced_game_consumer->queue->consumer_listener->available ==
           steady_ticks / 2);
    assert(paced_hud_consumer->queue->consumer_listener->available ==
           steady_ticks);
    assert(paced_game_consumer->queue->consumer_listener->replaced == 0);
    assert(paced_hud_consumer->queue->consumer_listener->replaced == 0);
    assert(paced_game_consumer->queue->consumer_listener->observed_fences.front() == 1000);
    assert(paced_hud_consumer->queue->consumer_listener->observed_fences.back() ==
           2000 + steady_ticks - 1);
    assert(Common::g_wall_clock.calls == 0);

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
fixture = fixture.replace("__CONSUMER_METHODS__", consumer_methods)
fixture = fixture.replace("__PRODUCER_PUBLISH__", producer_publish)
fixture = fixture.replace("__PRODUCER_CALLBACK__", producer_callback)
assert "__PRODUCER_PUBLISH__" not in fixture and "__PRODUCER_CALLBACK__" not in fixture
assert "__CONSUMER_METHODS__" not in fixture
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
        print("F05_NATIVE_BUFFERQUEUE_CONSUMER_COMPOSITOR_PASS", opt, "scope=source_extracted_host_no_guest_ipc_no_real_gpu")
        print("F05_NATIVE_PRODUCER_CONSUMER_FENCE_REPLAY_PASS", opt,
              "scope=source_extracted_producer_queue_consumer_compositor_mock_gpu")

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
