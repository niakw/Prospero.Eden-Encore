#!/usr/bin/env python3
"""Guard complete, tracked native CMake fork against generated/unreviewed changes.

This is one migrated build-configuration translation unit, not a certificate
that remaining CMake write_derived code paths have been consolidated.
"""
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
original = (root/"vendor/sources/eden/src/CMakeLists.txt").read_text()
active = (root/"vendor/encore-active/eden-build/src/CMakeLists.txt").read_text()
inject = (root/"headless/inject.cmake").read_text()
builder = (root/"tools/build-headless-native.sh").read_text()

old = '$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error-all>'
new = '$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error=all>'
assert original.count(old) == 1
assert old not in active
assert active == original.replace(old, new), "active native CMake has unreviewed drift"
assert inject.count('configure_file("${EDEN_ACTIVE_BUILD_CMAKE}" "${EDEN_SNAPSHOT_BUILD_CMAKE}" COPYONLY)') == 1
assert 'eden_build_snapshot STREQUAL eden_build_original' in inject
assert 'eden_build_snapshot STREQUAL eden_build_active' in inject
assert 'if(PS5_NATIVE)' in inject.split('configure_file')[0]
assert 'CMAKE_PROJECT_yuzu_INCLUDE="$root/headless/inject.cmake"' in builder
clang = shutil.which("clang++-18") or shutil.which("clang++")
if clang:
    run = subprocess.run([clang, "-Wno-error=all", "-x", "c++", "-fsyntax-only", "-"],
                         input="int main(){return 0;}\n",
                         text=True, capture_output=True, timeout=10)
    assert run.returncode == 0, run.stderr
    assert "unknown" not in run.stderr.casefold(), run.stderr
print("PASS: complete tracked native CMake fork matches upstream except one supported Clang flag")
print("PASS: PS5-only guarded CMake source copy, upstream preservation and compiler flag")
