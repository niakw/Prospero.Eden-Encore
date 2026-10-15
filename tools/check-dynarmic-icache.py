#!/usr/bin/env python3
from pathlib import Path
import sys
import subprocess, tempfile, shutil

root=Path(__file__).resolve().parents[1]
patch=root/'headless/backports/eden-dynarmic-icache-coherence.patch'
text=patch.read_text()
for needle in (
    '#include "core/arm/debug.h"',
    'Core::InvalidateInstructionCacheRange(m_process, cache_line_start, ICACHE_LINE_SIZE);',
    'InvalidateAllToPoUInnerSharable',
    'm_cb->last_code_addr = u64(-1);',
):
    assert needle in text, needle

cache_record = root / '.local/headless-cache'
# CI release preflight runs before the pinned native fixture is extracted.
# Always validate patch invariants; confirm exact source applicability later.
if not cache_record.is_file():
    if '--require-pinned-source' in sys.argv:
        raise SystemExit('Pinned Eden fixture unavailable; cannot verify patch applicability')
    print('Experimental patch static policy PASS (pinned source check deferred)')
    sys.exit(0)
cache=Path(cache_record.read_text().strip())
source=cache/'source'
# ACTIVE native sources already contain this patch. Reapplying it here would
# incorrectly reject a correctly patched source tree. Compare all five exact
# patched files against the original pinned baseline and patch replay instead.
subprocess.run([sys.executable, '-B', str(root/'tools/install-active-core-backports.py'),
                str(source), '--check'], check=True, timeout=60)
print('Dynarmic I-cache coherence is present in the actual staged native source: PASS')
