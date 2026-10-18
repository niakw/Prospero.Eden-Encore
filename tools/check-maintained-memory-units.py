#!/usr/bin/env python3
"""Assert complete A32/A64 memory emitter ownership and shared-layout parity.

Build-stage selection is checked; console execution remains unqualified.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
active = root / "vendor/encore-active/eden-core/src/dynarmic/backend/x64"
pinned = root / "vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64"
cm = (root / "headless/CMakeLists.txt").read_text()
shared_cmake = (root / "headless/dynarmic/shared-jit.cmake").read_text()
assert "macro(eden_shared_jit_memory_unit bits)" not in shared_cmake
assert 'target_compile_definitions(dynarmic PRIVATE EDEN_SHARED_JIT_LAYOUT=1)' in shared_cmake
assert 'write_derived("${PORT_BUILD_DIR}/${memory_unit}"' not in cm

for arch in (32, 64):
    name = f"a{arch}_emit_x64_memory.cpp"
    original = (pinned / name).read_text()
    actual = (active / name).read_text()
    assert actual.endswith(original), ("pinned unit changed", name)
    prelude = actual[:-len(original)]
    assert prelude.startswith("#ifdef EDEN_SHARED_JIT_LAYOUT\n")
    assert prelude.endswith("#endif\n\n")
    assert prelude.count("#define EDEN_EXCLUSIVE_ADDRESS(reg)") == 1
    assert prelude.count("#define EDEN_EXCLUSIVE_VALUE(reg)") == 1
    assert prelude.count("#define EDEN_CONF_ARG()") == 1
    assert "offsetof(A64JitState, eden_exclusive_address)" in prelude if arch == 64 else (
        "GetExclusiveMonitorAddressPointer(conf.global_monitor, conf.processor_id)" in prelude
    )
    assert "offsetof(A64JitState, eden_conf)" in prelude if arch == 64 else (
        "reinterpret_cast<u64>(&conf)" in prelude
    )
    assert f'configure_file("[object Object]"'
    assert "EDEN_EXCLUSIVE_ADDRESS" not in original
    assert "EDEN_CONF_ARG" not in original

# Stage the actual selection loop through CMake with target actions isolated.
first = cm.index('set(EDEN_MAINTAINED_MEMORY_UNIT_DIR\n')
last = cm.index('get_target_property(jit_sources dynarmic SOURCES)', first)
first_stage = cm[first:last]
assert "vendor/encore-active/eden-core/src/dynarmic/backend/x64" in first_stage
assert shutil.which("cmake"), "CMake missing"
with tempfile.TemporaryDirectory(prefix="eden-memory-unit-") as tmp:
    tmp = Path(tmp)
    for shared in (False, True):
        for native in (False, True):
            output = tmp / f"{int(shared)}-{int(native)}"
            output.mkdir()
            script = tmp / f"{int(shared)}-{int(native)}.cmake"
            script.write_text(
                "cmake_minimum_required(VERSION 3.25)\n"
                + f'set(PORT_ROOT "{root.as_posix()}")\n'
                + f'set(PORT_BUILD_DIR "{output.as_posix()}")\n'
                + f'set(EDEN_SHARED_JIT {"ON" if shared else "OFF"})\n'
                + f'set(PS5_NATIVE {"ON" if native else "OFF"})\n'
                + first_stage
                + 'foreach(bits 32 64)\n'
                + '  set(memory_unit "a${bits}_emit_x64_memory.cpp")\n'
                + '  configure_file("${EDEN_MAINTAINED_MEMORY_UNIT_DIR}/${memory_unit}"'
                  ' "${PORT_BUILD_DIR}/${memory_unit}" COPYONLY)\n'
                + 'endforeach()\n'
            )
            subprocess.run(["cmake", "-P", str(script)], check=True, timeout=30)
            for arch in (32, 64):
                name = f"a{arch}_emit_x64_memory.cpp"
                assert (output / name).read_bytes() == (active / name).read_bytes()
print("ENCORE_MAINTAINED_MEMORY_UNITS_PASS arches=2 selections=4")
