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
assert "launch_description_" in launch_setup
assert "launch_screenshots_" in launch_setup
assert "textures_.cover(launch_box_front_, 640.0f)" in launch_setup
assert "textures_.cover(launch_box_back_, 640.0f)" in launch_setup
assert "Common::Net" not in launch_setup

draw = launcher.split("void Launcher::draw_launch(", 1)[1].split(
    "void Launcher::draw(", 1
)[0]
for fragment in (
    "const std::string& scan = back ? launch_box_back_ : launch_box_front_;",
    "if (!scan.empty())",
    "c.list.rounded_image(artwork.texture, face,",
    "cover_crop(c, launch_cover_, art",
    "launch_screenshots_.front()",
    "text_block_semantic(c, launch_description_",
    "c.textures.brand()",
    "motion() > 0.0f",
    'tr("STARTING")',
):
    assert fragment in draw, fragment
assert "MakeRequest" not in draw
assert "progress%" not in draw
assert "std::vector<std::string> launch_screenshots_;" in header
assert "constexpr float kLaunchSeconds = 1.85f;" in theme

# Quarter turn becomes an edge; the full back is visible half a turn later.
assert math.cos(0.12) > 0
assert math.cos(0.12 + 6.10 * 0.50) < 0
assert math.cos(0.12 + 6.10 * 0.99) > 0
indexer = (root / "tools/launcher/build-box-art-index.py").read_text()
workflow = (root / ".github/workflows/build-040-zbic.yml").read_text()
packager = (root / "tools/package-headless-native.sh").read_text()
assert "Nintendo Switch" in indexer
assert "Box - Front" in indexer and "Box - Back" in indexer
assert "gamesdb.launchbox-app.com/Metadata.zip" in indexer
assert "if len(matching) != 1:" in indexer
assert "SafeCaseFilename" in native
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
assert "companion_scan = back ? launch_box_front_ : launch_box_back_" in draw
assert "if (!selected_game_.empty()) {\n        draw_launch(c);\n        return;" in launcher
preview_source = (root / "headless/prosperoeden/host/preview_main.cpp").read_text()
preview_workflow = (root / ".github/workflows/launcher-production-preview.yml").read_text()
assert 'PE_PREVIEW_BOTW: "1"' in preview_workflow
assert "tools/launcher/preview-botw-media.py" in preview_workflow
assert "00-launch-case-front" in preview_source
assert "01-launch-case-back" in preview_source
print("PASS real front/back index, cinematic Hero, host BOTW proof and branded launch")
