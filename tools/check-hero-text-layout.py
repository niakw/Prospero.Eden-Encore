#!/usr/bin/env python3
"""Compile and execute REAL portable Hero synopsis layout, no PS5 runtime."""
from pathlib import Path
import subprocess
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
assert compiler is not None, "C++ compiler required for measured Hero text fixture"
source = r'''
#include "pe/ui/hero_text_layout.hpp"
#include <cassert>
#include <cmath>
#include <string>
#include <string_view>

using pe::ui::hero_text::wrap_description;
using pe::ui::hero_text::weak_ending;

static std::size_t utf8_chars(std::string_view s) {
    std::size_t n = 0;
    for (unsigned char c : s)
        if ((c & 0xc0) != 0x80) ++n;
    return n;
}
static float measure(std::string_view s, float size) {
    // Deterministic fake font; REAL renderer passes gfx::Font::measure.
    return static_cast<float>(utf8_chars(s)) * size * .55f;
}
static bool ends(std::string_view s, std::string_view tail) {
    return s.size() >= tail.size() &&
           s.substr(s.size() - tail.size()) == tail;
}
static void valid(const pe::ui::hero_text::Layout& result, float size, float width) {
    assert(result.lines.size() <= 2);
    for (const auto& line : result.lines) {
        assert(!line.empty() && line != "..." && line != " …");
        assert(measure(line, size) <= width + .01f);
    }
    if (result.truncated && !result.lines.empty())
        assert(ends(result.lines.back(), " ..."));
}
int main() {
    constexpr float size = 20.0f;
    constexpr float width = 235.0f;
    const std::string french =
        "Explorez un immense monde mystérieux rempli de secrets et de villages "
        "à découvrir dans les montagnes, les plaines et les forêts anciennes.";
    auto long_fr = wrap_description(french, size, width, 2, measure);
    valid(long_fr, size, width);
    assert(long_fr.truncated && long_fr.lines.size() == 2);
    assert(long_fr.lines[0].find("Explorez") == 0);
    assert(long_fr.lines.back() != "...");
    auto long_en = wrap_description(
        "Discover a beautiful world full of forests and mysteries while "
        "travelling with your companions through many adventures ahead",
        size, width, 2, measure);
    valid(long_en, size, width);
    assert(long_en.truncated && long_en.lines.size() == 2);
    auto short_text = wrap_description("Un monde plein de secrets",size,width,2,measure);
    valid(short_text,size,width);
    assert(!short_text.truncated && short_text.lines.size() == 2);
    auto short_ellipsis = wrap_description(
        "Un voyage passionnant ...", size, 235.0f, 2, measure);
    valid(short_ellipsis,size,235.0f);
    assert(short_ellipsis.lines.size() == 1);
    for (auto empty : {"", "  \t\n ", "...", "…"}) {
        auto result=wrap_description(empty,size,width,2,measure);
        assert(result.lines.empty());
    }
    auto spaces = wrap_description(
        "Une aventure\n\tgrandiose  au coeur  du   monde\r\nmagique",
        size, width,2,measure);
    valid(spaces,size,width);
    for(const auto& line:spaces.lines)
        assert(line.find('\n') == std::string::npos &&
               line.find("  ") == std::string::npos);
    // French and English last visible words should not be articles/prepositions.
    for(const auto& text : {
        "Un monde grandiose de forêts merveilleuses et de paysages pour ",
        "Discover an incredible adventure and the legends of the ancestors",
        "Une terre magnifique avec des personnages et les destinations"
    }) {
        auto result=wrap_description(text,size,160.f,2,measure);
        valid(result,size,160.f);
        if (result.truncated && !result.lines.empty()) {
            auto line=result.lines.back().substr(0,result.lines.back().size()-4);
            auto split=line.find_last_of(' ');
            auto last=std::string_view(line).substr(
                split==std::string::npos?0:split+1);
            assert(!weak_ending(last));
        }
    }
    // Pathological unbreakable first token: never emit a lone ellipsis.
    auto path=wrap_description(
        "AVeryLongUnbreakableNlibTokenThatCannotPossiblyFit other text follows",
        size, 80.f,2,measure);
    assert(path.lines.size() <= 2);
    for (const auto& line:path.lines) assert(line != "...");
    // Optional two-line allocation is bounded even if full text fits in one.
    auto single=wrap_description("Breath of the Wild",size,235.f,2,measure);
    valid(single,size,235.f);
    assert(single.lines.size()==1 && !single.truncated);
}
'''
with tempfile.TemporaryDirectory(prefix="eden-hero-text-") as directory:
    temp = Path(directory)
    executable = temp / "hero_text_test"
    build = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "headless/prosperoeden"), "-x", "c++",
                            "-", "-o", str(executable)],
                           input=source, text=True, capture_output=True,
                           timeout=35)
    assert build.returncode == 0, build.stderr
    run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
    assert run.returncode == 0, run.stderr
print("R401 HERO LAYOUT PASS: compiled C++ word-boundary / two-line measured ellipsis")
