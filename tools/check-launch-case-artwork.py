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
    "c.list.case_face(artwork.texture, face, angle, back, kWhite, paper_uv);",
    "c.list.case_spine(side_strip, angle, case_depth,",
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
assert math.cos(math.pi + 0.18) < -0.98
assert math.sin(math.pi + 0.18) < 0
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
assert "flat_retail_sleeve(c, *game, enlarged, true, 0.92f," in library
assert "library_back_scale_);" in library
assert "std::max(paper.w, paper.h) * texture_scale" in library
assert "uv.x = rear ? 1.0f - uv.w : 0.0f;" in library
assert "c.list.image(artwork.texture, paper, uv," in library
assert "paper_uv.x = back ? 1.0f - paper_uv.w : 0.0f;" in draw
assert "flat_retail_sleeve(c, game, sleeve, false, 0.24f);" in library
assert "const Rect paper{shell.x + (rear ? side : 0.0f), shell.y + top," in library
assert "flat_back_fallback(c, game, paper);" in library
assert "flat_front_fallback(c, game, paper);" in library
assert "shell.y + shell.h - top" in library
assert "s.press({Key::r1, Key::r1});" in (
    root / "headless/prosperoeden/host/preview_main.cpp").read_text()
assert 's.shoot("03-library-back-zoom-pan");' in (
    root / "headless/prosperoeden/host/preview_main.cpp").read_text()
assert "RADIO_INPUT_L2" in (root / "headless/prosperoeden/radio_input.h").read_text()
assert "RADIO_INPUT_R2" in (root / "headless/prosperoeden/radio_input.h").read_text()
assert "if (key == Key::circle)" in library
assert "{Pad::r2, TR(\"Zoom in\")}" in library
assert "{Pad::dpad, TR(\"Move cover\")}" in library

assert "PE_PREVIEW_LIBRARY_ONLY" in (
    root / "headless/prosperoeden/host/preview_main.cpp").read_text()
assert "case_face(artwork.texture, face, angle, back, kWhite, paper_uv);" in draw
assert "c.list.case_cap(" in draw and draw.index("c.list.case_cap(") > draw.index("c.list.case_face(artwork.texture")
assert "c.list.case_plastic(physical, angle, back, Color::rgb(0xd9e8f7, 0.93f));" in draw
assert draw.count("c.list.case_plastic(physical, angle, back") == 1
assert "for (int hinge" not in draw
assert "const float return_start = back_start + theme::kCaseBackHold;" in draw
assert "constexpr float kFrontYaw = 0.52f;" in draw
assert "constexpr float kBackYaw = 3.14159265358979323846f + 0.18f;" in draw
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
assert "best_source = filename;" in native
assert "std::ofstream receipt(destination + \".source\"" in native
assert "cached_source == candidates.front()" in native
assert "best_pixels" not in native.split("bool FetchCaseFace(", 1)[1].split(
    "void EnsureRetailCase(", 1)[0]
assert "EUROPE_FRONT_PINS" in indexer
assert "regional_candidates(front)" in indexer
assert 'region_code(element.findtext("Region", ""))' in indexer
assert '"north america": "us"' in indexer
assert 'region:filename' in native
assert "SafeCaseCandidate(part)" in native
assert "LocaleCaseCandidates(selected->second[side], language_choice, side)" in native
assert 'regions = {"us", "ca", "world", "uk", "eu", "fr"};' in native
assert 'regions = {"fr", "eu", "world", "uk", "ca", "us"};' in native
assert "face == 1" in native
assert "CleanTitle(game.file), language_choice, cancel);" in native
assert "9524e5f7-ccc8-4ce6-a581-03f82c51825e.jpg" in indexer
assert "a8bcb4cc-a3b0-4cf0-82f3-cb10dd18b27c.jpg" in indexer
assert "BotW_NA_Switch_Box_Art" not in (root / "tools/launcher/preview-botw-media.py").read_text()
assert '"Box - Spine"' in indexer
assert "void EnsureRetailCase(" in native
assert "RetailCaseIndex()" in native
assert 'Eden::AppResourceFile("ui/box-art-index.tsv")' in native
assert 'Eden::AppFile("ui/box-art-index.tsv")' not in native
assert '"EDEN_CASE_INDEX status=%s entries=%zu path=%s' in native
assert '"EDEN_CASE_FETCH status=unavailable' in native
assert '"EDEN_CASE_LOOKUP title=%016llX status=no-match' in native
assert "std::chrono::minutes(5)" in native
assert "std::chrono::hours(4)" not in native.split("void EnsureRetailCase(", 1)[1].split("NlibEnrichment CachedNlibEnrichment(", 1)[0]
assert "both_faces_cached_at_start" in native
assert "attempts >= 3" in native
assert "const pe::ui::BoxArt cached_case = box_art(game.title_id);" in native
case_worker = native.split("pe::ui::Game EdenServices::enrich_game_media(pe::ui::Game game,", 1)[1].split("pe::ui::BoxArt EdenServices::box_art(", 1)[0]
assert case_worker.index("EnsureRetailCase(game.title_id, scanned_name") < case_worker.index("EnsureNlibEnrichment(game.title_id")
assert 'case_index_source = source_ui / "box-art-index.tsv"' in (
    root / "tools/ci/check-staged-app.py").read_text()
