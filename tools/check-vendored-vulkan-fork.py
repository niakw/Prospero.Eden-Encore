#!/usr/bin/env python3
"""Verify tracked native Vulkan C++ fork exactly matches validated R337 source generator."""
from pathlib import Path
import filecmp
import hashlib
import os
import shutil
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
    # The *production* renderer has always consumed Eden AFTER the ordered
    # 43 shipping backports, not the pristine archive. Reproduce that exact
    # working source before comparing the versioned Vulkan C++ translation
    # units; otherwise stale GPU lifetime / texture-cache patches leak in.
    patched=temp/'patched-eden'
    shutil.copytree(upstream,patched,symlinks=True)
    (patched/'GIT-COMMIT').write_text('5f142c7926d0c7fcbbd0ce30794d72f638a43b2a\n')
    subprocess.run([sys.executable,'-B',str(root/'tools/install-vendored-eden-backports.py'),
                    str(patched)],check=True,timeout=50,capture_output=True,text=True)
    # Pin shader input text separately from binary reproducibility. Avoid
    # depending on a nondeterministic host glslangValidator version in CI.
    expected_shaders={
        'vert':'b7efb0f17a2cfb2ac044d0d678dfd7f970323deef86c10d25dde8ed723ef0290',
        'frag':'eb91764f71e68593be5ddcc71599b9d66ed9d67ec49b44ff7b52473800ea3783',
    }
    for stage, digest in expected_shaders.items():
        source=root/'headless'/f'vulkan_hud.{stage}'
        assert hashlib.sha256(source.read_bytes()).hexdigest()==digest,source
        assert (active/f'vulkan_hud.{stage}.spv').is_file()
    env=os.environ.copy()
    env['EDEN_VULKAN_ORACLE_SPV_DIR']=str(active)
    subprocess.run([sys.executable,'-B',str(root/'tools/prepare-vulkan-port.py'),str(patched),str(temp/'generated')],check=True,timeout=150,env=env)
    actual={str(p.relative_to(temp/'generated')):p for p in (temp/'generated').rglob('*') if p.is_file()}
    expected={str(p.relative_to(active)):p for p in active.rglob('*') if p.is_file()}
    assert actual.keys()==expected.keys(),f'missing: {actual.keys()-expected.keys()}, extras: {expected.keys()-actual.keys()}'
    mismatches=[name for name in sorted(actual) if not filecmp.cmp(actual[name],expected[name],shallow=False)]
    if mismatches:
        # Print a tightly bounded exact diff before failing. The generator and
        # active files previously looked equivalent in high-level assertions,
        # forcing repeated CI runs to diagnose a single byte of drift.
        from difflib import unified_diff
        from itertools import islice
        for name in mismatches[:5]:
            generated, versioned = actual[name], expected[name]
            if not name.endswith(('.cpp', '.h', '.py', '.cmake')):
                print(f'VULKAN_ORACLE_BINARY_DIFF {name} SHA256={hashlib.sha256(generated.read_bytes()).hexdigest()} '
                      f'active_SHA256={hashlib.sha256(versioned.read_bytes()).hexdigest()}', flush=True)
                continue
            diff = unified_diff(generated.read_text().splitlines(keepends=True),
                                versioned.read_text().splitlines(keepends=True),
                                fromfile=f'generated/{name}', tofile=f'active/{name}')
            for line in islice(diff, 130):
                print(line, end='', flush=True)
        raise AssertionError(f'vendored Vulkan C++ differs from pinned generated source: {mismatches}')
    # Versioned code must compile after fresh clone at a different checkout
    # path: forbids CMake/host absolute paths embedded in generated C++.
    for name, file in expected.items():
        if name.endswith(('.cpp', '.h')):
            data=file.read_text()
            assert '#include "/private/tmp/' not in data and '#include "/home/runner/' not in data,(name,'checkout-specific include')
    assert '#include "performance.h"' in expected['vk_pipeline_cache_cost.cpp'].read_text()
    assert len(actual)>=35
    cmake=(root/'headless/vulkan.cmake').read_text()
    assert 'vendor/encore-active/eden-vulkan' in cmake
    assert 'file(COPY "${EDEN_ACTIVE_VULKAN}/" DESTINATION "${PORT_BUILD_DIR}")' in cmake
    assert 'execute_process(COMMAND python3 "${PORT_ROOT}/tools/prepare-vulkan-port.py"' not in cmake
    print(f'VENDORED_VULKAN_FORK_EQUIVALENT_OK files={len(actual)} active=versioned not regenerated')
