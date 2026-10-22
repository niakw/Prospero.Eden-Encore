#!/usr/bin/env python3
"""Compile QueueBuffer's actual listener-dispatch tail; preserve frame identity."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
active = (ROOT / "vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
pinned = (ROOT / "vendor/sources/eden/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
cmake = (ROOT / "headless/CMakeLists.txt").read_text()
oracle = (ROOT / "tools/check-vendor-consolidation-debt.py").read_text()
assert 'list(APPEND core_sources "${EDEN_MAINTAINED_PROFILE_DEQUEUE}")' in cmake
assert 'target_compile_definitions(core PRIVATE EDEN_NVNF_DEQUEUE_PROFILE=1)' in cmake
assert "dequeue_expected = dequeue_expected.replace(queue_before, queue_after)" in oracle
begin_marker = "Status BufferQueueProducer::QueueBuffer("
end_marker = "\nvoid BufferQueueProducer::CancelBuffer("
def queue_method(source):
    assert source.count(begin_marker) == 1
    start = source.index(begin_marker)
    return source[start:source.index(end_marker, start)]

method = queue_method(active)
assert "item.graphic_buffer.reset();" in queue_method(pinned)
assert "item.slot = BufferItem::INVALID_BUFFER_SLOT;" in queue_method(pinned)
assert "item.graphic_buffer.reset();" not in method
assert "item.slot = BufferItem::INVALID_BUFFER_SLOT;" not in method
assert method.count("listener_available->OnFrameAvailable(item);") == 1
assert method.count("listener_replaced->OnFrameReplaced(item);") == 1
assert method.index("output->Inflate(") < method.index("listener_available->OnFrameAvailable(item);")
assert method.index("    // Notify consumers with the actual queued item:") < method.index("listener_available->OnFrameAvailable(item);")
tail_start = method.index("    if (listener_available) {\n        listener_available->OnFrameAvailable(item);")
tail = method[tail_start:].strip()
assert tail.endswith("return Status::NoError;\n}")
fixture = r"""
#include <cassert>
#include <memory>
struct GraphicBuffer { int id; };
struct BufferItem {
    std::shared_ptr<GraphicBuffer> graphic_buffer;
    int slot = -1;
    unsigned frame_number = 0;
};
struct IConsumerListener {
    virtual ~IConsumerListener() = default;
    virtual void OnFrameAvailable(const BufferItem&) = 0;
    virtual void OnFrameReplaced(const BufferItem&) = 0;
};
struct Recorder : IConsumerListener {
    int available = 0, replaced = 0;
    int seen_slot = -1, seen_buffer = -1;
    unsigned seen_frame = 0;
    void Record(const BufferItem& item) {
        seen_slot = item.slot;
        seen_buffer = item.graphic_buffer ? item.graphic_buffer->id : -1;
        seen_frame = item.frame_number;
    }
    void OnFrameAvailable(const BufferItem& item) override { ++available; Record(item); }
    void OnFrameReplaced(const BufferItem& item) override { ++replaced; Record(item); }
};
enum class Status { NoError };
Status Dispatch(BufferItem item, std::shared_ptr<IConsumerListener> listener_available,
                std::shared_ptr<IConsumerListener> listener_replaced) {
""" + "\n" + tail + r"""

int main() {
    auto listener = std::make_shared<Recorder>();
    BufferItem item{};
    item.graphic_buffer = std::make_shared<GraphicBuffer>(GraphicBuffer{17});
    item.slot = 3;
    item.frame_number = 1234;
    assert(Dispatch(item, listener, nullptr) == Status::NoError);
    assert(listener->available == 1 && listener->replaced == 0);
    assert(listener->seen_buffer == 17 && listener->seen_slot == 3 &&
           listener->seen_frame == 1234);
    assert(Dispatch(item, nullptr, listener) == Status::NoError);
    assert(listener->available == 1 && listener->replaced == 1);
    assert(listener->seen_buffer == 17 && listener->seen_slot == 3 &&
           listener->seen_frame == 1234);
    assert(Dispatch(item, listener, listener) == Status::NoError);
    assert(listener->available == 2 && listener->replaced == 1);
    assert(Dispatch(item, nullptr, nullptr) == Status::NoError);
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "host compiler required"
with tempfile.TemporaryDirectory(prefix="encore-nvn-callback-") as tmp:
    source = Path(tmp) / "callback.cpp"
    source.write_text(fixture)
    for opt in ("-O0", "-O2"):
        binary = Path(tmp) / ("callback-" + opt)
        subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(source), "-o", str(binary)], check=True, timeout=40)
        subprocess.run([str(binary)], check=True, timeout=15)
        print("NATIVE_NVN_QUEUE_CALLBACK_PASS", opt)
