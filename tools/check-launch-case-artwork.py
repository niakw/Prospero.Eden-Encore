#!/usr/bin/env python3
"""Offline launch case-artwork wiring contract (host-only, no network)."""
from pathlib import Path
import math

root = Path(__file__).resolve().parents[1]
service = (root / "headless/prosperoeden/pe/ui/services.hpp").read_text()
native = (root / "headless/prosperoeden/eden_services.cpp").read_text()
header = (root / "headless/prosperoeden/pe/ui/launcher.hpp").read_text()
launcher = (root / "headless/prosperoeden/pe/ui/launcher.cpp").read_text()
theme = (root / "headless/prosperoeden/pe/ui/theme.hpp").read_text()

assert "struct BoxArt" in service
assert "virtual BoxArt box_art(std::uint64_t)" in service
assert "pe::ui::BoxArt EdenServices::box_art(std::uint64_t title_id)" in native
native_resolver = native.split("pe::ui::BoxArt EdenServices::box_art(", 1)[1].split(
    "std::string EdenServices::game_path(", 1
)[0]
for fragment in (
    'Eden::CoversDir() + "/box-"',
    'artwork.front = find_face("front");',
    'artwork.back = find_face("back");',
    'artwork.spine = find_face("spine");',
    '"png", "jpg", "jpeg", "tga"',
    "stbi_info(path.c_str()",
    "info.st_size > (16LL << 20)",
):
    assert fragment in native_resolver, fragment
assert "MakeRequest" not in native_resolver

launch_setup = launcher.split("void Launcher::launch(", 1)[1].split(
    "void Launcher::press(", 1
)[0]
assert "services_.box_art(title_id)" in launch_setup
assert "launch_box_front_ = case_art.front;" in launch_setup
assert "launch_box_back_ = case_art.back;" in launch_setup
assert "launch_box_spine_ = case_art.spine;" in launch_setup
assert "launch_description_" in launch_setup
assert "launch_screenshots_" in launch_setup
assert "textures_.cover(launch_box_front_, 760.0f)" in launch_setup
assert "textures_.cover(launch_box_back_, 760.0f)" in launch_setup
assert "textures_.cover(launch_box_spine_, 760.0f)" in launch_setup
assert "Common::Net" not in launch_setup

draw = launcher.split("void Launcher::draw_launch(", 1)[1].split(
    "void Launcher::draw(", 1
)[0]
for fragment in (
    "const std::string& scan = back ? launch_box_back_ : launch_box_front_;",
    "const Cover artwork = c.textures.cover(",
    "c.list.case_face(artwork.texture, face, angle, back, kWhite, paper_uv,",
    "c.list.case_spine(side_strip, angle, case_depth - 6.0f,",
    "c.list.case_plastic(physical, angle, back,",
    "launch_screenshots_.front()",
    "const Rect physical{374.0f, 126.0f, 454.0f, 730.0f};",
    "c.textures.brand()",
    "motion() > 0.0f",
    'tr("STARTING")',
):
    assert fragment in draw, fragment
assert "MakeRequest" not in draw
assert "progress%" not in draw
assert "std::vector<std::string> launch_screenshots_;" in header
assert "constexpr float kCaseBackHold = 4.50f;" in theme
assert "constexpr float kCaseTurnSeconds = 0.72f;" in theme
assert "constexpr float kCaseBackHold = 4.50f;" in theme
assert "s.wait(0.51f); // instantaneous ~90-degree spine glimpse, no dwell" in (
    root / "headless/prosperoeden/host/preview_main.cpp").read_text()
assert "constexpr float kLaunchSeconds = kCaseFrontHold" in theme

