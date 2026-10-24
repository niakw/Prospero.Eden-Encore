#!/usr/bin/env python3
"""Execute the actual Encore missing-cover media picker on host C++20.

All scenes come from existing locally cached game media. We never fetch,
invent or duplicate screenshot sources to fill a case page.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = root / "headless/prosperoeden/pe/ui/case_media_selection.hpp"
renderer = (root / "headless/prosperoeden/pe/ui/library.cpp").read_text()
assert '#include "pe/ui/case_media_selection.hpp"' in renderer
assert 'if (painting) reconstructed_cover(c, *painting, r);' in renderer
assert 'reconstructed_paper(c, paper);' in renderer
assert 'scene(game.cover,' not in renderer
assert 'glClearColor' not in renderer
assert 'case_media::BackScenes(hero, game.cover, game.screenshots)' in renderer
source = r"""
#include <cassert>
#include <string>
#include <vector>
#include "pe/ui/case_media_selection.hpp"
int main() {
    using namespace pe::ui::case_media;
    const std::string hero = "hero.tga";
    const std::string icon = "icon.tga";
    const std::vector<std::string> shots{
        "hero.tga", "hero.tga", "scene-2.tga", "scene-2.tga", "scene-3.tga"
    };
    const auto* front = FrontAlternate(hero, icon, shots);
    assert(front != nullptr && *front == "scene-2.tga");
    const auto pair = BackScenes(hero, icon, shots);
    assert(pair[0] && *pair[0] == "scene-2.tga");
    assert(pair[1] && *pair[1] == "scene-3.tga");
    assert(*pair[0] != *pair[1] && *pair[0] != hero && *pair[1] != hero);

    // Only independent screenshot sources may appear on the back.
    // Never insert an app icon as a synthetic second picture.
    const std::vector<std::string> only_hero{"hero.tga", "extra.tga"};
    const auto one = BackScenes(hero, icon, only_hero);
    assert(one[0] && *one[0] == "extra.tga");
    assert(!one[1]);
    assert(FrontAlternate(hero, icon, {"hero.tga", "hero.tga"}) == &icon);

    // A missing icon does not get a fabricated second screenshot.
    const std::string empty;
    const auto alone = BackScenes(hero, empty, only_hero);
    assert(alone[0] && *alone[0] == "extra.tga" && !alone[1]);
    const auto no_media = BackScenes(empty, empty, {});
    assert(!no_media[0] && !no_media[1]);
    assert(FrontAlternate(hero, empty, {"hero.tga"}) == nullptr);

    // When a game only has a front icon/poster, the back stays plain ink.
    const auto only_icon = BackScenes(hero, icon, {});
    assert(!only_icon[0] && !only_icon[1]);
    assert(*FrontPaper(hero, icon, shots) == hero);
    assert(*FrontPaper(empty, icon, shots) == "hero.tga");
    assert(*FrontPaper(empty, icon, {}) == icon);
    assert(FrontPaper(empty, empty, {}) == nullptr);
    const auto excluded_cover = BackScenes(hero, icon, {"icon.tga", "scene.tga"});
    assert(excluded_cover[0] && *excluded_cover[0] == "scene.tga");
    assert(!excluded_cover[1]);

    // All results point into existing metadata, no allocations or copies.
    assert(front == &shots[2]);
    assert(pair[0] == &shots[2] && pair[1] == &shots[4]);
}
"""
compilers = list(dict.fromkeys(filter(None,
    (shutil.which("clang++"), shutil.which("g++"), shutil.which("c++")))))
assert compilers, "Host C++ compiler required"
with tempfile.TemporaryDirectory(prefix="encore-case-media-") as temp:
    cpp = Path(temp) / "case-media.cpp"
    cpp.write_text(source)
    for compiler in compilers:
        for opt in ("-O0", "-O2"):
            exe = Path(temp) / (Path(compiler).name + opt)
            built = subprocess.run(
                [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(root / "headless/prosperoeden"), str(cpp), "-o", str(exe)],
                capture_output=True, text=True, timeout=50
            )
            assert built.returncode == 0, (compiler, opt, built.stderr[-4000:])
            result = subprocess.run(
                [str(exe)], capture_output=True, text=True, timeout=15
            )
            assert result.returncode == 0, (compiler, opt, result.stderr[-4000:])
            print("ENCORE_CASE_MEDIA_DEDUP_PASS", Path(compiler).name, opt)
