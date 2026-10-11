#!/usr/bin/env python3
"""Verify tracked native Vulkan C++ fork exactly matches validated R337 source generator."""
from pathlib import Path
import filecmp
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
active=root/'vendor/encore-active/eden-vulkan'
upstream=root/'vendor/sources/eden'
assert (upstream/'VENDOR-ORIGIN.json').exists()
assert (active/'vulkan_renderer.cpp').exists()
with tempfile.TemporaryDirectory(prefix='eden-vulkan-fork-compare-') as d:
    temp=Path(d)
    subprocess.run([sys.executable,'-B',str(root/'tools/prepare-vulkan-port.py'),str(upstream),str(temp)],check=True,timeout=150)
    actual={str(p.relative_to(temp)):p for p in temp.rglob('*') if p.is_file()}
    expected={str(p.relative_to(active)):p for p in active.rglob('*') if p.is_file()}
    assert actual.keys()==expected.keys(),f'missing: {actual.keys()-expected.keys()}, extras: {expected.keys()-actual.keys()}'
    mismatches=[name for name in sorted(actual) if not filecmp.cmp(actual[name],expected[name],shallow=False)]
    assert not mismatches, f'vendored Vulkan C++ differs from pinned generated source: {mismatches}'
    assert len(actual)>=35
    cmake=(root/'headless/vulkan.cmake').read_text()
    assert 'vendor/encore-active/eden-vulkan' in cmake
    assert 'file(COPY "${EDEN_ACTIVE_VULKAN}/" DESTINATION "${PORT_BUILD_DIR}")' in cmake
    assert 'execute_process(COMMAND python3 "${PORT_ROOT}/tools/prepare-vulkan-port.py"' not in cmake
    print(f'VENDORED_VULKAN_FORK_EQUIVALENT_OK files={len(actual)} active=versioned not regenerated')
