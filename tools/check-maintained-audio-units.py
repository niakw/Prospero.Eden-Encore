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
assert cmake.count("write_derived(") <= 77
assert cmake.count("file(READ") <= 87
assert cmake.count("string(REPLACE") <= 227
print("MAINTAINED_AUDIO_UNITS_PARITY_PASS sink=1 voice=1")
