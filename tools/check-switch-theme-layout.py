#!/usr/bin/env python3
"""Source geometry contract for original-drawn Switch-style console shell."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
src=(root/"headless/prosperoeden/pe/ui/switch_theme.cpp").read_text()
for line in (
    "kSwitchHomeTileSize = 384.0f;",
    "kSwitchHomeTilePitch = 405.0f;",
    "kSwitchHomeTileX = 160.5f;",
    "kSwitchHomeTileY = 291.0f;",
    "kSwitchLibraryTileSize = 261.0f;",
    "kSwitchLibraryTilePitch = 276.0f;",
    "kSwitchLibraryTileX = 138.0f;",
    "kSwitchLibraryTileY = 278.0f;",
    "constexpr int kHomeShortcuts = 6;",
    "555.0f+162.0f*float(i),y=816.0f;",
    "void Launcher::draw_switch_header",
    "constexpr float px=136.5f,py=98.0f;",
    "void Launcher::draw_switch_footer",
    "void Launcher::draw_switch_library",
    "void Launcher::draw_switch_settings",
    "void Launcher::draw_switch_dialog",
):
    assert line in src, f"reference console geometry missing: {line}"
assert "switch_game_tile(c,item.cover,item.title,box,i)" in src
assert "const Cover avatar=profile_avatar_path_.empty()?Cover{}:" in src
assert "case 5: { // Power glyph" in src
assert "std::clamp(current+delta,kHomeShortcutFirst," in src
assert "switch_home_last_tile_=current;" in src
assert "switch_home_focus_=last==kHomeAllSoftware||last>=count?" in src
assert "press_library(key);" in src, "Switch game launch must respect core validation"
assert "void Launcher::draw_switch_confirmation" in src
assert "switch_value(services_.resolution_labels(),prefs_.resolution)" in src
assert "switch_value(services_.filter_labels(),prefs_.filter)" in src
assert "switch_value(services_.anti_aliasing_labels(),prefs_.anti_aliasing)" in src
assert "switch_value(services_.performance_profile_labels(),prefs_.performance_profile)" in src
preview=(root/"headless/prosperoeden/host/preview_main.cpp").read_text()
assert "06-switch-exit-confirm" in preview
assert "Key::right, Key::right, Key::right, Key::right," in preview
assert 'if(!message_.empty())' in src, "game errors must remain visible"
assert "stock_assets.hpp" not in src, "firmware-extracted UI atlas must not be imported"
print("SWITCH_UI_GEOMETRY_AND_ASSET_ISOLATION: PASS")
