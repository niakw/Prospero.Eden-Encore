#!/usr/bin/env python3
"""Pin common x64 Patch()/Unpatch() implementation and native perf-map removal."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
active = root / "vendor/encore-active/eden-core/src/dynarmic/backend/x64"
pinned = root / "vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64/emit_x64.cpp"
cmake = (root / "headless/CMakeLists.txt").read_text()
old = pinned.read_text()
host = (active / "emit_x64_host.cpp").read_text()
native = (active / "emit_x64_native.cpp").read_text()
lookup = "    const PatchInformation& patch_info = patch_information[target_desc];"
fixed = (
    "    const auto patch = patch_information.find(target_desc);\n"
    "    if (patch == patch_information.end()) return;\n"
    "    const PatchInformation& patch_info = patch->second;"
)
perf = "    PerfMapRegister(entrypoint, code.getCurr(), LocationDescriptorToFriendlyName(descriptor));"
assert old.count(lookup) == old.count(perf) == 1
assert host == old.replace(lookup, fixed), "common emitter exact source drift"
assert native == host.replace(perf, ""), "native emitter exact source drift"
assert "LocationDescriptorToFriendlyName(descriptor)" not in native
assert "patch_information.find(target_desc)" in native
assert 'write_derived("${PORT_BUILD_DIR}/emit_x64.cpp"' not in cmake
assert 'configure_file("${EDEN_EMIT_X64_SOURCE}" "${PORT_BUILD_DIR}/emit_x64.cpp" COPYONLY)' in cmake

first = cmake.index('set(EDEN_MAINTAINED_EMIT_X64_ROOT "')
last = cmake.index('get_target_property(jit_sources dynarmic SOURCES)', first)
selection = cmake[first:last]
assert shutil.which("cmake"), "CMake unavailable for profile selection proof"
with tempfile.TemporaryDirectory(prefix="encore-x64-patch-owner-") as folder:
    root_temp = Path(folder)
    for native_mode in (False, True):
        folder_profile = root_temp / ("native" if native_mode else "host")
        folder_profile.mkdir()
        script = root_temp / ("native.cmake" if native_mode else "host.cmake")
        script.write_text(
            "cmake_minimum_required(VERSION 3.25)\n"
            + f'set(PORT_ROOT "{root.as_posix()}")\n'
            + f'set(PORT_BUILD_DIR "{folder_profile.as_posix()}")\n'
            + f'set(PS5_NATIVE {"ON" if native_mode else "OFF"})\n'
            + selection
        )
        subprocess.run(["cmake", "-P", str(script)], check=True, timeout=30)
        assert (folder_profile / "emit_x64.cpp").read_text() == (native if native_mode else host)
print("ENCORE_MAINTAINED_COMMON_EMITTER_PASS host/native=2 lookup=exact perfmap=native-removed")
