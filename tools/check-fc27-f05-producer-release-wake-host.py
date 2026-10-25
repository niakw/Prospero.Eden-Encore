#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F05: real producer-release callback body -> mock guest kernel event, O0/O2.

The native listener and registration/consumer-release handoff are selected from
the shipping vendored sources. This does not emulate guest HIPC parcels, the
guest CPU scheduler, a real kernel wait, or FC27 itself.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PRODUCER = (ROOT / "vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
CONSUMER = (ROOT / "vendor/sources/eden/src/core/hle/service/nvnflinger/buffer_queue_consumer.cpp").read_text()
CMAKE = (ROOT / "headless/CMakeLists.txt").read_text()
assert 'vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp' in CMAKE
assert 'core->connected_producer_listener = wake;' in PRODUCER
assert 'wake->SetDelegate(listener);' in PRODUCER
assert 'listener = core->connected_producer_listener;' in CONSUMER
assert 'listener->OnBufferReleased();' in CONSUMER
assert 'return &buffer_wait_event->GetReadableEvent();' in PRODUCER
assert PRODUCER.index('if (wake) wake->Stop();') < PRODUCER.index('service_context.CloseEvent(buffer_wait_event);')
assert 'release_wakes.erase(it);' in PRODUCER

signature = "class ProducerReleaseWake final : public IProducerListener {"
assert PRODUCER.count(signature) == 1, "native release callback signature drift"
start = PRODUCER.index(signature)
end = PRODUCER.index("\n};", start) + len("\n};")
native_class = PRODUCER[start:end]
assert 'event->Signal(kernel);' in native_class
assert 'if (forward) forward->OnBufferReleased();' in native_class

cpp = r"""
#include <atomic>
#include <cassert>
#include <cstdio>
#include <memory>
#include <mutex>
#include <thread>
namespace Kernel {
struct KernelCore {};
struct KEvent {
    std::atomic<int> signals{0};
    std::atomic<bool> closed{false};
    void Signal(KernelCore&) {
        assert(!closed.load());
        signals.fetch_add(1);
    }
};
}
namespace Service::android {
class IProducerListener {
public:
    virtual ~IProducerListener() = default;
    virtual void OnBufferReleased() = 0;
};
__NATIVE_LISTENER__
struct Forward : IProducerListener {
    std::atomic<int> notified{0};
    void OnBufferReleased() override { notified.fetch_add(1); }
};
}
int main() {
    using namespace Service::android;
    Kernel::KernelCore kernel;
    Kernel::KEvent event;
    auto wake = std::make_shared<ProducerReleaseWake>(&event, kernel);
    auto delegate = std::make_shared<Forward>();
    wake->SetDelegate(delegate);
    for (int i=0; i<260; ++i) wake->OnBufferReleased();
    assert(event.signals.load() == 260);
    assert(delegate->notified.load() == 260);
    // The consumer callback must not recur into itself when wrapped.
    wake->SetDelegate(wake);
    wake->OnBufferReleased();
    assert(event.signals.load() == 261);
    assert(delegate->notified.load() == 260);
    wake->SetDelegate(delegate);

    // Race a copied consumer callback against producer destruction.
    std::atomic<int> attempted{0};
    std::thread consumer([&] {
        for (int i=0; i<30000; ++i) {
            attempted.fetch_add(1);
            wake->OnBufferReleased();
            if ((i % 64) == 0) std::this_thread::yield();
        }
    });
    while (attempted.load() < 100) std::this_thread::yield();
    wake->Stop();
    event.closed.store(true);
    consumer.join();

    // Once Stop returns, no callback is permitted to touch a closed event.
    const int sealed = event.signals.load();
    wake->OnBufferReleased();
    assert(event.signals.load() == sealed);
    assert(delegate->notified.load() <= sealed);
    std::printf("F05_PRODUCER_RELEASE_WAKE_HOST_PASS initial=260 forwarded=260 "
                "stop_before_close=1 concurrent_release=1 "
                "scope=source_extracted_listener_mock_guest_kernel_event\n");
}
""".replace("__NATIVE_LISTENER__", native_class)

compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f05-release-wake-") as tmp:
    source = Path(tmp) / "release.cpp"
    source.write_text(cpp)
    for mode in ("-O0", "-O2"):
        output = Path(tmp) / ("release" + mode)
        build = subprocess.run(
            [compiler, "-std=c++20", mode, "-Wall", "-Wextra", "-Werror",
             "-fsanitize=undefined", "-fno-sanitize-recover=all", "-pthread",
             str(source), "-o", str(output)],
            capture_output=True, text=True, timeout=90)
        assert build.returncode == 0, (mode, build.stderr[-6000:])
        run = subprocess.run([str(output)], capture_output=True, text=True, timeout=30)
        assert run.returncode == 0, (mode, run.stderr[-6000:], run.stdout)
        assert run.stdout.count("F05_PRODUCER_RELEASE_WAKE_HOST_PASS initial=260") == 1
        print(run.stdout.strip(), mode, flush=True)
print("F05_GUEST_IPC_SCHEDULING_AND_REAL_GAME_PROGRESS_NOT_PROVEN")
