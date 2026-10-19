#!/usr/bin/env python3
"""Run G11/X06 CMake source-generation matrix (host-only, no hardware proof)."""
from pathlib import Path
import base64
import difflib
import hashlib
import json
import os
import re
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

# Production installs these qualified I-cache owners into the prepared
# upstream tree BEFORE the native CMake recipe reads PROJECT_SOURCE_DIR.
# Starting from raw vendor/sources/eden would silently drop J19/J20.
backport_root = root/"vendor/encore-active/eden-core/src/core/arm/dynarmic"
pinned = {bits:(backport_root/f"arm_dynarmic_{bits}.cpp").read_text()
          for bits in (32,64)}
assert "Core::InvalidateInstructionCacheRange" in pinned[64]
assert '#include "core/arm/debug.h"' in pinned[64]
assert pinned[32].count("m_cb->last_code_addr = u64(-1);") >= 2
for bits in (32,64):
    existing = (root/f"vendor/encore-active/eden-core/src/core/arm/dynarmic/arm_dynarmic_{bits}.cpp").read_text()
    assert "ConstructWithCapacityFallback" not in existing
    assert "if (!CheckMemoryAccess(vaddr" not in existing

outputs = {}
with tempfile.TemporaryDirectory(prefix="encore-g11-matrix-") as tempdir:
    temp = Path(tempdir)
    prepared = temp/"prepared-core"
    for bits in (32,64):
        staged = prepared/f"src/core/arm/dynarmic/arm_dynarmic_{bits}.cpp"
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text(pinned[bits])
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
set(PROJECT_SOURCE_DIR "__PREPARED__")
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
                              .replace("__PREPARED__", str(prepared))
                              .replace("__NATIVE__", "ON" if native else "OFF")
                              .replace("__DEV__", "ON" if dev else "OFF")
                              .replace("__INLINE__", "ON" if inline else "OFF"))
                (project/"CMakeLists.txt").write_text(setup + recipe + '''
# The real root CMake batches core_sources changes before applying the
# target property later. Reproduce that finalization in this focused fixture.
set_property(TARGET core PROPERTY SOURCES "${core_sources}")
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
                    if bits == 64:
                        assert "Core::InvalidateInstructionCacheRange" in src
                        assert '#include "core/arm/debug.h"' in src
                    else:
                        assert src.count("m_cb->last_code_addr = u64(-1);") >= 2
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
                    # G11 candidate parity for every current CMake profile.
                    # Only absolute private includes and the compile-time
                    # inline/exclusive dispatch are normalized.
                    owner = root/"vendor/encore-active/eden-core/src/core/arm/dynarmic/g11"/(
                        f"arm_dynarmic_{bits}_{'native' if native else 'host'}_{'dev' if dev else 'normal'}.cpp")
                    candidate = owner.read_text()
                    expected = src
                    for header in ("experimental_performance.h", "performance.h",
                                   "jit-startup-retry.h", "crash_site.h", "watch.h"):
                        expected = expected.replace(
                            '#include "'+str(root/"headless"/header)+'"',
                            '#include "'+header+'"')
                    match = re.search(
                        r'(?m)^([ \t]*)#if defined\(EDEN_INLINE_EXCLUSIVES\) && EDEN_INLINE_EXCLUSIVES\n'
                        r'\1config\.fastmem_exclusive_access = true;\n'
                        r'\1#else\n'
                        r'(?P<fallback>[ \t]*config\.fastmem_exclusive_access = config\.fastmem_pointer +!= std::nullopt;)\n'
                        r'\1#endif', candidate)
                    assert match is not None, (label,bits,"inline guard missing")
                    chosen = (match.group(1)+"config.fastmem_exclusive_access = true;"
                              if inline else match.group("fallback"))
                    assert candidate.replace(match.group(0),chosen) == expected, (
                        label,bits,"G11 maintained source parity drift")
                    outputs[(native,dev,inline,bits)] = src
                    # One-time migration bridge: emit compact line-based
                    # deltas against pinned public sources in CI logs. They
                    # are reconstructed and committed as full Encore C++
                    # owners; this does not run on shipping builds.
                    if os.environ.get("ENCORE_EXPORT_G11_PATCHES") == "1" and not inline:
                        before_lines = pinned[bits].splitlines(keepends=True)
                        source_lines = src.splitlines(keepends=True)
                        matcher = difflib.SequenceMatcher(
                            None, before_lines, source_lines, autojunk=False)
                        edits = [[i1, i2, "".join(source_lines[j1:j2])]
                                 for tag,i1,i2,j1,j2 in matcher.get_opcodes()
                                 if tag != "equal"]
                        encoded = base64.b64encode(json.dumps(
                            edits, ensure_ascii=True, separators=(",",":")).encode("utf-8")).decode("ascii")
                        print("ENCORE_G11_PATCH_BEGIN", label, bits, len(encoded), flush=True)
                        for part in range(0, len(encoded), 2048):
                            print("ENCORE_G11_PATCH_CHUNK", label, bits,
                                  part // 2048, encoded[part:part+2048], flush=True)
                        print("ENCORE_G11_PATCH_END", label, bits, flush=True)

                assert len(owners) == 2, (label,owners)
    for bits in (32,64):
        assert len({hashlib.sha256(value.encode()).digest()
                    for (native,dev,inline,arch),value in outputs.items()
                    if arch == bits}) == 8
print("ENCORE_G11_MAINTAINED_SOURCE_PARITY_PASS variants=8 profiles=16")
print("ENCORE_G11_X06_REAL_CMAKE_PROFILE_MATRIX_PASS cases=8 units=16")
print("ENCORE_G11_NATIVE_MEMORY_READ_GUARD_MATRIX_PASS widths32=4 widths64=5")
print("ENCORE_G11_SOURCE_OWNER_MATRIX_PASS exact_core_owners=2 host_only=1")
