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
print("Encore CI incremental-cache contract PASS")
