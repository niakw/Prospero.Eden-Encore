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
    assert len(before) == len(after) == 5
    assert before.keys() == after.keys(), f'changed file list: {before.keys() ^ after.keys()}'
    for relative in before:
        assert filecmp.cmp(before[relative], after[relative], shallow=False), relative
    print('VENDORED_RADV_FORK_EQUIVALENT_OK count=5 patch_oracle_matches_active_sources')

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
print('VENDORED_RADV_ACTIVE_INSTALL_OK immutable Mesa pin, bounded install, unknown-source rejection')
