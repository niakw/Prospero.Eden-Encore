#!/usr/bin/env python3
"""Source-extracted release Font::wrap: no candidate copies; Unicode parity.

Compiles the actual checked-in function at O0 and O2. A legacy source-equivalent
reference must generate exactly the same lines for long words, CJK boundaries,
combining marks, empty paragraphs and RTL paragraph markers. HOST ONLY.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/"headless/prosperoeden/pe/gfx/font.cpp").read_text()
start = "std::vector<std::string> Font::wrap(std::string_view text, float size, float max_width) const"
assert source.count(start) == 1
real = start + source.split(start, 1)[1].split("\n}\n\nstd::string Font::fit", 1)[0] + "\n}"
assert "part.reserve(word.size());" in real
assert "const std::size_t previous = part.size();" in real
assert "part.resize(previous);" in real
assert "const std::size_t previous = line.size();" in real
assert "line.resize(previous);" in real
assert "std::string candidate" not in real
assert "measure(part + std::string(character)" not in real

new1 = "        part.reserve(word.size());\n"
new2 = """            if (!part.empty())
            {
                // Append in-place, then roll back only if this cluster crosses
                // the line boundary. Avoid a copied candidate per UTF-8 glyph.
                const std::size_t previous = part.size();
                part.append(character);
                if (measure(part, size) > max_width)
                {
                    part.resize(previous);
                    lines.push_back(part);
                    part.assign(character);
                }
            }
            else
                part.append(character);"""
old2 = """            if (!part.empty() && measure(part + std::string(character), size) > max_width)
            {
                lines.push_back(part);
                part.clear();
            }
            part.append(character);"""
new3 = """                // The old candidate construction copied the current line
                // on every word. Measure a tentative in-place append instead.
                const std::size_t previous = line.size();
                if (previous != 0 && p == 0)
                    line.push_back(' ');
                line.append(piece);
                if (measure(line, size) > max_width)
                {
                    line.resize(previous);
                    if (!line.empty())
                        lines.push_back(line);
                    if (measure(piece, size) > max_width)
                        split_word(piece);
                    else
                        line.assign(piece);
                }"""
old3 = """                const std::string candidate =
                    line.empty() ? std::string(piece) : line + (p == 0 ? " " : "") + std::string(piece);
                if (measure(candidate, size) <= max_width)
                {
                    line = candidate;
                }
                else
                {
                    if (!line.empty())
                        lines.push_back(line);
                    if (measure(piece, size) > max_width)
                        split_word(piece);
                    else
                        line.assign(piece);
                }"""
for fragment in (new1,new2,new3):
    assert real.count(fragment) == 1, "selected wrap changed without reference update"
legacy = real.replace(new1, "", 1).replace(new2,old2,1).replace(new3,old3,1)
legacy = legacy.replace("Font::wrap(", "LegacyFont::wrap(", 1)

cpp = r"""
#include <cassert>
#include <cstddef>
#include <string>
#include <string_view>
#include <vector>
namespace pe::gfx {
char32_t next_codepoint(std::string_view s, std::size_t* i) {
    const auto lead = static_cast<unsigned char>(s[*i]);
    int width = (lead & 0x80) == 0 ? 1 : (lead & 0xe0) == 0xc0 ? 2 :
                (lead & 0xf0) == 0xe0 ? 3 : (lead & 0xf8) == 0xf0 ? 4 : 1;
    if (*i + width > s.size()) width = 1;
    char32_t cp = width == 1 ? lead : lead & ((1 << (7-width))-1);
    for (int n = 1; n < width; ++n)
        cp = (cp << 6) | (static_cast<unsigned char>(s[*i+n]) & 0x3f);
    *i += width;
    return cp;
}
bool breaks_between(char32_t before, char32_t now) {
    return before >= 0x4e00 && before <= 0x9fff &&
           now >= 0x4e00 && now <= 0x9fff;
}
namespace bidi {
bool attaches(char32_t cp) { return cp == 0x301 || cp == 0x308; }
int paragraph_level(const std::vector<char32_t>& text) {
    for (auto cp: text) if (cp >= 0x590 && cp <= 0x5ff) return 1;
    return 0;
}
}
class Font {
public:
    float measure(std::string_view text, float size) const {
        float w = 0;
        for (std::size_t p = 0; p < text.size();) {
            auto cp = next_codepoint(text, &p);
            if (bidi::attaches(cp)) continue;
            w += cp >= 0x4e00 && cp <= 0x9fff ? size * 1.5f : size;
        }
        return w;
    }
    const void* shaped(std::string_view text) const {
        return text.find("\xd7") == std::string_view::npos ? nullptr : this;
    }
    std::vector<std::string> wrap(std::string_view, float, float) const;
};
class LegacyFont : public Font {
public:
    std::vector<std::string> wrap(std::string_view, float, float) const;
};
""" + real + "\n" + legacy + r"""
}
int main() {
    const pe::gfx::Font actual;
    const pe::gfx::LegacyFont previous;
    const std::vector<std::string> cases = {
        "", " ", "   ", "one", "FC27 player career HUD scoreboard",
        "Zelda Breath of the Wild", "superlongunbreakablewordtestcase",
        "word    lots   of spaces", "alpha\n\nbeta", "\ntrailing\n",
        "Éden a\xcc\x81 team", "a\xcc\x81\xcc\x88bc a\xcc\x81 xyz",
        "\xe4\xbd\xa0\xe5\xa5\xbd\xe4\xb8\x96\xe7\x95\x8c", // Chinese
        "\xd7\x90\xd7\x91\xd7\x92 \xd7\x93\xd7\x94  abc", // RTL
        "\xe4\xb8\xad\xe5\x9b\xbd hello \xe4\xb8\x96\xe7\x95\x8c"
    };
    for (const auto& sample : cases)
        for (float size : {0.5f, 1.f, 2.5f})
            for (float width : {-1.f, 0.f, 0.5f, 1.f, 2.f, 4.f, 6.f, 16.f, 100.f})
                assert(actual.wrap(sample,size,width) ==
                       previous.wrap(sample,size,width));
    for (int n = 0; n < 130; ++n) {
        const std::string sample(n,'A');
        assert(actual.wrap(sample,1.f,n/3.f) ==
               previous.wrap(sample,1.f,n/3.f));
    }
}
""";
with tempfile.TemporaryDirectory(prefix="encore-wrap-release-") as tmp:
    src = Path(tmp)/"wrap.cpp"
    src.write_text(cpp)
    for opt in ("-O0","-O2"):
        binary = Path(tmp)/("wrap"+opt[2:])
        subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",opt,
                        str(src),"-o",str(binary)],
                       check=True,timeout=40,capture_output=True,text=True)
        subprocess.run([str(binary)],check=True,timeout=15)
print("ENCORE_RELEASE_FONT_WRAP_HOST_PASS selected=1 O0=1 O2=1 unicode=1 candidates_elided=1")
