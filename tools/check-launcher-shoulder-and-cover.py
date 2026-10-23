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
for attr in ("game.hero","case_media::BackScenes(hero, game.cover, game.screenshots)",
             "game.description", "text_block(c, desc,", "const Rect footer"):
    assert attr in back, attr
assert '"SWITCH"' in front
# A square app icon cannot be stretched across an entire tall retail sleeve.
contain = method(library, "void case_art_contain(", "void flat_front_fallback(")
for token in ("const float aspect", "fitted.h = panel.w / aspect;",
              "fitted.w = panel.h * aspect;", "c.list.image(art.texture, fitted"):
    assert token in contain, token
# Front artwork must cover the whole paper; a fixed square label sits
# exactly on the top-left corner and is never drawn on an original scan.
for token in ("const bool scenic", "cover_crop(c, painting, r, 0.0f, 0.0f);",
              "case_art_contain(c, game.cover,", "const Rect logo{r.x, r.y, logo_w,",
              "c.textures.switch_logo() != 0"):
    assert token in front, token
# Distinct back scenes come from the cached game, while the reference
# bottom section is immutable and cannot be overwritten by dynamic media.
for token in ("const std::string* first = shots[0];",
              "const std::string* second = shots[1];",
              "const Rect left{", "const Rect top_right{", "const Rect panorama{",
              "constexpr float kFixedFooter = 0.41f;",
              "c.textures.switch_rear_footer() != 0",
              "if (path == game.cover) case_art_contain(c, path, area);"):
    assert token in back, token
assert "ENCORE / GAME INFORMATION" in back
assert "const std::string& credit = !game.publisher.empty()" in back
# A real face remains untouched while asynchronous texture decoding runs;
# a different missing face can still receive a reconstructed paper insert.
assert "if (!scan.empty()) {" in render
assert "if (artwork.texture != 0)" in render
assert "c.list.gradient_rect(paper, 0.0f," in render
assert "if (rear)\\n                flat_back_fallback(c, game, paper);" not in render
# No invented regulatory content in the procedural fallback. The user-
# supplied reference footer is drawn as a static asset only, separately.
footer = back.split("if (c.textures.switch_rear_footer() != 0)",1)[1]
for word in ("PEGI", "HAC-P", "ESRB", "MADE IN JAPAN"):
    assert word not in footer, word
print("ENCORE_UI_SHOULDER_AND_COMPOSED_SLEEVES_PASS")
