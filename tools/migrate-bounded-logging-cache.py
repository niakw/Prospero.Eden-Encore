#!/usr/bin/env python3
"""One-time exact migration of already-applied pinned PS5 log patch in cached Eden.
No other source is rewritten. Abort on unknown source state or format.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1])
source=root/'src/common/logging.cpp'
text=source.read_text()
for expected in ('void RotatePs5() noexcept', 'first_filename += ".first.txt"',
                 'log tail rotated; storage remains bounded'):
    if expected not in text: raise SystemExit('unexpected cached Eden logging source: '+expected)
old='        if (entry.log_level >= Level::Error)\n            file->Flush();\n'
new='''        // Thousands of guest/device unmapped-memory errors can arrive
        // during a broken scene. Flush-on-EVERY-error serialized tens of
        // thousands of writes onto the PS5 storage, compounding stalls.
        // Keep ALL lines and immediate first-error/critical durability,
        // but amortize later Error-level syncs to every 64th event.
        if (entry.log_level >= Level::Error) {
            ++error_events;
            if (entry.log_level >= Level::Critical ||
                error_events == 1 || error_events % 64 == 0)
                file->Flush();
        }
'''
if new in text and '    std::size_t error_events = 0;' in text:
    print('Already migrated; verifying backport receipt only')
    raise SystemExit(0)
if text.count(old)!=1 or text.count('    bool rotated = false;\n')!=1:
    raise SystemExit('unknown cached logging version; refusing source-cache migration')
text=text.replace(old,new)
text=text.replace('    bool rotated = false;\n',
                  '    bool rotated = false;\n    std::size_t error_events = 0;\n')
source.write_text(text)
print('Known PS5 log-flush revision migrated without resetting other pinned dependencies')
