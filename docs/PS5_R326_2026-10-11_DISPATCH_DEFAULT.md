# R326 — Restore 8-draw GPU worker handoff on PS5 development builds

Branch `dev/ps5-sparse-jit`. This is a scheduling-policy correction, **not** a declared FC27 FPS or texture fix.

The pinned Eden Vulkan draw producer uses an 8-draw dispatch handoff (`dispatch_mask=7`). R309 had increased **development only** to 64 (`dispatch_mask=63`), borrowed from PS5 fork experiments on another game. There was no FC27 proof this reduces frame latency. It can let graphics commands accumulate longer before the worker handles them, even with R309's independent **512-draw hard flush ceiling**. FC27 detailed logs at 1440p found GPU-producer queue-full time was substantial during five poor 5-second windows (22.6 average FPS and 122 late frames), versus 29.5 average FPS and 63 late frames across 63 other windows; this is *association*, not evidence that the 64-draw cadence caused the stalls.

In dev `main.cpp`, the per-title default now resets `dispatch_mask=7` instead of 63; shipping already used 7. Keep the `dispatch_draws=64` per-title optional override to compare with the earlier experiment. The exact source-tested `FlushWork` still applies the hard 512-draw flush before considering dispatch. No Vulkan barriers, guest cache locks, descriptor fences, frame skipping, shaders, texture quality or GPU queue capacity are changed.

Tests: `tools/check-ps5-vulkan-dispatch-ceiling.py` compiles and runs the exact C++ dispatch algorithm at all cadences 8,16,32,64,128,256,512; validates both dev and shipping defaults and explicit override. `tools/check-performance-policy.py` checks title resets. Native CI and later one PS5 gameplay A/B are required to demonstrate an actual performance difference. Do not ask the user for a new run until other outstanding corrections are consolidated.
