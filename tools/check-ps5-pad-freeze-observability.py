#!/usr/bin/env python3
"""R332: actual native DualSense edge counter replay and quiet logging contracts."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'headless/pad.cpp').read_text()
header = (root / 'headless/devices.h').read_text()
main = (root / 'headless/main.cpp').read_text()
assert '#include "pad_diagnostics.h"' in header
assert '#include "log_pipe.h"' in source
assert 'face_edges.Observe(last_buttons, pressed, kButtonCross, kButtonCircle,' in source
assert 'kButtonSquare, kButtonTriangle);' in source
assert 'player == 0 && is_usable(raw) && NativeLogs::Detailed()' in source
assert 'if (NativeLogs::Detailed() && polls % 1250 == 0)' in source
assert source.count('EDEN_PAD_HEARTBEAT polls=') == 1
assert 'last_read=%d' in source and 'square=%llu triangle=%llu' in source
assert 'ActiveMapping()[game_x], ActiveMapping()[game_y]' in source
assert 'std::fflush(stderr)' not in source
assert 'EDEN_PAD_INPUT mode=%s' in main and 'pad->Poll();' in main
assert 'pad_square, pad_triangle' in (root / 'headless/button_mapping.h').read_text()
# A new title must not inherit the previous renderer's stall timestamp.
perf_source = (root / 'headless/performance.cpp').read_text()
perf_header = (root / 'headless/performance.h').read_text()
assert 'void ResetGpuReportForTitle() noexcept;' in perf_header
assert 'void ResetGpuReportForTitle() noexcept {' in perf_source
assert 'latest_gpu_report_ns.store(0, std::memory_order_release);' in perf_source
assert 'Eden::Performance::ResetGpuReportForTitle();' in main

unit = r'''
#include "pad_diagnostics.h"
#include <cassert>
#include <cstdio>
int main() {
    Eden::PadEdgeDiagnostics edges{};
    constexpr unsigned cross=1, circle=2, square=4, triangle=8;
    edges.Observe(0, 4, cross, circle, square, triangle);
    assert(edges.changes==1 && edges.square==1 && edges.triangle==0);
    edges.Observe(4, 4, cross, circle, square, triangle);
    assert(edges.changes==1 && edges.square==1);  // held does not recount
    edges.Observe(4, 12, cross, circle, square, triangle);
    assert(edges.changes==2 && edges.square==1 && edges.triangle==1);
    edges.Observe(12, 0, cross, circle, square, triangle);
    assert(edges.changes==3 && edges.square==1 && edges.triangle==1);
    edges.Observe(0, 3, cross, circle, square, triangle);
    assert(edges.changes==4 && edges.cross==1 && edges.circle==1);
    edges.Observe(3, 0, cross, circle, square, triangle);
    edges.Observe(0, 4, cross, circle, square, triangle);
    assert(edges.square==2 && edges.triangle==1 && edges.cross==1 && edges.circle==1);
    std::puts("R332 PASS: physical face rising edges, held/release, independent X/Y accounting");
}
'''
with tempfile.TemporaryDirectory(prefix='eden-r332-pad-') as tmp:
    path = Path(tmp)
    (path / 'test.cpp').write_text(unit)
    env = os.environ.copy()
    if sys.platform == 'darwin' and not env.get('SDKROOT'):
        sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk')
        if sdk.is_dir(): env['SDKROOT'] = str(sdk)
    subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-O2',
                    '-I', str(root/'headless'), str(path/'test.cpp'), '-o', str(path/'test')],
                   check=True, env=env, timeout=30)
    result = subprocess.run([str(path/'test')], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    print(result.stdout.strip())
print('R332 PASS: detailed-only once/1250-polls heartbeat, no per-sample persistent I/O')
