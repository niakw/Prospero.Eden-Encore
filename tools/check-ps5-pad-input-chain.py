#!/usr/bin/env python3
"""R389 static contract for DualSense Options -> virtual Switch Plus counters.

Pure source check, NO native compilation. The host InputEngine publication
counter is NOT proof that guest HID/Npad has consumed the event.
"""
import re
from pathlib import Path

root=Path(__file__).resolve().parents[1]
header=(root/'headless/devices.h').read_text()
source=(root/'headless/pad.cpp').read_text()
mapping=(root/'headless/button_mapping.h').read_text()

assert 'published_plus_edges{0}' in header
assert 'PublishedPlusEdges() const noexcept' in header
assert 'u64 options_edges = 0, create_edges = 0;' in header
assert 'button == static_cast<int>(VirtualButton::ButtonPlus)' in source
assert 'published_plus_edges.fetch_add(1, std::memory_order_relaxed)' in source
assert 'if ((pressed & kButtonOptions) && !(last_buttons & kButtonOptions))' in source
assert 'EDEN_PAD_INPUT_CHAIN polls=%llu options_edges=%llu published_plus_edges=%llu' in source
assert 'sony_intercepted_samples=%llu' in source
assert 'engine->PublishedPlusEdges()' in source
assert 'NativeLogs::Detailed()' in source
assert 'Button::ButtonPlus' in source
assert re.search(r'kPlayStationMapping\s*=\s*\{[^}]*pad_options',mapping,re.S)
assert 'guest_hid_consumed_plus_edges' not in source
print('PASS R389: detailed-only Options-to-virtual-Plus counters; guest HID not yet observed')
