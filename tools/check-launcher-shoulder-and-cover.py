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
assert render.index("if (!scan.empty() && !artwork.missing)") < render.index("flat_composed_ink(c, game, paper, rear)")
front = method(library, "void flat_front_fallback(", "void flat_back_fallback(")
back = method(library, "void flat_back_fallback(", "// Static sleeve used")
for attr in ("game.hero","game.cover","game.screenshots","game.name","reconstructed_cover"):
    assert attr in front, attr
for attr in ("game.hero","case_media::BackScenes(",
             "game.description", "text_block(c, desc,", "const Rect footer"):
    assert attr in back, attr
assert '"SWITCH"' in front
# Front uses a full-width cover UV crop, never stretched independently in X/Y.
front_cover = method(library, "void reconstructed_cover(", "// Reconstructed paper inserts")
for token in ("uv.w = target / source;", "uv.h = source / target;",
              "c.list.image(art.texture, paper, uv,"):
    assert token in front_cover, token
assert 'if (painting) reconstructed_cover(c, *painting, r);' in front
assert "case_media::FrontPaper(" in front
assert "case_media::FrontPaper(" in back
assert 'scene(game.cover,' not in back
assert 'case_art_contain(' not in library
assert 'reconstructed_paper(c, paper);' in library
assert "constexpr float kFixedFooter = 0.41f;" in back
assert 'c.textures.switch_rear_footer() != 0' in back
assert "ENCORE / GAME INFORMATION" in back
assert "const std::string& credit = !game.publisher.empty()" in back
# A real face remains untouched while asynchronous texture decoding runs;
# a different missing face can still receive a reconstructed paper insert.
# Every Library jacket uses the same height and visual composition as
# the launcher's paper face, regardless of a downloaded cover.
for token in ("constexpr float kCaseShellAspect = 454.0f / 730.0f;",
              "constexpr float kCaseInkWidth = 440.0f;",
              "constexpr float kCaseInkHeight = 704.0f;",
              "void flat_composed_ink(Canvas& c, const Game& game,",
              "const float sleeve_w = sleeve_h * kCaseShellAspect;",
              "constexpr float rear_h = 247.0f;",
              "constexpr float rear_w = rear_h * kCaseShellAspect;"):
    assert token in library, token
assert "flat_composed_ink(c, game, paper, rear);" in render
assert "selected ? 1.025f : 1.0f" not in library
assert "if (!scan.empty() && !artwork.missing) {" in render
assert "if (artwork.texture != 0)" in render
assert "reconstructed_paper(c, paper);" in render
assert "if (rear)\\n                flat_back_fallback(c, game, paper);" not in render
# No invented regulatory content in the procedural fallback. The user-
# supplied reference footer is drawn as a static asset only, separately.
footer = back.split("if (c.textures.switch_rear_footer() != 0)",1)[1]
for word in ("PEGI", "HAC-P", "ESRB", "MADE IN JAPAN"):
    assert word not in footer, word
print("ENCORE_UI_SHOULDER_AND_COMPOSED_SLEEVES_PASS")
