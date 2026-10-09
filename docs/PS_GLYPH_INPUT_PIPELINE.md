# PS5 input normalization vs game-owned PlayStation glyph artwork

## Sys-con architectural reference (o0Zz)

Reference: https://github.com/o0Zz/sys-con and https://github.com/o0Zz/sys-con/blob/master/doc/ARCHITECTURE.md

sys-con is a Nintendo Switch USB gamepad sysmodule with HID/XID support, per-device VID/PID mapping profiles, deadzone adjustments and optional HID MITM/virtual pads. The source is GPL-3.0; it is NOT a PS5 module and Eden Encore has not copied or embedded its code.

It separates two index spaces: physical pin/button identifier (RawInputData) and normalized Nintendo Switch GamepadButton (NormalizedButtonData). ControllerConfig::buttonsPin maps the former to the latter. This does not affect game-owned textures.

Eden's corresponding pipeline is:

physical DualSense face button -> Eden::ResolveSessionButtonMapping -> guest Nintendo HID A/B/X/Y -> Switch game's action -> independent game-owned UI graphic -> optional qualified replacement atlas.

## Correct two-space mapping for BOTW

For the default fixed PlayStation profile, the Nintendo guest action A is on PS Cross (physical bottom), B is on Circle (physical right), X is on Square (physical left) and Y is on Triangle (physical top).

For the alternative Switch-physical profile, guest A is on Circle and B on Cross.

An action-specific world prompt showing Switch A therefore needs a Cross image when the PlayStation profile is active. An illustrated controller needs its spatial right-side face button to be Circle, and its bottom button to be Cross, regardless of how the Switch actions are assigned. The same sprite may not serve both contexts without verifying its usage.

The Switch-specific BOTW DS4 UI v2 Western Layout at https://gamebanana.com/mods/659253 provides a public technical discovery lead. Its documentation is NOT exact Switch atlas XYWH evidence or redistribution permission for third-party game assets. We must not copy its assets or assert compatibility from a public description.

## Eden implementation

- tools/ps-glyph-reconstruct.py index: groups public Switch and Wii U/PC/PSP references across games. All entries are unqualified leads, not published compatibility.
- tools/ps-glyph-cross-platform-image.py: demands matching original decoded image pixels to transfer any other-platform candidate rectangle.
- tools/ps-glyph-reconstruct.py spec: requires a verified Switch ROMFS original, title/update identity, source SHA-256, scene, measured safe pixel rectangles, and explicit guest_action or controller_position meaning.
- tools/ps-glyph-atlas.py render and tools/ps-glyph-pack.py verify/install: generate new artist-owned PS artwork and stage a local LayeredFS pack with original-resource SHA checks.
- The native selector retains original Nintendo prompts if the per-title version, pack or evidence is missing. No BOTW pack is currently qualified.

sys-con cannot modify Nintendo in-game artwork; its optional network input tester is Switch-specific and its unauthenticated UDP service should not be copied into PS5. It also does not provide evidence for PS5 CPU threading, JIT, GPU timing, or VRAM capacity.

Host synthetic fixtures passed in GitHub Actions run 38000650164. Those fixtures do NOT verify BOTW game-owned assets or PS5 screenshots.
