#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
cmake=(root/'headless/CMakeLists.txt').read_text()
main=(root/'headless/main.cpp').read_text()
perf=(root/'headless/performance.cpp').read_text()
start=cmake.index('# JIT entry/exit sampling')
end=cmake.index('write_derived(',start)
section=cmake[start:end]
assert 'if(EDEN_DEV_PROFILE)' in section
assert 'if(PS5_NATIVE)' not in section
start=cmake.index("# Keep Eden's exact mutex/condition-variable idle path")
end=cmake.index('string(REPLACE "${prefetch_old}"',start)
assert 'elseif(PS5_NATIVE)' not in cmake[start:end]
start=main.index('// Shipping path: no periodic profiler/watchdog work')
end=main.index('#endif',start)
release=main[start:end]
assert 'Performance::Snapshot()' not in release
assert 'completion->wake.wait(lock, completed);' in release
assert 'filter.ParseFilterString("*:Debug")' not in main
assert 'release logging unchanged\\n", stderr);' in main
for forbidden in ('ReleasePcSignal', 'EnableReleasePcSignal', 'release_guest_threads', 'release_guest_pcs'):
    assert forbidden not in perf, forbidden
print('Shipping PS5 hot path diagnostics stripped: PASS')
