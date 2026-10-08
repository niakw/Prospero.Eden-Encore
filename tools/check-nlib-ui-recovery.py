#!/usr/bin/env python3
from pathlib import Path
root = Path(__file__).resolve().parents[1]
def src(name): return (root / name).read_text()
svc = src("headless/prosperoeden/eden_services.cpp")
lib = src("headless/prosperoeden/pe/ui/library.cpp")
home = src("headless/prosperoeden/pe/ui/home.cpp")
hdr = src("headless/prosperoeden/pe/ui/launcher.hpp")
nav = src("headless/prosperoeden/pe/ui/launcher.cpp")
assert "bool ValidNlibTga(" in svc
assert "if (!ValidNlibTga(path))" in svc
assert "const bool sparse_metadata = current_metadata_cache" in svc
assert "metadata_expired || sparse_metadata" in svc
assert 'metadata["_encore_checked_at"] = now_seconds' in svc
assert "refresh_existing_artwork" in svc
assert "CachedNlibHero(title_id).empty()" in svc
assert "game.artwork_changed = enrichment.artwork_changed" in svc
assert "textures_.invalidate(enriched.hero)" in lib
assert "void Textures::invalidate(" in src("headless/prosperoeden/pe/ui/textures.cpp")
assert "EDEN_NLIB_ASSETS title_id=" in svc
assert "home_media_next_retry_" in hdr and "media_next_retry_" in hdr
assert "media_retry_timer_ >= 8.0f" in nav
assert "!game.cover.empty() ? game.cover : game.hero" in lib
assert "if (image.missing) continue;" in lib
assert "Loading artwork" in home and "Artwork unavailable" in home
assert "text_block(c, title_label" in home
assert "text_block(c, hero_caption" in home
assert "label_area.w - 4.0f, Align::center" in home
assert 'TR("Recent")' in nav
# Regression from FC27 hardware tests: use the matching game's proper Nlib
# description before a short marketing intro after returning to the Hero.
# Genuinely missing-ROM/language warnings remain higher priority.
hero_types = src("headless/prosperoeden/pe/ui/services.hpp")
assert "std::string last_description;" in hero_types
assert "std::string description; // detailed, title-keyed Nlib text for the Hero" in hero_types
assert "home.last_description = nlib.description;" in svc
assert "recent.description = nlib.description;" in svc
assert "home_.last_description = enriched.description;" in lib
assert "recent.description = enriched.description;" in lib
assert "home_.last_description = game.description;" in lib
assert "const std::string &hero_description =" in home
assert "!hero_description.empty() ? hero_description :" in home
assert "hero_caption_warning ? home_.last_caption :" in home
# Never decompress or resize Nlib artwork inside the frame update.
texture_h = src("headless/prosperoeden/pe/ui/textures.hpp")
texture_cpp = src("headless/prosperoeden/pe/ui/textures.cpp")
assert "std::future<DecodedCover> decode_;" in texture_h
assert "decoded.ok = services_.load_image(path, &decoded.image);" in texture_cpp
assert "decode_ = std::async(std::launch::async" in texture_cpp
assert "it->second.generation == result.generation" in texture_cpp
assert "entry.texture = create(result.image);" in texture_cpp
assert "decode_.wait_for(std::chrono::seconds(0))" in texture_cpp
# A rare native frame overrun gets one bounded phase label (no noisy per-frame
# printf) so the next PS5 test can tell GPU texture upload, cache/media merge,
# and 2-second game-presence file I/O apart.
assert "EDEN_UI_HOTSPOT phase=%s elapsed_ms=%lld" in nav
assert 'slow_stage("texture_upload", update_stage_begin);' in nav
assert 'slow_stage("media_merge", media_started);' in nav
assert 'slow_stage("game_presence_scan", presence_started);' in nav
assert "now - last_ui_hotspot_report_ >= std::chrono::seconds(2)" in nav

# Presence checks may run every two seconds, but normal PS5 UI navigation
# must not synchronously stat the entire game library.
assert "std::future<std::vector<std::string>> presence_scan_;" in hdr
assert "presence_scan_.wait_for(std::chrono::seconds(0))" in lib
assert "presence_scan_ = std::async(std::launch::async" in lib
assert "if (!services_.game_exists(path))" in lib
# Library navigation must not wait for a full scan or stat every game on the UI thread.
library_entry = lib.split("void Launcher::enter_library()", 1)[1].split("bool Launcher::open_game_settings_at_file", 1)[0]
assert "finish_scan(false);" in library_entry
assert "finish_scan(true);" not in library_entry
assert "drop_missing_games();" not in library_entry
assert "start_scan();" in library_entry
assert "library_.selected >= 0 &&" in lib
# Per-title mod directories/config are resolved on the scan worker, not
# synchronously when finish_scan() updates the visible Library.
scan_entry = lib.split("void Launcher::start_scan()", 1)[1].split("void Launcher::finish_scan(", 1)[0]
apply_entry = lib.split("void Launcher::apply_games(", 1)[1].split("void Launcher::name_home_games()", 1)[0]
assert "std::vector<Game> games = services_.games();" in scan_entry
assert "services_.mods(game.title_id)" in scan_entry
assert "services_.mods_enabled(game.title_id)" in scan_entry
assert "services_.mods(game.title_id)" not in apply_entry
assert "home_.last_mods = game.mods;" in lib
assert "home_.last_mods_on = game.mods_on;" in lib

assert "if (presence_scan_.valid())" in nav
assert "drop_missing_games(&missing);" in lib
assert "if (known_missing)" in lib
assert "bool drop_missing_games(const std::vector<std::string>* known_missing = nullptr);" in hdr

print("Nlib and four PS5 capture regressions: SOURCE CONTRACT PASS")
