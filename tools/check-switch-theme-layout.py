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
assert "if(modal_==Modal::none && confirmation_==Confirmation::none && !message_.empty())" in src
assert "if(modal_==Modal::none && confirmation_==Confirmation::none && !feedback.empty())" in src
assert "void Launcher::draw_switch_confirmation" in src, "native confirmation must be themed"
assert "stock_assets.hpp" not in src, "firmware-extracted UI atlas must not be imported"
print("SWITCH_UI_GEOMETRY_AND_ASSET_ISOLATION: PASS")

assert "void Launcher::draw_switch_game(Canvas& c,float opened)" in src
assert "void Launcher::draw_switch_mods(Canvas& c,float opened)" in src
assert "void Launcher::draw_switch_mapping(Canvas& c,float opened)" in src
assert "VideoPresetForTitle(id" in src

preview=(root/"headless/prosperoeden/host/preview_main.cpp").read_text()
for filename in ("07-switch-game-options","08-switch-game-mods","09-switch-button-mapping"):
    assert filename in preview

assert '!message.empty()&&warn?' in src, "stale confirmation must not tint normal modal hint red"
assert 'text_shrink(c,tr("Back"),1230.0f' in src

# The visual mapping must use the effective mapped pad (not a fixed platform
# face glyph), and custom profiles must not be mislabeled as defaults.
assert "switch_profile_name(int layout,const ButtonMapping& mapping)" in src
assert "switch_profile_name(g.controller_layout" in src
assert "switch_physical_pad(mapped)" in src
assert "const Pad icon=switch_physical_pad(mapped);" in src
assert "draw_pad(c,icon,1035.0f" in src
assert "if(mapped>=4)" in src, "shoulder/system glyphs need a dark backing on white"
assert "settings_.wrap=false;" in src
assert "settings_.wrap=original_wrap;" in src
assert 'text_shrink(c,tr("Select"),1024.0f' in src

mapping=(root/"headless/prosperoeden/pe/ui/mapping.cpp").read_text()
assert "screen_ == Screen::home" in mapping
assert "close_modal();" in mapping
assert "10-switch-mods-installed" in preview
assert "11-switch-mod-enabled" in preview

assert "text_block(c,message.empty()?tr(fallback):message" in src
assert "418.0f,2,kShrink" in src
