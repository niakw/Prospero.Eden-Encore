#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def read(path): return (root/path).read_text()
home=read('headless/prosperoeden/pe/ui/home.cpp')
library=read('headless/prosperoeden/pe/ui/library.cpp')
settings=read('headless/prosperoeden/pe/ui/settings.cpp')
browse=read('headless/prosperoeden/pe/ui/browse.cpp')
launcher=read('headless/prosperoeden/pe/ui/launcher.cpp')
launcher_h=read('headless/prosperoeden/pe/ui/launcher.hpp')
widgets=read('headless/prosperoeden/pe/ui/widgets.cpp')
widgets_h=read('headless/prosperoeden/pe/ui/widgets.hpp')
mapping=read('headless/prosperoeden/pe/ui/mapping.cpp')
services=read('headless/prosperoeden/eden_services.cpp')
presets=read('headless/prosperoeden/pe/ui/video_presets.hpp')
store=read('headless/settings_store.h')
devices=read('headless/devices.h')
pad=read('headless/pad.cpp')
main=read('headless/main.cpp')
generated=read('headless/encore_overrides_generated.h')

# One TV shell everywhere.
assert 'void Launcher::draw_top_nav' in launcher
for call in ('draw_top_nav(c, 0','draw_top_nav(c, 1','draw_top_nav(c, 3'):
    assert call in home+library+settings, call
assert 'Persistent section state' in launcher

# Home composition and controller-first navigation.
assert 'kHomeRecentMax = 6' in home
assert 'kHomeQuickPanel' in home
assert 'focus == kHomeQuickPanel' in home
assert 'Open quick settings' in home
assert 'Deliberately inert: the user must press Cross to enter the quick-settings block.' in home
assert 'home_quick_edit_' in home and 'Pad::cross, TR("Edit")' in home
assert 'VIEW ALL GAMES' not in home
assert 'View all games' not in home
assert 'const Rect hero{72.0f, 164.0f, 1228.0f, 514.0f}' in home
assert 'const Rect quick{1324.0f, 164.0f, 524.0f, 286.0f}' in home
assert 'const Rect status{1324.0f, 470.0f, 524.0f, 454.0f}' in home
assert 'kHomeStorage' in home and 'kHomeCache' in home
assert 'Confirmation::shader_caches' in home and 'clear_shader_caches' in home
assert 'Cross to clear' in home
assert 'AssetsDir()' in services
assert 'std::filesystem::space(storage_root' in services

# Cards: gameplay media first and no ugly language subtitle under recent titles.
assert 'recent.screenshot' in home
recent_block=home[home.index('// ---- recently played ----'):home.index('// ---- footer ----')]
assert 'recent.language' not in recent_block
assert 'const int shown = std::min<int>(6' in recent_block
assert 'card_w = (available - gap * 5.0f) / 6.0f' in recent_block

# Library/Settings are horizontal TV surfaces, not legacy utility lists.
assert 'horizontal TV-first game rail' in library
assert 'library_.move(key == Key::right ? 1 : -1)' in library
press_library=library[library.index('void Launcher::press_library'):library.index('void Launcher::draw_library')]
assert 'set_docked' not in press_library
assert 'game->screenshots' in library
assert 'category rail: one row, controller-first' in settings
assert browse.count('draw_top_nav(c, 3)') >= 3
assert 'draw_frame(c' not in browse
assert '1080p is recommended for stability and memory' not in settings
assert 'Game render scale. 1x is recommended' not in settings
assert 'PlayStation uses Cross=A and Circle=B' not in settings
assert '1x is the safe default' not in library

# Face button visuals: PS-style primitives and coloured symbols.
for name in ('cross','circle','square','triangle','dpad','l1','r1','l2','r2','l3','r3','options','create','touchpad'):
    assert f'Pad::{name}' in widgets_h or name in widgets_h, name
assert 'face_ink' in widgets
for rgb in ('0x55b7ff','0xff6b8a','0xe987ff','0x66e6a6'):
    assert rgb in widgets, rgb
assert 'physical_pad_icon' in mapping and 'draw_pad(c, icon' in mapping

# Micro-DA: glass depth, double edge, focus bloom, active-vs-focus differentiation.
for marker in ('Two-layer elevation','Inner hairline','Console-style focus','kFocusCore','kFocusBlue'):
    assert marker in widgets+read('headless/prosperoeden/pe/ui/theme.hpp'), marker

# Nlib rich media: icon + banner + screenshots + metadata.
for marker in ('/banner/1080p','/screen/','/icon/512','fields=name,intro,description,publisher,developer,releaseDate',
               'CachedNlibScreens','result.screenshots','result.hero'):
    assert marker in services, marker
assert 'hero_intro' in home
assert 'kNlibCacheSchema = 2' in services
assert 'current_metadata_cache' in services
assert 'artwork_files.resize(6)' in services
assert 'game->screenshots' in library

# Global PlayStation Auto control contract.
assert 'kPlayStationAutoControls' in generated
assert 'SetAdaptivePlayStation(bool enabled)' in devices
assert 'mapping_context == MappingContext::gameplay ? kSwitchMapping : mapping' in pad
assert 'EDEN_PAD_CONTEXT mode=gameplay' in pad and 'EDEN_PAD_CONTEXT mode=ui' in pad
assert 'pad->SetAdaptivePlayStation(effective_layout == 0 && !custom_mapping);' in main
assert '"PlayStation Auto"' in main

# Four authored performance tiers + derived Custom.
for label in ('"Minimum"','"Recommended"','"High"','"Ultra"','"Custom"'):
    assert label in store
assert 'kAuthoredVideoProfiles = Eden::EncoreOverrides::kAuthoredProfileCount' in presets
assert 'VideoPresetForTitle' in presets


# Final Home polish contracts: full-bleed banner, explicit teal values, DualSense capacity, exact baseline.
assert 'const Rect hero_art{hero.x + 4.0f, hero.y + 4.0f, hero.w - 8.0f, hero.h - 8.0f}' in home
assert 'kAccentTeal' in read('headless/prosperoeden/pe/ui/theme.hpp')
assert 'tr("DualSense")' in home and 'std::to_string(hero_max_players)' in home
assert 'hero.x + hero.w - 192.0f, 606.0f, 156.0f, 34.0f' in home
assert 'gfx::mix(theme::kAccentTeal, theme::kTitle, f)' in home
assert 'constexpr float card_h = 174.0f' in home
assert '750.0f, card_w, card_h' in home
assert 'const Rect status{1324.0f, 470.0f, 524.0f, 454.0f}' in home

print('Encore UX/media/profile contracts: PASS')
