#!/usr/bin/env python3
"""Security R419: keep CodeQL exclusions narrow and first-party coverage intact.

This fixture deliberately checks policy source only. CodeQL default setup must
be pointed to the config using github-codeql-config-file in repository settings.
"""
from fnmatch import fnmatchcase
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
config = (root / ".github/codeql/codeql-config.yml").read_text()
doc = (root / "docs/CODEQL_SECURITY_TRIAGE_R419.md").read_text()
assert config.startswith("name: Eden Encore CodeQL")
patterns = re.findall(r"^\s+- '([^']+)'", config, flags=re.M)
expected = {
    "vendor/sources/**/libs/mpl/preprocessed/pp.py",
    "vendor/sources/**/tools/litre/cplusplus.py",
    "vendor/sources/**/bin/nir-test-runner.py",
    "vendor/sources/**/hb_test_tools.py",
    "vendor/sources/**/python/run_tests.py",
}
assert set(patterns) == expected, (patterns, expected)
def ignored(path: str) -> bool:
    return any(fnmatchcase(path, p) for p in patterns)

for path in (
    "vendor/sources/eden-cpm/boost/libs/mpl/preprocessed/pp.py",
    "vendor/sources/eden-cpm/boost/tools/litre/cplusplus.py",
    "vendor/sources/opengl-mesa-26-2/bin/nir-test-runner.py",
    "vendor/sources/ps5-mesa/bin/nir-test-runner.py",
    "vendor/sources/harfbuzz/test/shaping/hb_test_tools.py",
    "vendor/sources/harfbuzz/test/shaping/python/run_tests.py",
):
    assert ignored(path), path
for path in (
    "headless/main.cpp",
    "headless/network_domain_rules.c",
    "tools/ps-glyph-mod-discovery.py",
    "tools/check-guest-network-isolation.py",
    "tools/check-ps-glyph-curl-search.py",
    "vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp",
    "vendor/encore-active/ps5-mesa/src/util/disk_cache_os.c",
    "vendor/sources/eden/src/video_core/renderer_vulkan/vk_scheduler.cpp",
    "vendor/sources/harfbuzz/src/hb-shape.cc",
    "vendor/sources/ps5-mesa/src/amd/vulkan/radv_device.c",
):
    assert not ignored(path), path
assert "github-codeql-config-file" in doc
assert "default setup" in doc
assert "#23" in doc and "#28" in doc
print("R419 CodeQL scope policy: narrow third-party test exclusions PASS")
