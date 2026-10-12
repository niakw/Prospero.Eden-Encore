#!/usr/bin/env python3
"""Byte-for-byte pinned Mesa adaptation replay and production installer checks."""
from __future__ import annotations
import filecmp
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / 'vendor/encore-active/ps5-mesa'
SOURCE = ROOT / 'vendor/sources/ps5-mesa'
assert (SOURCE / 'VENDOR-ORIGIN.json').is_file()
with tempfile.TemporaryDirectory(prefix='eden-radv-fork-equivalence-') as tmp:
    temp = Path(tmp)
    subprocess.run([sys.executable, '-B', str(ROOT / 'tools/patch-radv-wsi.py'), '--oracle',
                    str(SOURCE), str(temp)], check=True, capture_output=True, text=True, timeout=60)
    before = {str(p.relative_to(temp)): p for p in temp.rglob('*') if p.is_file()}
    after = {str(p.relative_to(ACTIVE)): p for p in ACTIVE.rglob('*') if p.is_file()}
    assert len(before) == len(after) == 10
    assert before.keys() == after.keys(), f'changed file list: {before.keys() ^ after.keys()}'
    for relative in before:
        assert filecmp.cmp(before[relative], after[relative], shallow=False), relative
    print('VENDORED_RADV_FORK_EQUIVALENT_OK count=10 patch_oracle_matches_active_sources')

    # Replay installation from the EXACT original pinned inputs, then retry
    # idempotently. Unexpected prior modifications must fail closed.
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location('install_active_radv', ROOT / 'tools/install-vendored-radv.py')
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    source_stage = temp / 'staged'
    for relative in before:
        file = source_stage / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / relative, file)
    provenance = temp / 'PROVENANCE.txt'
    provenance.write_text('upstream native build receipt')
    module.install(source_stage, provenance)
    assert not provenance.exists() and provenance.with_suffix('.base.txt').exists()
    module.install(source_stage, provenance)
    for relative in before:
        assert filecmp.cmp(source_stage / relative, ACTIVE / relative, shallow=False)
    # A restored actions/cache can contain multiple R343 active RADV units
    # simultaneously. Test the entire mixed-generation staging tree: old
    # complete files -> canonical current inputs, then enforce idempotence.
    historical = {
        'src/vulkan/wsi/wsi_common_videoout.c':
            ROOT / 'tools/fixtures/ps5-r398-wsi-videoout.c',
        'src/amd/vulkan/radv_cmd_buffer.c':
            ROOT / 'tools/fixtures/ps5-r343-radv-cmd-buffer.c',
        'src/amd/vulkan/radv_physical_device.c':
            ROOT / 'tools/fixtures/ps5-r343-radv-physical-device.c',
        'src/amd/vulkan/winsys/ps5/radv_ps5_winsys.c':
            ROOT / 'tools/fixtures/ps5-r343-radv-winsys.c',
        'src/amd/vulkan/winsys/ps5/radv_ps5_platform.c':
            ROOT / 'tools/fixtures/ps5-r343-radv-platform.c',
    }
    assert set(module.LEGACY_COMPILER_SHA256) == set(historical)
    for relative, fixture in historical.items():
        old_sha = module.digest(fixture)
        assert old_sha in module.LEGACY_COMPILER_SHA256[relative], relative
        assert module.approved_compiler_input(
            relative, old_sha, module.digest(SOURCE / relative),
            module.digest(ACTIVE / relative))
        for unrelated in before:
            if unrelated == relative:
                continue
            assert not module.approved_compiler_input(
                unrelated, old_sha, module.digest(SOURCE / unrelated),
                module.digest(ACTIVE / unrelated)), (relative, unrelated)
        shutil.copy2(fixture, source_stage / relative)
    module.install(source_stage, None)
    module.install(source_stage, None)
    for relative in before:
        assert filecmp.cmp(source_stage / relative, ACTIVE / relative, shallow=False), relative

    # Do not quietly clobber unknown source changes in a fresh driver export.
    invalid = source_stage / next(iter(before))
    invalid.write_bytes(b'unexpected unknown upstream revision')
    try:
        module.install(source_stage, None)
    except RuntimeError as exc:
        assert 'Unrecognized RADV compiler input' in str(exc), str(exc)
    else:
        raise AssertionError('unexpected Mesa source rewrite was accepted')

build = (ROOT / 'tools/build-radv-dependencies.sh').read_text()
assert 'install-vendored-radv.py' in build
assert 'python3 "$root/tools/patch-radv-wsi.py"' not in build
assert build.count('bash "$vulkan/tools/build-radv.sh" release') == 2
assert 'EDEN_WSI_SHA256' in build
print('VENDORED_RADV_ACTIVE_INSTALL_OK immutable Mesa pin, mixed R343/R398 cached inputs, unknown-source rejection')
