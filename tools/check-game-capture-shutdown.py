#!/usr/bin/env python3
"""Keep production PS5 presentation free of diagnostic GPU readbacks."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = (root / 'headless/main.cpp').read_text()
graphics = (root / 'headless/graphics.cpp').read_text()
cache = Path((root / '.local/headless-cache').read_text().strip())
renderer = (cache / 'native-local/headless/renderer_opengl.cpp').read_text()

assert 'm_current_frame != 29' not in renderer
assert 'EDEN_GAME_CAPTURE_TARGET' not in renderer
assert 'EDEN_GAME_PRESENT_FRAME' not in renderer
draw_hud = graphics.split('    void DrawHud(', 1)[1].split('    unsigned presented_frames', 1)[0]
assert 'glReadPixels' not in draw_hud
assert 'game-hud.ppm' not in graphics and 'loading.ppm' not in graphics

capture = main.index('window.CaptureNextFrame(')
assert main.rfind('#ifndef PS5_NATIVE', 0, capture) > main.rfind('#endif', 0, capture)
presentation = main.index('window.CheckPresentation(')
assert main.rfind('#ifndef PS5_NATIVE', 0, presentation) > main.rfind('#endif', 0, presentation)
assert 'completion->wake.wait(lock, completed);' in main
assert 'completion->return_to_menu' in main
# Development capture/profiling stays isolated from the shipping game wait.
development_wait = main.split('#ifdef EDEN_DEV_PROFILE\n                        for ', 1)[1].split('#elif defined(EDEN_DEV_ROM_ID)', 1)[0]
dev_rom_wait = main.split('#elif defined(EDEN_DEV_ROM_ID)', 1)[1].split('#else\n                        // Shipping path:', 1)[0]
shipping_wait = main.split('#else\n                        // Shipping path:', 1)[1].split('#endif\n                    } else', 1)[0]
assert development_wait.count('Performance::Snapshot()') == 1
assert main.count('Performance::Snapshot()') == 1
assert development_wait.count('window.CaptureNextFrame(') == 2
assert dev_rom_wait.count('window.CaptureNextFrame(') == 1
assert shipping_wait.count('window.CaptureNextFrame(') == 0
assert main.count('window.CaptureNextFrame(') == 4
assert 'completion->wake.wait(lock, completed);' in development_wait
assert 'completion->wake.wait(lock, completed);' in shipping_wait
assert 'Performance::Snapshot()' not in shipping_wait
assert 'wait_for(' not in shipping_wait
print('Native gameplay has no automatic GPU readback or frame capture')
