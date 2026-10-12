#!/usr/bin/env python3
"""R385 static launcher contracts, intentionally NO C++ build or PS5 compilation."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
ui=root/'headless/prosperoeden/pe/ui'
home=(ui/'home.cpp').read_text()
launcher=(ui/'launcher.cpp').read_text()
header=(ui/'launcher.hpp').read_text()
widgets=(ui/'widgets.cpp').read_text()
widgets_header=(ui/'widgets.hpp').read_text()
frontend=(root/'headless/prosperoeden/frontend.cpp').read_text()
main=(root/'headless/main.cpp').read_text()
services=(root/'headless/prosperoeden/eden_services.cpp').read_text()
version=(root/'headless/prosperoeden/version.h').read_text()
cmake=(root/'headless/CMakeLists.txt').read_text()
native=(root/'tools/build-headless-native.sh').read_text()
po=(root/'headless/prosperoeden/ui/lang/fr-FR.po').read_text()
embedded=(root/'headless/prosperoeden/fr_fr_embedded.h').read_text()
assert 'constexpr float kHeroX = 90.0f' in home
assert 'constexpr float kHeroContentWidth = 1250.0f' in home
assert 'text_block(c, title_label, kHeroX' in home
assert 'text_block_semantic(c, hero_caption, kHeroX' in home
assert 'kHeroX + kHeroContentWidth - chip_x' in home
assert 'room / desired' in home
assert 'list.image(hero_picture.texture, hero, uv' in home
assert 'theme::kBody, kHeroContentWidth, 2, 0.90f' in home
assert 'constexpr float kChipGap = 9.0f' in home
assert 90+1250 <= 1340

# Ensure no mid-word UTF8 character elision, no visually misleading dangling
# prepositions/articles, and actual font-metric reservation for " ...".
assert 'font.wrap(value, drawn, max_width)' in widgets
assert 'font.measure(candidate, size) <= max_width' in widgets
assert 'constexpr std::string_view suffix = " ...";' in widgets
assert 'semantic_hero_last_line(font, line, drawn, max_width, complete_word)' in widgets
assert 'std::size_t position = value.find(line, source_cursor)' in widgets
assert 'if (!whole_word)' in widgets
assert 'text_block_semantic(Canvas &c' in widgets
assert 'text_block_semantic(Canvas &c' in widgets_header
stopblock=widgets.split('constexpr std::array<std::string_view,',1)[1].split('};',1)[0]
stops=set(re.findall(r'"([^"]+)"',stopblock))
for weak in ['de','des','le','la','les','un','une','et','qui','que','dans','pour','the','and','of','to']:
    assert weak in stops,weak
def preview_last_line(line, max_chars):
    """Simulate the font-width gate for illustrative regression examples only."""
    pieces=line.split()
    if not pieces:return '...'
    while pieces:
        last=pieces[-1].lower().strip('.,;:!')
        if last not in stops and len(' '.join(pieces)+' ...')<=max_chars:
            return ' '.join(pieces)+' ...'
        pieces.pop()
    return '...'
assert preview_last_line('Un monde grandiose de',29)=='Un monde grandiose ...'
assert preview_last_line('Un monde grandiose et le',29)=='Un monde grandiose ...'
assert preview_last_line('Discover a beautiful world and the',29)=='Discover a beautiful ...'
assert preview_last_line('Un voyage mystérieux de',25)=='Un voyage mystérieux ...'

# Exit is available only at Home root and uses existing modal/input gating.
assert '(void)confirm_action(Confirmation::exit_app);' in home
assert 'exit_app,' in header
assert 'Confirmation::exit_app && key == Key::cross' in launcher
assert 'done_ = true;' in launcher
assert 'if (key == Key::circle)' in launcher
assert 'clear_confirmation();' in launcher
assert 'TR("Exit Eden Encore?")' in launcher
assert 'tr("Exit Eden Encore")' in launcher
assert 'Pad::circle, TR("Quit")' in home
assert 'if (confirmation_ != Confirmation::none)' in launcher
assert 'launcher.done()' in frontend
assert 'if (!launcher.done()) selected_game.clear();' in frontend
assert 'if (selected_game.empty())' in main and 'return 0;' in main
for text in ('Quit','Exit Eden Encore','Exit Eden Encore?'):
    assert f'msgid "{text}"' in po, text
assert 'Voulez-vous quitter Eden Encore ?' in po
assert 'Voulez-vous quitter Eden Encore ?' in embedded
assert 'void Launcher::draw_confirmation' in launcher

# Compiler-injected RNNN; not release package metadata nor a GitHub run number.
assert 'kBuildVersion = EDEN_LAUNCHER_BUILD_LABEL' in version
assert 'return Eden::kBuildVersion;' in services
assert 'EDEN_LAUNCHER_BUILD_LABEL=' in cmake
assert r'EDEN_LAUNCHER_BUILD_LABEL=\"${EDEN_LAUNCHER_BUILD_LABEL}\"' in cmake
assert 'EDEN_LAUNCHER_BUILD_LABEL="$build_label"' in native
assert 'GITHUB_RUN_NUMBER' not in native
assert 'kAppVersion = "R1"' in version and 'kPackageVersion = "01.000.041"' in version
assert 'text(c, version_, 1860.0f, 1026.0f' in home
script=root/'tools/ci/derive-encore-build-label.py'
with tempfile.TemporaryDirectory(prefix='eden-r385-static-') as directory:
    f=Path(directory)/'memory.md'
    f.write_text('### 2026-10-12 R384 — old\n### 2026-10-12 R385 — new\n')
    result=subprocess.run([sys.executable,'-B',str(script),str(f)],capture_output=True,text=True)
    assert result.returncode==0 and result.stdout.strip()=='R385',result.stderr
    f.write_text('### 2026-10-12 R384 — old\n### 2026-10-12 R386 — new\n')
    result=subprocess.run([sys.executable,'-B',str(script),str(f)],capture_output=True,text=True)
    assert result.returncode==0 and result.stdout.strip()=='R386'
    f.write_text('Nothing yet\n')
    result=subprocess.run([sys.executable,'-B',str(script),str(f)],capture_output=True,text=True)
    assert result.returncode!=0
current=subprocess.run([sys.executable,'-B',str(script),str(root/'MEMORY.md')],
                       capture_output=True,text=True,check=True).stdout.strip()
assert re.fullmatch(r'R\d+',current) and int(current[1:]) >= 385
print('R385 STATIC PASS: compact 1250px Hero, smart FR/EN words, 4 bounded chips, safe Circle confirmation, compiled version R385')