# Quarter turn becomes an edge; the full back is visible half a turn later.
assert math.cos(0.52) > 0 and math.sin(0.52) > 0
assert math.cos(math.pi + 0.44) < -0.90
assert math.sin(math.pi + 0.44) < 0
assert math.cos(2.0 * math.pi + 0.52) > 0
library = (root / "headless/prosperoeden/pe/ui/library.cpp").read_text()
assert "game.box_front" in library and "game.box_back" in library
assert "library_back_zoom_" in library and "library_back_focused_" in library
assert "library_format(game->format)" in library
assert "library_size(game->size)" in library
assert "library_date(game->release_date" in library
assert "library_genres(game->categories)" in library
assert 'tr("Down: view back cover")' in library
assert 'tr("Enlarge cover")' in library
assert "flat_retail_sleeve(c, *game, art, true, 0.60f);" in library
assert "flat_retail_sleeve(c, *game, enlarged, true, 0.92f);" in library
assert "flat_retail_sleeve(c, game, sleeve, false, 0.24f);" in library
assert "const Rect paper{shell.x + side, shell.y + top," in library
assert "flat_back_fallback(c, game, paper);" in library
assert "flat_front_fallback(c, game, paper);" in library
assert "shell.y + shell.h - top" in library
assert "s.press({Key::r1, Key::r1});" in (
    root / "headless/prosperoeden/host/preview_main.cpp").read_text()
assert "PE_PREVIEW_LIBRARY_ONLY" in (
    root / "headless/prosperoeden/host/preview_main.cpp").read_text()
