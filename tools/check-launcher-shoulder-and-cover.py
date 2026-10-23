#!/usr/bin/env python3
"""Check user-facing shoulder navigation and composed case fallback contract.

These are source ownership checks; host OpenGL screenshots validate the
actual pixels separately. No generated image is shipped as retail art.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def source(path):
    return (ROOT / path).read_text()
def method(text, start, stop):
    assert text.count(start) == 1, start
    assert text.count(stop) >= 1, stop
    return text.split(start, 1)[1].split(stop, 1)[0]
settings = source("headless/prosperoeden/pe/ui/settings.cpp")
library = source("headless/prosperoeden/pe/ui/library.cpp")
switch = source("headless/prosperoeden/pe/ui/switch_theme.cpp")
mapping = source("headless/prosperoeden/pe/ui/mapping.cpp")
general = method(settings, "void Launcher::press_settings(Key key)", "void Launcher::draw_settings(")
dialog = method(settings, "void Launcher::press_dialog(Key key)", "void Launcher::draw_dialog(")
game = method(library, "void Launcher::press_game(Key key)", "void Launcher::draw_game(")
mods = method(library, "void Launcher::press_mods(Key key)", "void Launcher::draw_mods(")
switch_keys = method(switch, "void Launcher::press_switch_settings(Key key)", "} // namespace pe::ui")
mapping_keys = method(mapping, "void Launcher::press_mapping(Key key)", "void Launcher::draw_mapping(")
for label, body in (("settings",general),("game",game),("mods",mods),
                    ("switch",switch_keys),("mapping",mapping_keys)):
    assert "Key::l1" in body and "Key::r1" in body, label
for label, body in (("dialog",dialog),("mapping",mapping_keys),
                    ("game",game),("mods",mods)):
    assert "key == Key::r1 ? 1 : -1" in body, label
assert "const bool activate = key == Key::cross;" in dialog
assert "const bool adjust = key == Key::left || key == Key::right;" in dialog
assert "if (!adjust && !activate)" in dialog
assert "const int step = key == Key::left ? -1 : 1;" in mapping_keys
assert "settings_.move(delta)" in general
assert "key==Key::r1?1:-1" in switch_keys
# True scanned faces must take precedence over any composited fallback.
render = method(library, "void flat_retail_sleeve(", "// ONE physical shell: narrow top/bottom")
assert 'const std::string& scan = rear ? game.box_back : game.box_front;' in render
assert render.index("if (!scan.empty())") < render.index("flat_back_fallback(c, game, paper)")
front = method(library, "void flat_front_fallback(", "void flat_back_fallback(")
back = method(library, "void flat_back_fallback(", "// Static sleeve used")
for attr in ("game.hero","game.cover","game.screenshots","game.name","cover_crop"):
    assert attr in front, attr
for attr in ("game.hero","game.screenshots[1]","game.description",
             "text_block(c, desc,", "const Rect footer"):
    assert attr in back, attr
assert '"SWITCH"' in front
assert "ENCORE  /  GAME INFORMATION" in back
# The fixed lower panel must not pretend that unknown regions, age labels,
# publisher addresses, barcodes or classifications are official information.
footer = back.split("const Rect footer",1)[1]
for word in ("barcode", "PEGI", "HAC-P", "ESRB", "MADE IN JAPAN"):
    assert word not in footer, word
print("ENCORE_UI_SHOULDER_AND_COMPOSED_SLEEVES_PASS")
