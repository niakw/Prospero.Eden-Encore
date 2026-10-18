#!/usr/bin/env python3
"""Pin complete A64 source owners, their historical bodies and CMake selection.

Host source/selection evidence only; not a PS5 firmware/build qualification.
"""
from pathlib import Path
import hashlib
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
owner = root / "vendor/encore-active/eden-core/src/dynarmic/backend/x64"
standard = (owner / "a64_interface_standard.cpp").read_text()
shared = (owner / "a64_interface_shared.cpp").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
assert not (root / "headless/jit-compile-batch.inc").exists()
assert 'write_derived("${PORT_BUILD_DIR}/a64_interface.cpp"' not in cmake
assert 'configure_file("${EDEN_A64_INTERFACE_UNIT}" "${PORT_BUILD_DIR}/a64_interface.cpp" COPYONLY)' in cmake
for flag in ("EDEN_JIT_A64_BATCH=1", "EDEN_JIT_A64_DEV_PROFILE=1", "PS5_NATIVE=1"):
    assert 'APPEND PROPERTY COMPILE_DEFINITIONS "' + flag + '"' in cmake

def git_blob(content):
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()

# DEV instrumentation surrounds but does not modify the original batch body.
batch = standard.split("#if defined(EDEN_JIT_A64_BATCH)\n", 1)[1].split(
    "\n#else\n        const auto get_code", 1)[0]
phase = re.search(r"#if defined\(EDEN_JIT_A64_DEV_PROFILE\)\n.*?\n#else\n(.*?)\n#endif", batch, re.S)
assert phase, "batch DEV timing isolation missing"
batch = batch[:phase.start()] + phase.group(1) + batch[phase.end():] + "\n"
assert git_blob(batch.encode()) == "a1648168121822bb5c8a1fc8233a12a3771e55da", (
    "maintained compile batch differs from reviewed historical 2557-byte body"
)
assert "#if defined(EDEN_JIT_A64_BATCH)" in standard
assert "#if defined(EDEN_JIT_A64_DEV_PROFILE)" in standard
assert "#ifdef PS5_NATIVE" in standard
assert "if (eden_native_detailed_logging && eden_native_detailed_logging() && ++pressure_count <= 200)" in standard

# Shared mode used to replace Jit::Impl entirely after the standard edits.
# Verify the maintained variant preserves the original exact support+Impl.
pinned = (root / "vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64/a64_interface.cpp").read_text()
support = (root / "vendor/encore-active/eden-core/dynarmic/shared-jit/jit_group_support.inc").read_text()
impl = (root / "vendor/encore-active/eden-core/dynarmic/shared-jit/jit_impl.inc").read_text()
start = pinned.index("struct Jit::Impl final {")
end = pinned.index("Jit::Jit(UserConfig conf)", start)
assert shared.endswith(pinned[:start] + support + "\n" + impl + "\n" + pinned[end:])
assert "macro(eden_shared_jit_interface)" not in (root / "headless/dynarmic/shared-jit.cmake").read_text()

# Replay selected CMake configure_file for all profile combinations, without
# recompiling or mutating third-party dependencies.
start = cmake.index('set(EDEN_A64_INTERFACE_ROOT "')
end = cmake.index('get_target_property(jit_sources dynarmic SOURCES)', start)
selection = cmake[start:end]
assert shutil.which("cmake"), "CMake required for source selection validation"
with tempfile.TemporaryDirectory(prefix="encore-a64-selection-") as folder:
    folder = Path(folder)
    for shared_mode in (False, True):
        for native in (False, True):
            for batch_enabled in (False, True):
                for dev in (False, True):
                    label = f"{'shared' if shared_mode else 'standard'}-{int(native)}-{int(batch_enabled)}-{int(dev)}"
                    output = folder / label
                    output.mkdir()
                    script = folder / (label + ".cmake")
                    script.write_text(
                        "cmake_minimum_required(VERSION 3.25)\n"
                        + f'set(PORT_ROOT "{root.as_posix()}")\n'
                        + f'set(PORT_BUILD_DIR "{output.as_posix()}")\n'
                        + f'set(EDEN_SHARED_JIT {"ON" if shared_mode else "OFF"})\n'
                        + f'set(PS5_NATIVE {"ON" if native else "OFF"})\n'
                        + f'set(EDEN_JIT_COMPILE_BATCH {"ON" if batch_enabled else "OFF"})\n'
                        + f'set(EDEN_DEV_PROFILE {"ON" if dev else "OFF"})\n'
                        + selection
                    )
                    subprocess.run(["cmake", "-P", str(script)], check=True, timeout=30)
                    expected = shared if shared_mode else standard
                    assert (output / "a64_interface.cpp").read_text() == expected
print("MAINTAINED_A64_INTERFACE_PASS source_modes=2 profile_stages=16 batch_blob=exact")