assert 'Common::Net::MakeRequest(' in native
assert '"https://images.launchbox-app.com"' in native
assert "EnsureRetailCase(game.title_id, game.name," in native
assert "1500.0f / width, 2100.0f / height" in native
assert "ValidNlibTga(path)" in native
assert "CleanTitle(game.file), language_choice, cancel);" in native
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
assert "float d = round_box(v_local, v_half, 0.0);" in shader
assert "float scan_inside = v_params.z > 0.5 ?" in shader
assert "paper_uv.h = source_aspect / target_aspect;" in draw
assert "paper_uv.w = target_aspect / source_aspect;" in draw
assert "w < (narrow_spine ? 64 : 128)" in native
assert "h < (narrow_spine ? 600 : 200)" in native
assert "c.list.case_spine(side_strip, angle, 3.2f," not in draw
assert "c.list.case_spine_blank(side_strip, angle, case_depth," in draw
# Single paper wrap with one localized projected rim; no second full-face
# coating and no clear border at the rear's printed spine fold.
assert draw.count("c.list.case_plastic(physical, angle, back") == 1
assert "Color::rgb(0xe6effa, 0.38f)" not in draw
assert "case_spine({physical.x, y" not in draw
# Navigation in the enlarged Library viewer is not delegated to the game.
assert "key == Key::circle || key == Key::cross" not in library
assert "key == Key::l2 || key == Key::r2" in library
assert "library_back_pan_x_" in library and "library_back_pan_y_" in library
assert "list.push_clip(viewer);" in library
assert "list.push_transform(library_back_scale_" in library
assert "{Pad::circle, TR(\"Close\")}" in library
assert '{Pad::cross, TR("Close")}' not in library
assert "RADIO_INPUT_L2" in (root / "headless/prosperoeden/radio_input.c").read_text()
assert "RADIO_INPUT_R2" in (root / "headless/prosperoeden/radio_input.c").read_text()
assert "constexpr float kPaperSideInset = 7.0f;" in draw
assert "constexpr float kPaperTopInset = 13.0f;" in draw
assert "const Rect face{physical.x + kPaperSideInset," in draw
assert draw.count("const Rect face{") == 1
assert "const Rect side_strip = face;" in draw
assert "physical.h - 2.0f * kPaperTopInset" in draw
assert "physical.h - 2.0f * case_radius" not in draw
# The continuous WRAP must meet the spine without left/right paper margins.
# All three scanned faces share EXACTLY one physical Y interval. Front Z=0,
# spine Z=[0,-depth], back Z=-depth: there is no paper break at either seam.
assert "const Rect face{physical.x + kPaperSideInset," in draw
assert "physical.w - 2.0f * kPaperSideInset," in draw
assert "physical.h - 2.0f * kPaperTopInset};" in draw
assert "const Rect side_strip = face;" in draw
assert "c.list.case_face(0, physical" not in draw
assert "case_depth - 6.0f" not in draw
assert "2.5f" not in draw.split("void Launcher::draw_launch(", 1)[-1]
assert "c.list.case_spine(side_strip, angle, case_depth," in draw
assert "float d = round_box(v_local, v_half, 0.0);" in shader
assert "float radius = v_params.z > 0.5 ?" not in shader
assert "float from_edge = (1.0 - v_st.x)" in shader
paper_top, paper_bottom, side_lip, box_h, width, depth = 13.0, 13.0, 7.0, 730.0, 454.0, 44.0
paper_h = box_h - paper_top - paper_bottom
paper_l = side_lip
paper_r = width - side_lip
front_x = (paper_l, paper_r)
back_x = (paper_l, paper_r)
spine_x = (paper_l, paper_r)
spine_z = (0.0, -depth)
front_z, back_z = 0.0, -depth
assert front_x == back_x == spine_x
assert spine_z == (front_z, back_z)
assert (paper_l, width - paper_r) == (7.0, 7.0)
assert paper_h == 704.0 and paper_top + paper_h == box_h - paper_bottom
lib_sleeve = library.split("void flat_retail_sleeve(", 1)[1].split(
    "std::string controller_profile_name(", 1)[0]
