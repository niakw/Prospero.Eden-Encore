# Launcher themes

Eden Encore ships with two optional launcher layouts. **Encore** remains the
default on a fresh installation and on older settings files.

| Theme | Interface |
| --- | --- |
| **Encore** (default) | Tropical-neon TV launcher, detailed portrait library and original hero |
| **Switch** | Light HOME with square game icons, All Software grid, system-style settings, light dialogs and utilities |

Use **Settings > Appearance** to change the selection. The choice is saved
immediately to `config/prosperoeden.json` as `appearance.theme`:
`"encore"` or `"switch"`. An unknown or absent value safely selects Encore.
It changes presentation **only**, not installed games, game settings, guest
controller mapping, or firmware configuration.

The alternate layout references the open-source
[kasobos67/SwitchPS5](https://github.com/kasobos67/SwitchPS5) (GPL-3.0-or-later)
and its Nintendo Switch-inspired interaction patterns. Original vector
placeholders, system buttons and gradients are authored in this fork.
**No firmware-extracted art, Nintendo fonts, sound samples or other
proprietary console files were copied** from that repository.

The Switch appearance is a compatible interpretation, **not a pixel-perfect
reproduction** of the console OS. Some shared game-specific tools and dialogs
still use their Encore implementation where the underlying behavior must be
preserved. These should be brought into the alternate presentation without
copying extracted firmware resources.

Host previews: `PE_PREVIEW_SWITCH_THEME=1 bash tools/launcher/preview.sh ...`.
This exercises HOME, All Software, System Settings, Appearance, storage and
language using the actual C++ drawing backend. It does not prove PS5 firmware
compatibility or availability of the profile avatar cache.
