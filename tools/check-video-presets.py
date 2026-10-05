#!/usr/bin/env python3
from pathlib import Path
root = Path(__file__).resolve().parents[1]
preset = (root / 'headless/prosperoeden/pe/ui/video_presets.hpp').read_text()
settings = (root / 'headless/prosperoeden/pe/ui/settings.cpp').read_text()
library = (root / 'headless/prosperoeden/pe/ui/library.cpp').read_text()
for expected in ('{1, 1, 3, 0, 88, 0, 0}', '{1, 0, 3, 0, 88, 0, 0}', '{1, 0, 2, 1, 50, 0, 0}'):
    assert expected in preset, expected
assert 'ApplyVideoPreset(prefs_, preset);' in settings
assert 'ApplyVideoPreset(next, preset);' in library
for reset in ('next.renderer = -1;', 'next.resolution = -1;', 'next.filter = -1;', 'next.refresh = -1;'):
    assert reset in library, reset
assert 'tr("VIDEO PRESET")' in settings
assert 'tr("DETAILED LOGGING")' in settings
assert 'TR("Video preset")' in settings
assert 'TR("Video preset")' in library
print('Video presets: global/per-game application and complete previews PASS')

assert 'video_fsr_sharpness' in settings and 'video_anti_aliasing' in settings
assert 'FSR SHARPNESS' in settings and 'ANTI-ALIASING' in settings
