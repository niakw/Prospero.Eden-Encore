# Prospero.Eden Encore — Settings guide

This guide explains the settings exposed by Encore on PS5, their defaults, and practical starting profiles.

> **Important:** TV output and Game resolution are different. TV output is the final image sent to the display. Game resolution is the internal Switch render scale before scaling.

## Factory defaults

A clean Encore configuration starts with:

| Setting | Default |
| --- | --- |
| Renderer | **Vulkan** |
| Video preset | **Recommended** |
| TV output | **1080p** |
| Game resolution | **1x** |
| Upscaling filter | **Bilinear** |
| FSR sharpness | **88%** |
| Anti-aliasing | **None** |
| Refresh rate | **60 Hz** |
| FPS overlay | **Off** |
| Console mode | **Docked** |
| Stick deadzone | **8%** |
| Vibration | **100%** |
| Detailed logging | **Off** |
| Language | Seeded from the PS5 system language on first setup |

The factory values above are the fallback values of an empty configuration. Selecting a Video preset actively rewrites the video settings owned by that preset.

## Video presets

| Preset | Renderer | TV output | Game resolution | Filter | FSR sharpness | AA | Refresh |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| **Recommended** | Vulkan | 1440p | 1x | Bilinear | 88% | None | 60 Hz |
| **Smooth** | Vulkan | 1080p | 1x | Bilinear | 88% | None | 60 Hz |
| **Performance** | Vulkan | 1080p | 0.75x | AMD FSR | 50% | None | 60 Hz |

Presets are real starting points, not labels. After applying one, every advanced row can still be changed manually. Per-game settings can override the same options without changing the global configuration.

## Video settings

### Renderer

- **Vulkan — default/recommended.** Main PS5 renderer.
- **OpenGL.** Compatibility fallback for a title with a Vulkan-specific problem.

Do not use OpenGL only because a title is slow unless Vulkan is known to be the cause.

### TV output

Available: **1080p, 1440p, 2160p**.

This is the final output surface. It is not the internal game resolution. A 2160p output can look cleaner on a 4K TV, but it also increases presentation and bandwidth work.

For demanding titles, 1080p or 1440p is the safer starting point even on a 4K television.

### Game resolution

Available:

**0.25x · 0.5x · 0.75x · 1x · 1.25x · 1.5x · 2x · 3x · 4x**

- **1x — default/recommended.** Normal Switch render scale.
- **0.75x.** Useful performance compromise, especially with FSR.
- **0.5x / 0.25x.** Emergency performance or diagnostic values; visibly softer.
- **1.25x / 1.5x.** Moderate supersampling when the title has spare GPU headroom.
- **2x and above.** Expensive in GPU time and graphics memory; not normal PS5 defaults.

Docked and Handheld modes can also change what the game itself chooses to render.

### Upscaling filter

- **Bilinear — default.** Lightest general-purpose scaler.
- **AMD FSR.** Most useful when Game resolution is below the TV output.
- **Bicubic.** Sharper conventional scaling.
- **Nearest.** Mainly useful for pixel-art or diagnostics.

### FSR sharpness

Range: **0–100%**, changed in 5% steps. Factory value: **88%**.

Higher is not automatically better. Too much sharpening can make grass, hair, crowds and thin lines look noisy or grainy.

Useful starting points:

- **40–55%** for 0.75x with FSR;
- **25–45%** if the image looks grainy;
- increase only when the image is clearly too soft.

### Anti-aliasing

Available: **None, FXAA, SMAA**.

- **None — default/fastest.**
- **FXAA.** Light smoothing with a small clarity trade-off.
- **SMAA.** Better edge quality, but use it only when performance headroom remains.

### Refresh rate

- **60 Hz — default/recommended.**
- **120 Hz.** Requests a 120 Hz output mode when the display supports it.

120 Hz does not turn a 30 FPS game into a 120 FPS game.

### FPS overlay

**Off by default.** Useful while tuning or diagnosing a title.

## Console mode

- **Docked — default.** Usually asks the game for its higher graphics targets.
- **Handheld.** Can reduce the game's own workload and is worth testing on demanding titles.

This is a game-side mode change, not merely a TV-output setting.

## Per-game video settings

Library → Game settings can override the global configuration for one title:

