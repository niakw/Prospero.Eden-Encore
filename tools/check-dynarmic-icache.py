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
source=cache/'source/src/core/arm/dynarmic'
with tempfile.TemporaryDirectory(prefix='encore-icache-') as tmp:
    tmp=Path(tmp)
    dst=tmp/'src/core/arm/dynarmic'
    dst.mkdir(parents=True)
    for name in ('arm_dynarmic_64.cpp','arm_dynarmic_32.cpp'):
        shutil.copy2(source/name,dst/name)
    subprocess.run(['patch','--batch','--forward','-p1','-d',str(tmp)],
                   input=patch.read_text(),text=True,check=True,
                   stdout=subprocess.DEVNULL)
    a64=(dst/'arm_dynarmic_64.cpp').read_text()
    a32=(dst/'arm_dynarmic_32.cpp').read_text()
    assert 'Core::InvalidateInstructionCacheRange(m_process, cache_line_start, ICACHE_LINE_SIZE);' in a64
    section=a64[a64.index('InvalidateAllToPoU:'):a64.index('default:',a64.index('InvalidateAllToPoU:'))]
    assert 'InvalidateAllToPoUInnerSharable' in section and 'm_parent.ClearInstructionCache();' in section
    for src,name in ((a64,'64'),(a32,'32')):
        marker=f'void ArmDynarmic{name}::InvalidateCacheRange'
        block=src[src.index(marker):src.index('}',src.index(marker))+1]
        assert 'm_cb->last_code_addr = u64(-1);' in block
print('Dynarmic cross-core I-cache coherence backport applies to pinned Eden: PASS')
