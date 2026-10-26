// SPDX-License-Identifier: GPL-3.0-or-later
// R01 native header is used by actual Vulkan renderer/presenter and reports.
#include "../../headless/frame_metrics.h"
#include <cassert>
#include <thread>
#include <vector>
using namespace Eden::FrameMetrics;

int main() {
    ResetForTitle(false, 1'000'000'000ULL);
    for (int i=0; i<10; ++i) {
        OnSourceComposite(); OnRealQueued(); OnGeneratedQueued();
        OnSwapchainPresentReturned(); OnLoadingQueued(); OnSourceSkipped();
    }
    assert(!Enabled());
    assert(!Sample(2'000'000'000ULL).valid);
    assert(source_composites.load() == 0);
    ResetForTitle(true, 1'000'000'000ULL);
    assert(Enabled());
    for (int i=0; i<30; ++i) {
        OnSourceComposite();
        OnRealQueued();
        OnGeneratedQueued();
        OnSwapchainPresentReturned();
        OnSwapchainPresentReturned();
    }
    OnLoadingQueued();
    OnSourceSkipped();
    auto window = Sample(2'000'000'000ULL);
    assert(window.valid && window.interval_ns == 1'000'000'000ULL);
    assert(window.source_composites == 30);
    assert(window.real_frames_queued == 30);
    assert(window.generated_frames_queued == 30);
    assert(window.loading_frames_queued == 1);
    assert(window.skipped_source_frames == 1);
    assert(window.present_calls_returned == 60);
    assert(Rate(window.source_composites, window.interval_ns) == 30.0);
    assert(Rate(window.present_calls_returned, window.interval_ns) == 60.0);
    assert(Rate(33, 0) == 0);
    // Atomics handle separate GPU and presenter workers without allocations.
    constexpr int n = 2048;
    std::thread real([] {
        for (int i=0; i<n; ++i) { OnSourceComposite(); OnRealQueued(); }
    });
    std::thread display([] {
        for (int i=0; i<n; ++i) OnSwapchainPresentReturned();
    });
    real.join();
    display.join();
    auto concurrent = Sample(4'000'000'000ULL);
    assert(concurrent.valid);
    assert(concurrent.source_composites == n);
    assert(concurrent.real_frames_queued == n);
    assert(concurrent.generated_frames_queued == 0);
    assert(concurrent.present_calls_returned == n);
    assert(Rate(n, 2'000'000'000ULL) == 1024.0);
    assert(!Sample(4'000'000'000ULL).valid);
    // New title cannot inherit previous window counters or an enabled state.
    ResetForTitle(false, 5'000'000'000ULL);
    assert(!Sample(6'000'000'000ULL).valid);
    ResetForTitle(true, 7'000'000'000ULL);
    auto clean = Sample(8'000'000'000ULL);
    assert(clean.valid && clean.source_composites == 0 &&
           clean.real_frames_queued == 0 &&
           clean.generated_frames_queued == 0 &&
           clean.present_calls_returned == 0);
}
