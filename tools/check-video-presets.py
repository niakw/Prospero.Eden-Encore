#!/usr/bin/env python3
from pathlib import Path
root = Path(__file__).resolve().parents[1]
preset = (root / 'headless/prosperoeden/pe/ui/video_presets.hpp').read_text()
settings = (root / 'headless/prosperoeden/pe/ui/settings.cpp').read_text()
library = (root / 'headless/prosperoeden/pe/ui/library.cpp').read_text()
for expected in ('{1, 0, 2, 0, 0}', '{1, 0, 1, 1, 0}', '{1, 0, 0, 0, 0}'):
    assert expected in preset, expected
assert 'ApplyVideoPreset(prefs_, preset);' in settings
assert 'ApplyVideoPreset(next, preset);' in library
assert 'tr("VIDEO PRESET")' in settings
assert 'tr("DETAILED LOGGING")' in settings
assert 'TR("Video preset")' in settings
assert 'TR("Video preset")' in library
print('Video presets: global/per-game application and complete previews PASS')
