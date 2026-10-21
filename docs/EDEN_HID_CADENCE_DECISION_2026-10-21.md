# HID polling — stable production cadence

Source: `vendor/encore-active/eden-core/src/hid_core/resource_manager.cpp` (H31).

The prior 1 ms NPad scheduler period was labeled by the source as an overclock relative to 4 ms. The selected single native shipping cadence is 4 ms (250 Hz), preserving the other HID event periods, guest samples and registered controller API.

This is a CPU/HLE scheduling trade-off: approximately 750 fewer NPad callbacks per second; **worst-case extra sample latency up to 3 ms**. Neither a measured frame-time improvement nor a fix for controller mapping/pause issues is claimed.

Oracle: `tools/check-vendored-hid-resource-source.py` compares the entire native translation unit to the pinned source with only two explicit deltas. Test: `tools/check-native-hid-cadence-host.py` compiles a source-extracted C++20 definition under ASan/UBSan and checks 250 Hz and the x4 interval ratio.

After this lot: 416/491 reviewed/handled; 13 engine files remain (previously 14); 62 launcher sources tracked separately.