- Renderer
- Video preset
- TV output
- Game resolution
- Upscaling filter
- FSR sharpness
- Anti-aliasing
- Refresh rate
- Console mode

A per-game value of **Default** means “follow the global setting”. Resetting the game overrides returns those rows to the global configuration.

## Controls

Encore exposes full DualSense button mapping globally and per game.

Settings → Controls → Button mapping can assign the emulated A/B/X/Y, L/R/ZL/ZR, Plus/Minus and stick-click actions to DualSense buttons. A title can use its own mapping without changing the global one.

Defaults:

| Setting | Default |
| --- | --- |
| Stick deadzone | **8%** |
| Vibration | **On** |
| Vibration strength | **100%** |

If a game's own rebinding menu does not recognize the expected PS5 layout, adjust Encore's mapping first: the game receives emulated controller actions, not native DualSense labels.

## Language

Settings → Language is shared by Encore and the games.

On first setup, Encore seeds the preference from the PS5 system language. Changing it later changes both the launcher catalog and the language/region value presented to games. A game can still ignore the choice when that language is not included.

## Audio

- Game volume: **100%**
- Mute: **Off**
- Launcher/menu volume: **70%**

## Accessibility

Launcher-only options:

- Larger text
- High contrast
- Reduce motion

All are **Off by default**.

## Diagnostics

Detailed logging is **Off by default**. Enable it while reproducing a problem, then disable it for normal use.

Logs are stored under the Encore storage root, normally /data/prosperoeden/logs/.

## Practical profiles

These are starting points, not compatibility guarantees.

### 4K TV — balanced

| Setting | Value |
| --- | --- |
| Renderer | Vulkan |
| TV output | **1440p** |
| Game resolution | **1x** |
| Filter | Bilinear |
| Anti-aliasing | None |
| Refresh | 60 Hz |
| Console mode | Docked |

A modern 4K TV can upscale 1440p well while Encore keeps more GPU and presentation headroom.

### 4K TV — image quality

Use only after the title is already stable.

| Setting | Value |
| --- | --- |
| Renderer | Vulkan |
| TV output | **2160p** |
| Game resolution | **1x to 1.25x** |
| Filter | Bilinear or Bicubic |
| Anti-aliasing | None first, then SMAA if headroom remains |
| Refresh | 60 Hz |

Increase one setting at a time. If frame pacing worsens, return TV output to 1440p first.

### 4K TV — demanding game / unstable frame pacing

A useful starting point for a heavy modern title:

| Setting | Value |
| --- | --- |
| Renderer | Vulkan |
| TV output | **1080p** |
| Game resolution | **0.75x** |
| Filter | **AMD FSR** |
| FSR sharpness | **40–50%** |
| Anti-aliasing | None |
| Refresh | 60 Hz |
| Console mode | Docked; try Handheld if still too heavy |

Once stable, try 1x before raising TV output.

### 1080p TV

| Setting | Value |
| --- | --- |
| TV output | **1080p** |
| Game resolution | **1x** |
| Filter | Bilinear |
| Anti-aliasing | None |
| Refresh | 60 Hz |

There is normally little benefit in forcing a 2160p Encore output on a 1080p display.

### Troubleshooting / compatibility

When a game crashes, freezes or renders incorrectly:

1. Use **Safe Launch** once.
2. Keep **60 Hz, 1080p, 1x, Bilinear, AA None**.
3. If the issue is graphical, test OpenGL.
4. If it is performance-related, return to Vulkan and try 0.75x + FSR.
5. Change one major setting at a time and compare logs/FPS.

Safe Launch is temporary and does not overwrite saved global or per-game settings.

## Compared with Eden desktop/Windows

Encore now exposes most of the settings that are useful for normal PS5 tuning, but it intentionally does **not** mirror every Eden desktop debug/advanced switch.

Still internal or not exposed include examples such as:

- anisotropic-filter overrides;
- aspect-ratio overrides;
- advanced GPU-accuracy toggles;
- ASTC decode/recompression modes;
- low-level VSync/frame-pacing controls;
- VRAM/memory-layout modes;
- shader-backend and shader-cache internals;
- advanced CPU timing/accuracy controls;
- platform-specific options that do not make sense on fixed PS5 hardware.

The goal is **complete practical PS5 tuning**, not a one-for-one copy of every Windows engineering switch. Additional Eden controls should be exposed only when they have a real PS5 use case and a safe default.
