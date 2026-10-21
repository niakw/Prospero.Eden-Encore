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
expected_voice=original.replace(needle,updated)
# Preserve byte-for-byte pinned parity except for the known native audio-flag
# adjustment and the bounded PCM offset arithmetic correction.
voice_namespace="namespace AudioCore::Renderer {\\n"
helper="""\\nnamespace {
// Guard offset products without signed multiplication or wrap-around.
// Positive sample strides are fixed by the format, and division here is a
// compile-time constant (2 or 4) in both PCM cases.
constexpr bool PcmOffsetsWithinBuffer(s32 start, s32 end, u64 bytes, u32 sample_bytes) noexcept {
    return sample_bytes != 0 && start >= 0 && end >= 0 &&
           static_cast<u64>(start) <= bytes / sample_bytes &&
           static_cast<u64>(end) <= bytes / sample_bytes;
}
} // namespace
"""
assert expected_voice.count(voice_namespace)==1
expected_voice=expected_voice.replace(voice_namespace,voice_namespace+helper)
for pcm in ("PCM16","PCMFloat"):
    before=( "        if (wave_buffer_internal.start_offset * byte_size > wave_buffer_internal.size ||\\n"
             "            wave_buffer_internal.end_offset * byte_size > wave_buffer_internal.size) {\\n"
             f'            LOG_ERROR(Service_Audio, "Invalid {pcm} start/end wavebuffer sizes!");' )
    after=( "        if (!PcmOffsetsWithinBuffer(wave_buffer_internal.start_offset, wave_buffer_internal.end_offset,\\n"
            "                                    wave_buffer_internal.size, byte_size)) {\\n"
            f'            LOG_ERROR(Service_Audio, "Invalid {pcm} start/end wavebuffer sizes!");' )
    assert expected_voice.count(before)==1,pcm
    expected_voice=expected_voice.replace(before,after)
assert (active/"audio_core/renderer/voice/voice_info.cpp").read_text()==expected_voice

# Historical native sink-stream translation-unit parity. Do not use CMake
# string rewriting or alter the release audio semantics while consolidating.
original=(base/"audio_core/sink/sink_stream.cpp").read_text()
rewrite_cases=(
    ('        std::vector<s16> new_samples(samples.size() / system_channels * device_channels);', "        // AppendBuffer does not call back into producers. Reuse this thread's\n        // expansion storage across streams while preserving one PCM publication.\n        thread_local std::vector<s16> new_samples;\n        new_samples.assign(samples.size() / system_channels * device_channels, 0);"),
    ("    if (type == StreamType::In)\n        return;", "    if (type == StreamType::In)\n        return;\n    static_assert(std::is_same_v<decltype(samples_buffer), Common::RingBuffer<s16, 0x10000>>);\n    if (buffer.frames * device_channels > 0x10000 - samples_buffer.Size())\n        throw std::overflow_error(\"Audio PCM queue capacity exceeded\");"),
    ("        samples_buffer.Push(new_samples);", "        if (system_channels == 1 && device_channels == 2) {\n            for (std::size_t i = 0; i < new_samples.size(); i += 2) new_samples[i + 1] = new_samples[i];\n        }\n        samples_buffer.Push(new_samples);"),
    ("    std::memcpy(last_frame.data(), &output_buffer[(frames_written - 1) * frame_size], frame_size_bytes);", ""),
    ("        samples_buffer.Pop(&output_buffer[frames_written * frame_size], frames_available * frame_size);", "        samples_buffer.Pop(&output_buffer[frames_written * frame_size], frames_available * frame_size);\n        if (frames_available) std::memcpy(last_frame.data(), &output_buffer[(frames_written + frames_available - 1) * frame_size], frame_size_bytes);"),
)
for old,new in rewrite_cases:
    assert original.count(old)==1, ("pinned sink stream drift",old)
    original=original.replace(old,new)
assert (active/"audio_core/sink/sink_stream.cpp").read_text() == '#include <stdexcept>\n'+original
assert 'set(EDEN_MAINTAINED_SINK_STREAM' in cmake
assert 'if(NOT EXISTS "${EDEN_MAINTAINED_SINK_STREAM}")' in cmake
assert 'list(REMOVE_ITEM audio_sources sink/sink_details.cpp sink/sink_stream.cpp renderer/voice/voice_info.cpp)' in cmake
assert cmake.count('list(APPEND audio_sources "${EDEN_MAINTAINED_SINK_DETAILS}" "${EDEN_MAINTAINED_SINK_STREAM}" "${EDEN_MAINTAINED_VOICE_INFO}")')==1
assert 'write_derived("${PORT_BUILD_DIR}/sink_stream.cpp"' not in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/audio_core/sink/sink_stream.cpp"' not in cmake
print("MAINTAINED_AUDIO_STREAM_PARITY_PASS: historical rewrites, reusable scratch and selected source")


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
# Native NPad no longer has a CMake generator. Its byte-exact guards
# and selected hid_core translation unit are checked by the consolidation oracle.
assert 'list(APPEND npad_sources "${EDEN_NPAD_SELECTED}")' in cmake
assert 'list(FILTER npad_sources EXCLUDE REGEX "(^|/)npad\\\\.cpp$")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/npad.cpp"' not in cmake
# VSync/compose is a maintained native unit now, not a CMake string patch.
assert 'list(APPEND core_sources "${EDEN_MAINTAINED_VI_CONDUCTOR}")' in cmake
assert 'set(EDEN_MAINTAINED_VI_CONDUCTOR' in cmake
assert 'set(compose_new [=[' not in cmake
# The GPU/JIT generator ceilings and canonical GPU source contracts belong
# to check-vendor-consolidation-debt.py, invoked independently by preflight.
# This audio test deliberately does not assert retired CMake rewrite internals.
print("MAINTAINED_AUDIO_UNITS_PARITY_PASS sink_details=1 sink_stream=1 voice=1")
