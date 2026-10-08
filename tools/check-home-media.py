#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
hpp=(root/'headless/prosperoeden/pe/ui/launcher.hpp').read_text()
lib=(root/'headless/prosperoeden/pe/ui/library.cpp').read_text()
home=(root/'headless/prosperoeden/pe/ui/home.cpp').read_text()
launch=(root/'headless/prosperoeden/pe/ui/launcher.cpp').read_text()
svc=(root/'headless/prosperoeden/eden_services.cpp').read_text()
for needle in ('start_home_media()', 'finish_home_media()', 'home_media_scan_', 'home_media_next_retry_'):
    assert needle in hpp, needle
assert 'start_home_media();\n}' in home
# All Nlib images are fetched for every installed title; no Home-first subset.
assert 'home_media_priority' not in svc + lib + hpp
assert 'const int wanted_screens = std::clamp(screen_count, 0, 3);' in svc
assert 'const int selected = std::clamp(library_.selected' in lib
assert 'for (std::size_t offset = 0; offset < games_.size(); ++offset)' in lib
assert 'start_selected_media();' in lib[lib.index('void Launcher::apply_games'):lib.index('void Launcher::name_home_games')]
assert 'artwork_files.resize(6)' not in svc
assert 'Only Home/recent titles' not in svc
assert 'services_.enrich_game_media(std::move(request))' in lib
assert 'home_.last_hero = enriched.hero' in lib
assert 'home_.last_max_players = enriched.max_players' in lib
assert 'recent.max_players = enriched.max_players' in lib
assert 'finish_home_media();' in launch
assert 'home_media_scan_.wait();' in launch
assert 'artwork_tasks' not in svc
assert 'A library enumeration itself must remain local/cache-only' in svc
assert 'const Rect hero{0.0f, 0.0f, 1920.0f, 1080.0f};' in home
for needle in ('quick settings overlay', 'recently played: seven-ish large artwork tiles',
               'utility cards: the four Home actions', 'hero_button(details_rect, "..."'):
    assert needle in home, needle
assert 'recent.max_players' not in home
assert 'const Cover hero_picture = c.textures.cover(hero_artwork, 1920.0f)' in home
print('All-games complete Nlib artwork + TV-first layout PASS')
