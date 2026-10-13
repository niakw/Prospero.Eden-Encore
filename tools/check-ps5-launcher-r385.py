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
hero_layout=(ui/'hero_text_layout.hpp').read_text()
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
assert 'text_shrink(c, title_label, kHeroX' in home
assert 'kHeroContentWidth, Align::left, 0.0f, 0.45f)' in home
assert 'text_block(c, title_label, kHeroX' not in home
assert 'text_block_semantic(c, hero_caption, kHeroX' in home
assert 'kHeroX + kHeroContentWidth - chip_x' in home
assert 'room / desired' in home
assert 'list.image(hero_picture.texture, hero, uv' in home
assert 'theme::kBody, kHeroContentWidth, 2, 0.90f' in home
assert 'constexpr float kChipGap = 9.0f' in home
assert 90+1250 <= 1340

# Hero titles are always one responsive line. Only Nlib's long description
# may populate the synopsis (no one-line intro fallback). A real C++ test
# exercises the same header-only measured layout that the renderer calls.
assert 'hero_description;' in home
assert '!hero_intro.empty() ? hero_intro' not in home
assert 'const std::string &hero_intro' not in home
assert 'hero_text::wrap_description(value, drawn, max_width, max_lines, measure)' in widgets
assert 'font.measure(part, scale)' in widgets
assert 'font.wrap(value, drawn, max_width)' in widgets  # generic non-Hero text only
assert 'inline bool weak_ending(std::string_view word)' in hero_layout
assert 'const std::string candidate = line + " ...";' in hero_layout
assert 'out.lines.pop_back();' in hero_layout
subprocess.run([sys.executable, '-B', str(root / 'tools/check-hero-text-layout.py')],
               check=True, timeout=60)

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
    f=Path(directory)/'commit-subjects.txt'
    f.write_text('docs: updated engineering notes\nR384: old\nR385: new\n')
    result=subprocess.run([sys.executable,'-B',str(script),str(f)],capture_output=True,text=True)
    assert result.returncode==0 and result.stdout.strip()=='R385',result.stderr
    f.write_text('docs: update\nR384: old\nR386: newer\n')
    result=subprocess.run([sys.executable,'-B',str(script),str(f)],capture_output=True,text=True)
    assert result.returncode==0 and result.stdout.strip()=='R386'
    f.write_text('docs: only this commit\n')
    result=subprocess.run([sys.executable,'-B',str(script),str(f)],capture_output=True,text=True)
    assert result.returncode!=0
# The native build must not derive the footer from the historical MEMORY file.
assert 'derive-encore-build-label.py" "$root/MEMORY.md"' not in native
assert 'fetch-depth: 256' in (root/'.github/workflows/build-040-zbic.yml').read_text()
current_result=subprocess.run([sys.executable,'-B',str(script)],
                              capture_output=True,text=True)
if current_result.returncode == 0:
    current=current_result.stdout.strip()
    assert re.fullmatch(r'R[0-9]+',current) and int(current[1:]) >= 457, current
else:
    # Lightweight source preflights check out only HEAD. The native build
    # checks out 256 commits and must fail closed if it cannot derive R.
    shallow=subprocess.run(['git','-C',str(root),'rev-parse','--is-shallow-repository'],
                           capture_output=True,text=True,check=True).stdout.strip()
    assert shallow=='true' and 'No numbered R revision' in current_result.stderr, current_result.stderr
print('R401 HERO STATIC PASS: one-line measured title, long synopsis only, two-line semantic clipping, 4 bounded chips')
