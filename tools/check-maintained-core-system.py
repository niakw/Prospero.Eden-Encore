#!/usr/bin/env python3
"""Exact G14 normal/native Core::System parity and maintained CMake selection."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
base = root / "vendor/sources/eden/src/core/core.cpp"
active = root / "vendor/encore-active/eden-core/src/core"
oracle = root / "tools/fixtures/retired-g14-core.cmake"
cmake = (root / "headless/CMakeLists.txt").read_text()
assert base.is_file() and oracle.is_file()
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/core.cpp" system_source)' not in cmake
assert 'write_derived("${PORT_BUILD_DIR}/core.cpp"' not in cmake
assert cmake.count('configure_file("${EDEN_MAINTAINED_CORE_SYSTEM}" "${PORT_BUILD_DIR}/core.cpp" COPYONLY)') == 1
assert 'target_include_directories(core PRIVATE "${EDEN_PORT_DIR}")' in cmake
assert 'set(EDEN_MAINTAINED_CORE_SYSTEM "${EDEN_MAINTAINED_CORE_SYSTEM_ROOT}/core_standard.cpp")' in cmake
assert 'set(EDEN_MAINTAINED_CORE_SYSTEM "${EDEN_MAINTAINED_CORE_SYSTEM_ROOT}/core_native.cpp")' in cmake
for native in (False, True):
    with tempfile.TemporaryDirectory(prefix="encore-core-g14-") as tmp:
        subprocess.run([
            "cmake", f"-DPS5_NATIVE={'ON' if native else 'OFF'}",
            f"-DPROJECT_SOURCE_DIR={root / 'vendor/sources/eden'}",
            f"-DPORT_BUILD_DIR={tmp}",
            f"-DEDEN_PORT_DIR={root / 'headless'}",
            "-P", str(oracle),
        ], check=True, capture_output=True, text=True)
        generated = (Path(tmp) / "core.cpp").read_text()
        if native:
            generated = generated.replace(
                '#include "' + (root / "headless/diagnostics.h").as_posix() + '"',
                '#include "diagnostics.h"')
        filename = "core_native.cpp" if native else "core_standard.cpp"
        actual = (active / filename).read_text()
        assert generated == actual, ("G14 byte parity", filename)
        assert actual.count("process.reset();\\n            ShutdownMainProcess()") == 2
        assert 'GameSettings::LoadOverrides(params.program_id,' in actual
        assert ("::Eden::ReportStep" in actual) == native
print("ENCORE_MAINTAINED_CORE_SYSTEM_PARITY_PASS G14=retired variants=2")
