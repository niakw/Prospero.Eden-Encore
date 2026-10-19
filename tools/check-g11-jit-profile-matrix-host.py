#!/usr/bin/env python3
"""Run G11/X06 CMake source-generation matrix (host-only, no hardware proof)."""
from pathlib import Path
import hashlib
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cmake = (root / "headless/CMakeLists.txt").read_text()
start = 'foreach(bits 32 64)\n    set(relative "arm/dynarmic/arm_dynarmic_${bits}.cpp")'
finish = 'endforeach()\n# G12: complete maintained PhysicalCore sources.'
assert cmake.count(start) == cmake.count(finish) == 1
recipe = cmake[cmake.index(start):cmake.index(finish)+len("endforeach()")]
assert recipe.count('write_derived("${derived}" "#include <bit>\\n${wrapper}")') == 1
assert 'include("${EDEN_PORT_DIR}/native_jit_memory_read_guard.cmake")' in recipe
assert recipe.count("foreach(bits 32 64)") == 1

pinned = {bits:(root/f"vendor/sources/eden/src/core/arm/dynarmic/arm_dynarmic_{bits}.cpp").read_text()
          for bits in (32,64)}
for bits in (32,64):
    existing = (root/f"vendor/encore-active/eden-core/src/core/arm/dynarmic/arm_dynarmic_{bits}.cpp").read_text()
    assert "ConstructWithCapacityFallback" not in existing
    assert "if (!CheckMemoryAccess(vaddr" not in existing

outputs = {}
with tempfile.TemporaryDirectory(prefix="encore-g11-matrix-") as tempdir:
    temp = Path(tempdir)
    for native in (False, True):
        for dev in (False, True):
            for inline in (False, True):
                label = f"{'native' if native else 'host'}_{'dev' if dev else 'normal'}_{'inline' if inline else 'monitor'}"
                project = temp/label
                project.mkdir()
                stage = project/"stage"
                stage.mkdir()
                (project/"empty.cpp").write_text("int g11_matrix_fixture() { return 0; }\n")
                setup = r'''cmake_minimum_required(VERSION 3.24)
project(EncoreG11Matrix LANGUAGES CXX)
set(PORT_ROOT "__ROOT__")
set(PROJECT_SOURCE_DIR "__ROOT__/vendor/sources/eden")
set(EDEN_PORT_DIR "__ROOT__/headless")
set(PORT_BUILD_DIR "__STAGE__")
set(PS5_NATIVE __NATIVE__)
set(EDEN_DEV_PROFILE __DEV__)
set(EDEN_INLINE_EXCLUSIVES __INLINE__ CACHE BOOL "G11 matrix" FORCE)
add_library(core STATIC "${CMAKE_CURRENT_SOURCE_DIR}/empty.cpp"
    arm/dynarmic/arm_dynarmic_32.cpp arm/dynarmic/arm_dynarmic_64.cpp)
function(write_derived path content)
    file(WRITE "${path}" "${content}")
endfunction()
'''
                setup = (setup.replace("__ROOT__", str(root))
                              .replace("__STAGE__", str(stage))
                              .replace("__NATIVE__", "ON" if native else "OFF")
                              .replace("__DEV__", "ON" if dev else "OFF")
                              .replace("__INLINE__", "ON" if inline else "OFF"))
                (project/"CMakeLists.txt").write_text(setup + recipe + '''
get_target_property(g11_sources core SOURCES)
file(WRITE "${PORT_BUILD_DIR}/selected.txt" "${g11_sources}")
''')
                result = subprocess.run(
                    ["cmake","-S",str(project),"-B",str(project/"build")],
                    capture_output=True, text=True, timeout=60)
                if result.returncode:
                    print(result.stdout[-3000:],result.stderr[-5500:])
                    raise AssertionError("G11 source matrix configure failed: "+label)
                owners = (stage/"selected.txt").read_text().split(";")
                for bits in (32,64):
                    src = (stage/f"arm_dynarmic_{bits}.cpp").read_text()
                    assert owners.count(str(stage/f"arm_dynarmic_{bits}.cpp")) == 1, (label,bits)
                    assert f"arm/dynarmic/arm_dynarmic_{bits}.cpp" not in owners, (label,bits)
                    assert len(src)>len(pinned[bits])-200, (label,bits)
                    assert src.startswith("#include <bit>\n"), (label,bits)
                    assert src.count("std::countl_zero(Common::PageTable::ATTRIBUTE_MASK)") == 1
                    assert "Common::PageTable::SIGN_BIT" not in src
                    assert "std::uint32_t(512_MiB)" not in src
                    assert ('config.fastmem_exclusive_access = true;' in src) == inline, (label,bits)
                    assert ('/performance.h"' in src) == dev, (label,bits)
                    assert ("::Eden::Performance::CpuSampleDue" in src) == dev, (label,bits)
                    if native:
                        assert "ConstructWithCapacityFallback" in src, (label,bits)
                        assert "experimental_performance.h" in src, (label,bits)
                        assert "jit-startup-retry.h" in src, (label,bits)
                        assert src.count("if (!CheckMemoryAccess(vaddr") == (4 if bits==32 else 5)
                        assert ("::Eden::Experimental::A32CacheBytes" in src) == (bits==32)
                        assert ("::Eden::Experimental::A64CacheBytes" in src) == (bits==64)
                    else:
                        assert "ConstructWithCapacityFallback" not in src, (label,bits)
                        assert "if (!CheckMemoryAccess(vaddr" not in src, (label,bits)
                    if dev and bits==32:
                        assert "::Eden::Performance::CountJit(" in src
                        assert "::Eden::Watch::Hit(" not in src
                    if dev and bits==64:
                        assert "::Eden::Watch::Hit(" in src
                        assert "::Eden::CrashSite::Dump(" in src
                    outputs[(native,dev,inline,bits)] = src
                assert len(owners) == 3, (label,owners)
    for bits in (32,64):
        assert len({hashlib.sha256(value.encode()).digest()
                    for (native,dev,inline,arch),value in outputs.items()
                    if arch == bits}) == 8
print("ENCORE_G11_X06_REAL_CMAKE_PROFILE_MATRIX_PASS cases=8 units=16")
print("ENCORE_G11_NATIVE_MEMORY_READ_GUARD_MATRIX_PASS widths32=4 widths64=5")
print("ENCORE_G11_SOURCE_OWNER_MATRIX_PASS exact_core_owners=2 host_only=1")
