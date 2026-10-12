#!/usr/bin/env python3
"""R400 official PS5_Mesa 47e9eb61 120Hz feature detection + VRR-safe guard."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
wsi=(ROOT/'vendor/encore-active/ps5-mesa/src/vulkan/wsi/wsi_common_videoout.c').read_text()
generator=(ROOT/'tools/patch-radv-wsi.py').read_text()
assert wsi.count('out->high_frame_rate = supported > 0 && configured == 0;') == 1
assert wsi.count('            : -1;') == 1
assert 'out->high_frame_rate = configured == 0;' not in wsi
assert 'period == 0 || (period > UINT64_C(15000000) && period < UINT64_C(18500000))' in wsi
assert '119.88 Hz not offered on present output' in wsi
assert '119.88 Hz accepted, but a vblank wait failed' in wsi
assert 'out->high_frame_rate = supported > 0 && configured == 0;' in generator
assert 'period == 0 || (period > UINT64_C(15000000) && period < UINT64_C(18500000))' in generator
# Truth-table all relevant outputs. In particular unsupported=0/configured=0
# must NEVER offer 119.88Hz, and VRR 48Hz vblank must not be misread as 60Hz.
def high(supported,configured,period):
    accepted = supported > 0 and configured == 0
    return accepted and period != 0 and not (15000000 < period < 18500000)
assert not high(0,0,8338000)
assert not high(-1,0,8338000)
assert not high(1,-1,8338000)
assert not high(1,0,0)
assert not high(1,0,16680000)
assert high(1,0,8338000)
assert high(1,0,20800000)  # transient 48Hz VRR interval
print('R400 PASS source-based VideoOut supported/configured + failed wait + VRR guard')