assert "case_face(artwork.texture, face, angle, back, kWhite, paper_uv," in draw
assert "c.list.case_cap(" in draw and draw.index("c.list.case_cap(") > draw.index("c.list.case_face(artwork.texture")
assert "const float return_start = back_start + theme::kCaseBackHold;" in draw
assert "constexpr float kFrontYaw = 0.52f;" in draw
assert "constexpr float kBackYaw = 3.14159265358979323846f + 0.44f;" in draw
assert "case_depth, 3.2f" not in draw
assert "const bool printed_side_visible = std::sin(angle) >= 0.0f;" in draw
assert "Color::rgb(0xb61626, 0.78f)" not in draw
assert "c.list.case_spine(side_strip, angle, 3.2f," not in draw
indexer = (root / "tools/launcher/build-box-art-index.py").read_text()
workflow = (root / ".github/workflows/build-040-zbic.yml").read_text()
packager = (root / "tools/package-headless-native.sh").read_text()
assert "Nintendo Switch" in indexer
assert "def candidates(items, limit=6):" in indexer
assert "flat spine candidates" in indexer
assert "Box - Front" in indexer and "Box - Back" in indexer
assert "gamesdb.launchbox-app.com/Metadata.zip" in indexer
assert "if len(matching) != 1:" in indexer
assert "SafeCaseFilename" in native
assert 'std::array<std::vector<std::string>, 3>' in native
assert "w >= 750 && h >= 1100" in native
assert '"Box - Spine"' in indexer
assert "void EnsureRetailCase(" in native
assert "RetailCaseIndex()" in native
assert 'Eden::AppFile("ui/box-art-index.tsv")' in native
assert 'Common::Net::MakeRequest(' in native
assert '"https://images.launchbox-app.com"' in native
assert "EnsureRetailCase(game.title_id, game.name," in native
assert "1500.0f / width, 2100.0f / height" in native
assert "ValidNlibTga(path)" in native
assert "CleanTitle(game.file), cancel);" in native
assert 'IsFile(base + ".png")' in native
assert "ui/box-art-index.tsv" in workflow
assert "tools/launcher/build-box-art-index.py --download" in workflow
assert 'cp -a "$root/headless/prosperoeden/ui" "$app/ui"' in packager
assert "MakeRequest" not in launch_setup and "MakeRequest" not in draw
assert "launch_hero_ = game.hero;" in launcher
assert "launch_hero_ = home_.last_hero;" in launcher
assert "c.list.image(background.texture, kScreen, uv," in draw
assert "theme::kScrim.with_alpha(0.16f)" in draw
# Projective body and spine are shared geometry; game title only selects art.
assert "const std::string& scan = back ? launch_box_back_ : launch_box_front_;" in draw
assert "0x01007EF00011E000" not in draw
shapes = (root / "headless/prosperoeden/pe/gfx/draw_list.hpp").read_text()
drawlist = (root / "headless/prosperoeden/pe/gfx/draw_list.cpp").read_text()
shader = (root / "headless/prosperoeden/pe/gfx/gl_batch.cpp").read_text()
assert "case_face = 9" in shapes and "case_spine = 10" in shapes
assert "case_plastic = 11" in shapes
assert "case_cap = 12" in shapes
assert "case_corner = 13" in shapes
assert "case_spine_image = 14" in shapes
assert "case_spine_blank = 15" in shapes
assert "void DrawList::case_spine_blank(" in drawlist
assert "void DrawList::case_face(" in drawlist
assert "void DrawList::case_spine(" in drawlist
assert "void DrawList::case_plastic(" in drawlist
assert "void DrawList::case_cap(" in drawlist
assert "void DrawList::case_corner(" in drawlist
assert "void DrawList::case_spine_image(" in drawlist
assert "depth_offset * transform_.scale" in drawlist
assert "clip_w = max(0.65, 1.0 - pitched_z / 820.0)" in shader
assert "float pitched_y = world_y * cos(pitch) - z * sin(pitch);" in shader
assert "gl_Position = vec4(ndc.x * clip_w, -ndc.y * clip_w, 0.0, clip_w);" in shader
assert "1.0 - corner.x : corner.x" in shader
assert "shape == 9 || shape == 10 || shape == 11 || shape == 12" in shader
assert "else if (shape == 11)" in shader
assert "else if (shape == 12)" in shader
assert "else if (shape == 13)" in shader
assert "else if (shape == 14)" in shader
assert "else if (shape == 15)" in shader
assert "printed_side_visible" in draw
assert "c.list.case_spine_image(ink.texture, side_strip, angle," in draw
assert "True rounded corner" in shader
assert "float radius = v_params.z > 0.5 ? 18.0 : 22.0;" in shader
assert "float scan_inside = v_params.z > 0.5 ?" in shader
assert "paper_uv.h = source_aspect / target_aspect;" in draw
assert "paper_uv.w = target_aspect / source_aspect;" in draw
assert "w < (narrow_spine ? 64 : 128)" in native
assert "h < (narrow_spine ? 600 : 200)" in native
assert "c.list.case_spine(side_strip, angle, 3.2f," not in draw
assert "c.list.case_spine_blank(side_strip, angle, case_depth," in draw
assert "constexpr float kPaperSideInset = 9.0f;" in draw
assert "constexpr float kPaperTopInset = 13.0f;" in draw
assert "const Rect face{physical.x + kPaperSideInset," in draw
assert draw.count("const Rect face{") == 1
assert "float rounded = round_box(v_local, v_half, 22.0);" in shader
assert "angle, false, case_depth," in draw
assert "c.list.case_corner(physical, angle, case_radius, case_depth," in draw
assert "constexpr float case_depth = 44.0f;" in draw
assert "float depth = a_params.y > 0.5 ? 44.0 : 0.0;" in shader
assert "constexpr float case_radius = 22.0f;" in draw
assert "float rounded = round_box(v_local, v_half, 22.0);" in shader
assert "float fresnel = pow(1.0 - abs(cos(v_params.x)), 3.0);" in shader
assert "case_depth * std::abs(std::sin(angle))" in draw
assert "if (!selected_game_.empty()) {\n        draw_launch(c);\n        return;" in launcher
preview_source = (root / "headless/prosperoeden/host/preview_main.cpp").read_text()
preview_workflow = (root / ".github/workflows/launcher-production-preview.yml").read_text()
assert 'PE_PREVIEW_BOTW: "1"' in preview_workflow
assert "tools/launcher/preview-botw-media.py" in preview_workflow
assert "00-launch-case-front" in preview_source
assert "01-launch-case-spine" in preview_source
assert "02-launch-case-back" in preview_source
assert "PE_PREVIEW_NO_BOX_SCANS" in preview_workflow
assert "UNIVERSAL_CASE_NO_RETAIL_ART: PASS" in preview_workflow
assert "const float return_start = back_start + theme::kCaseBackHold;" in draw
assert "angle = kBackYaw;" in draw
assert "const Cover ink = c.textures.cover(launch_box_spine_, 760.0f);" in draw
assert "std::string fallback;" in draw
assert "constexpr float kPaperSideInset = 9.0f;" in draw
assert "constexpr float kPaperTopInset = 13.0f;" in draw
assert "const Rect face{physical.x + kPaperSideInset," in draw
assert draw.count("const Rect face{") == 1
assert "int side = 0" in shapes
assert "a_extra.x < -0.5 ? -0.5 :" in shader
assert "botw-back.tga" in (root / "tools/launcher/preview-botw-media.py").read_text()
assert "4b815db4-d2d1-4587-89c7-f82524750914.jpg" in (
    root / "tools/launcher/preview-botw-media.py").read_text()
print("PASS source-scans region fallback, readable back, rounded solid 3D case")
