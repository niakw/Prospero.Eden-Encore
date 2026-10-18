#!/usr/bin/env python3
"""G15: exact historical generator equivalence and native-only source selection."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
original = root / "vendor/sources/eden/src/core/loader/nso.cpp"
maintained = root / "vendor/encore-active/eden-core/src/core/loader/nso.cpp"
cmake = (root / "headless/CMakeLists.txt").read_text()
oracle = root / "tools/fixtures/retired-g15-nso.cmake"
assert original.is_file() and maintained.is_file() and oracle.is_file()
assert original.read_bytes() != maintained.read_bytes()
assert 'set(EDEN_MAINTAINED_NATIVE_NSO' in cmake
assert cmake.count('configure_file("${EDEN_MAINTAINED_NATIVE_NSO}" "${PORT_BUILD_DIR}/nso.cpp" COPYONLY)') == 1
assert 'list(REMOVE_ITEM core_sources loader/nso.cpp)' in cmake
assert 'list(APPEND core_sources "${PORT_BUILD_DIR}/nso.cpp")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/nso.cpp"' not in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/loader/nso.cpp"' not in cmake
assert cmake.index('if(PS5_NATIVE)\n    set(EDEN_MAINTAINED_NATIVE_NSO') < cmake.index('list(REMOVE_ITEM core_sources core.cpp)')
assert 'DecompressDataZBIC' in maintained.read_text()
assert 'ZeroBlock(load_base + codeset.memory.size()' in maintained.read_text()
with tempfile.TemporaryDirectory(prefix="encore-nso-oracle-") as tmp:
    subprocess.run([
        "cmake", "-DPS5_NATIVE=ON",
        f"-DPROJECT_SOURCE_DIR={root / 'vendor/sources/eden'}",
        f"-DPORT_BUILD_DIR={tmp}", "-P", str(oracle),
    ], check=True, capture_output=True, text=True)
    derived = Path(tmp) / "nso.cpp"
    assert derived.read_bytes() == maintained.read_bytes(), "G15: byte parity changed"
print("ENCORE_MAINTAINED_NSO_PARITY_PASS G15=retired native=copy-only")
