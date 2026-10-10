#!/usr/bin/env python3
"""Pure source/UI contract: static per-game PS5 map and launcher polishing.

Prepared for the next USER-AUTHORIZED CI run; do not use its mere presence as
proof of PS5 hardware/UI testing.
"""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
home = (root / "headless/prosperoeden/pe/ui/home.cpp").read_text()
library = (root / "headless/prosperoeden/pe/ui/library.cpp").read_text()
mapping = (root / "headless/prosperoeden/pe/ui/mapping.cpp").read_text()
launch = (root / "headless/main.cpp").read_text()
inputs = (root / "headless/pad.cpp").read_text()

# A title can select Global, PlayStation, Switch using arrows, independently
# of the global setting. Cross still enters the advanced per-button editor.
assert "if (option_ == row_controls)" in library
assert "if (key == Key::cross) {" in library
assert "open_mapping(true);" in library
assert "constexpr std::array profiles{-1, 0, 1};" in library
assert "next.controller_layout = profiles[" in library
assert "next.own_mapping = false;" in library
assert "services_.set_game_settings(game.title_id, next)" in library
assert "game_settings_.controller_layout >= 0 ?" in library
assert "Eden::BaseMappingForLayout(game_settings_.controller_layout)" in library
assert "Eden::ResolveSessionButtonMapping" in mapping
assert "Eden::ResolveSessionButtonMapping" in launch
assert "SetAdaptivePlayStation(" not in inputs
assert "adaptive_playstation" not in inputs
assert "mapping_context" not in inputs

# Triangle game settings: ten editable rows before Mods. Seven hints
# previously indexed through row_controls (9) caused an OOB read.
import re
rows = library.split("enum GameRow : int", 1)[1].split("};", 1)[0]
editable = re.findall(r"^\\s*(row_\\w+),", rows, flags=re.MULTILINE)
assert len(editable) == 10 and editable[-1] == "row_controls"
help_text = library.split("kGameAbout = {{", 1)[1].split("}};", 1)[0]
assert len(re.findall(r'TR\\("', help_text)) == len(editable)
assert "kGameAbout.size() == static_cast<std::size_t>(row_mods)" in library
assert "option_ < static_cast<int>(kGameAbout.size())" in library
assert "library_.selected < 0 ||" in library
assert "static_cast<std::size_t>(library_.selected) >= games_.size()" in library
# Driver traces are opt-in; disabling UI detailed logging also silences RADV.
assert "performance_run || !launch_preferences.detailed_logging" in launch
assert 'setenv("PS5VK_QUIET_LOG", quiet_driver ? "1" : "0", 1);' in launch

# The Library title scrim now actually extends to the bottom of the cover
# interior, rather than leaving a four-percent bright strip under the text.
assert "tile_art.y + tile_art.h * 0.43f" in library
assert "tile_art.w, tile_art.h * 0.57f" in library
assert "card.h * 0.53f" not in library

# The user-supplied mask is 96% transparent, and the actual visible
# strokes were 33%-alpha on dark panels. Whiten nontransparent samples
# before tinting, otherwise the "white" icon still renders black on PS5.
mask = (root / "headless/prosperoeden/pe/ui/dualsense_mask_asset.hpp").read_text()
textures = (root / "headless/prosperoeden/pe/ui/textures.cpp").read_text()
assert 'color[0] = color[1] = color[2] = 255;' in textures
assert 'color[3] = level == 0 ? 0 : (level == 1 ? 240 : 255);' in textures
assert 'kDualSenseAlphaRuns' in mask
assert 'controller_ = create(pad_image);' in textures
assert 'dualsense_icon(c, r, ink, 0.40f + 0.60f * lit);' in (root / "headless/prosperoeden/pe/ui/widgets.cpp").read_text()
# Controller icon is licensed DualSense image; keep the settings cog unchanged.
assert "dualsense_icon(c, {left - 10.0f, cy - 15.0f, 44.0f, 30.0f}, theme::kTitle, 1.0f);" in home
assert "theme::kTitle, 1.0f);" in home
assert "players_chip.x + 8.0f, players_chip.y + 3.0f, 45.0f, 30.0f" in home
assert "controller_icon(c, {card.x + card.w - 74.0f" not in library
assert "42.0f, 29.0f}, theme::kTitle, 1.0f);" in library
print("SOURCE CHECK ONLY: Triangle bounds + per-game controls + quiet Vulkan driver + white DualSense")
print("REQUIRES USER RUN AUTHORIZATION: compiled PS5 UI rendering and controller effects NOT VERIFIED")
