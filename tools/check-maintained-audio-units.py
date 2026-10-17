#!/usr/bin/env python3
"""Validate maintained audio source parity with the pinned emulator snapshot.

The test does not claim audio timing, frame sync, or gameplay correctness.
"""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
base=root/"vendor/sources/eden/src"
active=root/"vendor/encore-active/eden-core/src"
cmake=(root/"headless/CMakeLists.txt").read_text()

original=(base/"audio_core/sink/sink_details.cpp").read_text()
needle="    return GetOutputSinkDetails(sink_id).factory(device_id);"
updated='    if (device_id == "ps5") return std::make_unique<Eden::AudioSink>();\n'+needle
assert original.count(needle)==1
expected='#include "devices.h"\n'+original.replace(needle,updated)
assert (active/"audio_core/sink/sink_details.cpp").read_text()==expected

original=(base/"audio_core/renderer/voice/voice_info.cpp").read_text()
needle="flags |= u16(params.flags.IsVoicePitchAndSrcSkippedSupported);"
updated="flags |= u16(params.flags.IsVoicePitchAndSrcSkippedSupported) << 1;"
assert original.count(needle)==1
assert (active/"audio_core/renderer/voice/voice_info.cpp").read_text()==original.replace(needle,updated)

assert 'list(APPEND audio_sources "${EDEN_MAINTAINED_SINK_DETAILS}" "${PORT_BUILD_DIR}/sink_stream.cpp" "${EDEN_MAINTAINED_VOICE_INFO}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/sink_details.cpp"' not in cmake
assert 'write_derived("${PORT_BUILD_DIR}/voice_info.cpp"' not in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/audio_core/sink/sink_details.cpp"' not in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/audio_core/renderer/voice/voice_info.cpp"' not in cmake
assert 'target_include_directories(audio_core PRIVATE "${EDEN_PORT_DIR}"' in cmake
# Full checked source for the native guest scheduler lock: no CMake-derived override.
spin_original=(base/"core/hle/kernel/k_spin_lock.cpp").read_text()
spin_old="void KSpinLock::Lock() {\n    m_lock.lock();\n}"
assert spin_original.count(spin_old)==1
spin_expected=spin_original.replace(
    '#include "core/hle/kernel/k_spin_lock.h"',
    '#include "performance.h"\n#include "core/hle/kernel/k_spin_lock.h"'
).replace(spin_old,"void KSpinLock::Lock() {\n    ::Eden::Performance::SpinAcquire(m_lock);\n}")
assert (active/"core/hle/kernel/k_spin_lock.cpp").read_text()==spin_expected
assert 'list(APPEND core_sources "${eden_kernel_spin}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/k_spin_lock.cpp"' not in cmake
assert 'set(npad_entry "void NPad::ControllerUpdate(' in cmake
assert "set(compose_new [=[" in cmake
# The port must keep reducing generator rewrites, not silently increase them.
gpu_span_derived='write_derived("${eden_gpu_span_tu}" "${eden_gpu_span_src}")'
assert cmake.count(gpu_span_derived) == 1
assert cmake.count("write_derived(") - cmake.count(gpu_span_derived) <= 77
# One explicitly checked native GPU synchronization-method input is
# approved; keep the prior 87-read generator budget for everything else.
gpu_sync_input='file(READ "${EDEN_PORT_DIR}/gpu_sync_failure_wait.inc" gpu_sync_wait_replacement)'
assert cmake.count(gpu_sync_input) == 1
gpu_span_input='file(READ "${PROJECT_SOURCE_DIR}/src/video_core/memory_manager.cpp" eden_gpu_span_src)'
assert cmake.count(gpu_span_input) == 1
assert cmake.count("file(READ") - cmake.count(gpu_sync_input) - cmake.count(gpu_span_input) <= 87
# The native GPU producer cancellation contract adds exactly one checked
# source-derived wait replacement; keep the previous ceiling for all others.
gpu_producer_wait='string(REPLACE "${gpu_block_wait_original}" "${gpu_block_wait_checked}"'
assert cmake.count(gpu_producer_wait) == 1
gpu_enqueue_fence='string(REPLACE "${gpu_enqueue_fence_original}" "${gpu_enqueue_fence_atomic}"'
assert cmake.count(gpu_enqueue_fence) == 1
gpu_read_capture='string(REPLACE "${gpu_read_capture_original}"'
assert cmake.count(gpu_read_capture) == 1
assert "Pinned GPU read callback lifetime changed" in cmake
# One bounded native GPU dirty-mask fix uses a separately pinned source
# replacement. Explicitly account for this exact expression; do not raise the
# generator-wide budget or grant an anonymous rewrite.
dirty_mask_split='string(REPLACE "${eden_dirty_raw}" [=['
assert cmake.count(dirty_mask_split) == 1
assert 'Pinned native GPUDirty Collect call changed' in cmake
native_read_slot='string(REPLACE "${eden_read_original}" "${eden_read_native}"'
assert cmake.count(native_read_slot) == 1
assert "Pinned native guest CPU read scratch/slot contract changed" in cmake
native_span_guard='string(REPLACE "${eden_span_original}" [=['
assert cmake.count(native_span_guard) == 1
assert "Pinned native guest span page-boundary contract changed" in cmake
gpu_span_guard='string(REPLACE "${eden_gpu_span_original}" [=['
assert cmake.count(gpu_span_guard) == 1
assert "Pinned native GPU guest span range gate changed" in cmake
# Explicitly exempt ONLY the two pinned native queue-slot destructor rewrites.
# This preserves the old 227 unapproved generator-rewrite ceiling.
gpu_queue_slot_find='string(REPLACE "${queue_slot_construct}" "__ENCORE_GPU_QUEUE_SLOT__"'
gpu_queue_slot_apply='string(REPLACE "__ENCORE_GPU_QUEUE_SLOT__" "${queue_slot_repair}"'
assert cmake.count(gpu_queue_slot_find) == 1
assert cmake.count(gpu_queue_slot_apply) == 1
assert 'list(LENGTH queue_slot_matches queue_slot_count)' in cmake
assert 'if(NOT queue_slot_count EQUAL 2)' in cmake
assert cmake.count("string(REPLACE") - cmake.count(gpu_producer_wait) - cmake.count(gpu_enqueue_fence) - cmake.count(dirty_mask_split) - cmake.count(native_read_slot) - cmake.count(native_span_guard) - cmake.count(gpu_span_guard) - cmake.count(gpu_read_capture) - cmake.count(gpu_queue_slot_find) - cmake.count(gpu_queue_slot_apply) <= 227
print("MAINTAINED_AUDIO_UNITS_PARITY_PASS sink=1 voice=1")
