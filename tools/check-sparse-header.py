#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every compiled file must have seen the derived common/sparse_large_vector.h.

The header's inline functions decide how Eden's large tables take their memory. The port
replaces it for all targets by an include folder that comes first (headless/inject.cmake). A
source file that still saw the original would announce a table's first write with mprotect
while the others give the slot memory of its own: this reads the build's dependency records and
fails when any object depends on the original header.

  check-sparse-header.py <build folder>
"""
import pathlib
import subprocess
import sys

build = pathlib.Path(sys.argv[1]).resolve()
root = pathlib.Path(__file__).resolve().parents[1]
canonical = root / 'vendor/encore-active/eden-core/src/common/sparse_large_vector.h'
copied = build / 'headless/sparse/common/sparse_large_vector.h'
if not copied.is_file() or copied.read_bytes() != canonical.read_bytes():
    sys.exit('sparse header check failed: native copy differs from maintained canonical header')
accepted = {canonical.resolve(), copied.resolve()}
deps = subprocess.run(['ninja', '-C', str(build), '-t', 'deps'], capture_output=True, text=True, check=True).stdout
original, derived, target = [], 0, None
for line in deps.splitlines():
    if line and not line.startswith(' '):
        target = line.split(':', 1)[0]
        continue
    path = line.strip()
    if not path.endswith('common/sparse_large_vector.h'):
        continue
    header = pathlib.Path(path.replace('\\', '/'))
    if not header.is_absolute():
        header = build / header
    if header.resolve() in accepted:
        derived += 1
    else:
        original.append(f'{target}: {path}')
if original or derived == 0:
    for line in original[:20]:
        print('  saw the original header:', line)
    sys.exit(f'sparse header check failed: {len(original)} objects saw the original, {derived} the derived one')
print(f'Sparse table header: {derived} objects compiled with identical canonical/derived headers, none with the original PASS')
