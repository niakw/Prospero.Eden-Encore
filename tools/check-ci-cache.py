#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep GitHub's native cache genuinely restorable instead of silently rejecting sibling paths."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
workflow = (root / ".github/workflows/build-040-zbic.yml").read_text()
linker = (root / "tools/ci/link-sibling-deps.sh").read_text()
build = (root / "tools/build-headless-native.sh").read_text()
deps = (root / "tools/deps.py").read_text()

for path in (
    "../ps5-native-app-boilerplate",
    "../ps5-opengl-review",
    "../mihawk-vulkan-review",
    "../mihawk-mesa-review",
    "../mihawk-sdk-review",
):
    assert path not in workflow, f"actions/cache still contains unsupported path {path}"

# Native all-on builds must provision the same Boost.Container header as
# the separate host-only core preflight. Four Vulkan host C++ checks consume
# boost/container/small_vector.hpp before PS5-native compilation starts.
host_workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
native_toolchain = workflow.split("      - name: Install build toolchain", 1)[1].split(
    "      - name: Upgrade Meson", 1)[0]
assert "libboost-container-dev" in host_workflow
assert "libboost-container-dev" in native_toolchain
assert "clang++-18 -std=c++20 -x c++ -fsyntax-only -" in native_toolchain
assert native_toolchain.index("libboost-container-dev") < native_toolchain.index(
    "clang++-18 -std=c++20 -x c++ -fsyntax-only -"
)
assert "PROSPEROEDEN_GIT_DEPS_ROOT: .deps/repos" in workflow
assert "PROSPEROEDEN_GIT_DEPS_ROOT" in deps
assert "item.get('path', '').startswith('../')" in deps
assert "pathlib.Path(item['path']).name" in deps
assert "PROSPEROEDEN_GIT_DEPS_ROOT" in linker

assert workflow.count("            .deps\n") == 2
assert "Prepare cacheable sibling dependency paths" in workflow
assert workflow.index("Prepare cacheable sibling dependency paths") < workflow.index("Prepare native build inputs")
for name in (
    "ps5-native-app-boilerplate",
    "ps5-opengl-review",
    "mihawk-vulkan-review",
    "mihawk-mesa-review",
    "mihawk-sdk-review",
):
    assert name in linker
assert '.deps/repos' in linker

assert "fork-source-stamps.json" in build
assert "sha256(path.read_bytes())" in build
assert "os.utime(path" in build
assert "-exec touch" not in build
# Catch PS5 ABI/source errors before spending time on the native Ninja build.
assert '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON' in build
assert 'tools/check-native-source-syntax.py' in build
assert build.index('tools/check-native-source-syntax.py') < build.index('cmake --build "$scratch/native-local"')
# The R422 all-on compile reached a potentially lengthy cache upload BEFORE
# GitHub saved the usable PS5 zip. Never sacrifice a successful build artifact
# to optional cache persistence: publish and verify first, cache last.
assert workflow.index("Upload checked all-on PS5 test app") < workflow.index("Save build caches after verified artifact uploads")
assert workflow.index("Upload unstripped PS5 All-On crash symbols") < workflow.index("Save build caches after verified artifact uploads")
assert workflow.index("Upload compiled release bundle") < workflow.index("Save build caches after verified artifact uploads")
cache_block = workflow.split("      - name: Save build caches after verified artifact uploads", 1)[1].split("  release:", 1)[0]
assert "continue-on-error: true" in cache_block, "optional cache write must not fail artifact delivery"
print("Encore CI incremental-cache and early syntax gate contract PASS")