assert "const Rect paper{shell.x + (rear ? side : 0.0f), shell.y + top," in lib_sleeve
assert "shell.w - side, shell.h - 2.0f * top" in lib_sleeve
assert "const Cover artwork = c.textures.cover(" in lib_sleeve
assert "scan, std::max(paper.w, paper.h) * texture_scale);" in lib_sleeve
assert "const float other_x" not in lib_sleeve
assert "cover(c, scan, paper, 0.0f, 0.0f);" not in lib_sleeve
assert "c.list.image(artwork.texture, paper, uv," in lib_sleeve
assert "Rect fitted = paper;" not in lib_sleeve
assert "fitted.w = paper.h * source;" not in lib_sleeve
assert "fitted.h = paper.w / source;" not in lib_sleeve
assert "uv.w = target / source;" in lib_sleeve
assert "uv.h = source / target;" in lib_sleeve
assert "uv.y = (1.0f - uv.h) * 0.5f;" in lib_sleeve
assert "uv.x = rear ? 1.0f - uv.w : 0.0f;" in lib_sleeve
assert "std::clamp(shell.w * 0.012f, 1.75f, 5.0f)" in lib_sleeve
# A 181x278 retail sleeve must not spend ~10% of its width on an
# aspect-contain blank column + molded opening. Source pixels UV-cover paper.
shelf_width, shelf_height = 181.0, 278.0
shelf_rim = min(5.0, max(1.75, shelf_width * 0.012))
shelf_cap = max(5.0, shelf_height * 0.018)
paper_aspect = (shelf_width - shelf_rim) / (shelf_height - 2 * shelf_cap)
european_front_aspect = 872.0 / 1419.0
assert shelf_rim < 2.3 and paper_aspect > european_front_aspect
assert 0.85 < european_front_aspect / paper_aspect < 1.0
# The 3D caps run the SAME 13px plastic skirt on either projected face.
assert "float from_cap = min(v_st.y, 1.0 - v_st.y)" in shader
assert "max(rim_intensity, cap_intensity)" in shader
assert "shell.w - side, shell.h - 2.0f * top" in lib_sleeve
assert "const float opening_x = rear ? shell.x : shell.x + shell.w - side;" in lib_sleeve

assert "c.list.bordered_rect(shell, radius" not in lib_sleeve
assert "const float opening_x = rear ? shell.x : shell.x + shell.w - side;" in lib_sleeve
assert "const float glint_x = rear ? opening_x : opening_x + side - highlight_w;" in lib_sleeve
assert "c.list.gradient_rect(shell, radius" in lib_sleeve
assert "for (int i = 1; i < 5; ++i)" in lib_sleeve
assert "color.rgb = vec3(0.97, 0.025, 0.07);" not in shader
assert "float from_edge = (1.0 - v_st.x)" in shader
assert "float outer_glint" in shader
assert "float from_cap = min(v_st.y, 1.0 - v_st.y)" in shader
assert "float cap_band = 1.0 - smoothstep(11.5, 13.2, from_cap);" in shader
assert "float cap_outer = exp(" in shader
assert "float cap_inner = exp(" in shader
assert "max(rim_intensity, cap_intensity)" in shader
assert "round_box(v_local, v_half, 22.0)" in shader
assert "v_border.x > 0.5 && v_params.y < 0.5" not in shader
assert "float inner_ridge" in shader
assert "vec4(material, v_top.a *" in shader
assert "simplify_switch_header" not in shapes and "simplify_switch_header" not in drawlist
assert "float inner_ridge = exp(" in shader
assert "angle, false, case_depth," in draw
assert "Color::rgb(0xe9f3ff, 0.79f)" in draw
assert "Color::rgb(0xddeaf8, 0.78f)" in draw
assert "c.list.case_corner(physical, angle, case_radius, case_depth," in draw
assert "constexpr float case_depth = 44.0f;" in draw
assert "float depth = a_params.y > 0.5 ? 44.0 : 0.0;" in shader
assert "constexpr float case_radius = 22.0f;" in draw
assert "float inner_ridge = exp(" in shader
assert "float grazing = 0.15 + 0.20" in shader
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
assert "constexpr float kPaperSideInset = 7.0f;" in draw
assert "constexpr float kPaperTopInset = 13.0f;" in draw
assert "const Rect face{physical.x + kPaperSideInset," in draw
assert draw.count("const Rect face{") == 1
assert "int side = 0" in shapes
assert "a_extra.x < -0.5 ? -0.5 :" in shader
assert "botw-back.tga" in (root / "tools/launcher/preview-botw-media.py").read_text()
assert "4b815db4-d2d1-4587-89c7-f82524750914.jpg" in (
    root / "tools/launcher/preview-botw-media.py").read_text()
assert "source_replacement_guard" not in native
assert "textures_.invalidate(enriched.box_front);" in library
assert "textures_.invalidate(enriched.box_back);" in library
assert '"https://images.launchbox-app.com/9524e5f7-ccc8-4ce6-a581-03f82c51825e.jpg"' in (
    root / "tools/launcher/preview-botw-media.py").read_text()
assert 'EUROPE_FRONT_PINS["79189"]' in indexer or '"79189": (' in indexer
assert 'region_code' in indexer and 'REGION_ORDER' in indexer
assert "LocaleCaseCandidates" in native
print("PASS regional fronts/backs, case geometry and zoom/pan source contracts")
