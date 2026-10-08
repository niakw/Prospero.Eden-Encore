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
# Nlib media must be scaled on the decode worker to the dimensions the
# launcher actually draws. Otherwise every 300px card uploads a 1080p image.
assert "int target_pixels = 64;" in texture_cpp
assert "target_pixels *= 2;" in texture_cpp
assert "path + '#' + std::to_string(target_pixels)" in texture_cpp
assert "entry.target_pixels = target_pixels;" in texture_cpp
assert "const int target_pixels = it->second.target_pixels;" in texture_cpp
assert "std::max(decoded.image.width, decoded.image.height) >" in texture_cpp
assert "target_pixels * 3 / 2" in texture_cpp
assert "decoded.image = gfx::halve(decoded.image);" in texture_cpp
assert "int target_pixels = 64;" in texture_h
assert "kMaxTextureReclaimsPerFrame = 2" in texture_cpp
assert "reclaimed < kMaxTextureReclaimsPerFrame" in texture_cpp

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
# Home Triangle game options can be requested before the first background
# library scan returns: defer it rather than blocking the UI for a full scan.
settings_entry = lib.split("bool Launcher::open_game_settings_at_file(", 1)[1].split(
    "void Launcher::refresh_selected_game()", 1)[0]
assert "finish_scan(false);" in settings_entry
assert "finish_scan(true);" not in settings_entry
assert "pending_settings_file_ = file;" in settings_entry
assert "std::string pending_settings_file_;" in hdr
# Home recent cards and quick-setting saves reuse a per-title settings
# snapshot; editing settings in another screen invalidates that snapshot.
assert "home_settings_cache_;" in hdr
assert "home_settings_cache_.find(title_id)" in home
assert "home_settings_cache_.emplace(title_id," in home
assert "home_settings_cache_[title_id] = {home_game_settings_, home_game_docked_};" in home
assert "home_settings_cache_.clear();" in nav
assert "const bool game_settings_closed = modal_ == Modal::game;" in nav

assert "const std::string file = std::move(pending_settings_file_);" in nav
assert "if (games_loaded_ && !pending_settings_file_.empty())" in nav
assert "pending_settings_file_.clear();" in nav
assert "(void)open_game_settings_at_file(file);" in nav

assert "drop_missing_games();" not in library_entry
assert "start_scan();" in library_entry
assert "library_.selected >= 0 &&" in lib
# Per-title mod directories/config are resolved on the scan worker, not
# synchronously when finish_scan() updates the visible Library.
scan_entry = lib.split("void Launcher::start_scan()", 1)[1].split("void Launcher::finish_scan(", 1)[0]
apply_entry = lib.split("void Launcher::apply_games(", 1)[1].split("void Launcher::name_home_games()", 1)[0]
assert "std::vector<Game> games = services_.games(&scan_cancel_);" in scan_entry
assert "services_.mods(game.title_id)" in scan_entry
assert "services_.mods_enabled(game.title_id)" in scan_entry
assert "catch (const std::bad_alloc&)" in scan_entry
assert "catch (const std::exception& error)" in scan_entry
assert "if (mod_scan_errors++ < 3)" in scan_entry
# Obsolete scans must stop enumerating optional per-game mod folders
# when the user launches a game. Do not asynchronously kill a thread.
assert "std::atomic<bool> scan_cancel_{false};" in hdr
assert "scan_cancel_.load(std::memory_order_acquire)" in scan_entry
assert "if (scan_cancel_.load(std::memory_order_acquire)) break;" in scan_entry
assert "if (!scan_cancel_.load(std::memory_order_acquire))" in lib
assert "scan_cancel_.store(true, std::memory_order_release);" in nav
# Native game enumeration must itself honor cancellation between ROMs,
# not merely skip the follow-up mod scan in the Launcher wrapper.
native_svc = src("headless/prosperoeden/eden_services.cpp")
native_hdr = src("headless/prosperoeden/eden_services.h")
assert "virtual std::vector<Game> games(const std::atomic<bool>* cancel)" in hero_types
assert "games(const std::atomic<bool>* cancel) override;" in native_hdr
assert "EdenServices::games(const std::atomic<bool>* cancel)" in native_svc
native_scan = native_svc.split(
    "EdenServices::games(const std::atomic<bool>* cancel)", 1)[1].split(
    "EdenServices::enrich_game_media", 1)[0]
assert "cancel && cancel->load(std::memory_order_acquire)" in native_scan
assert "return {}; // discard partial results and stop per-title disk work" in native_scan
assert "return {}; // extraction finished; skip ID/Nlib/add-on metadata" in native_scan

assert "auto games = scan_.get();" in lib
# A failed first scan must not become a valid empty list. Otherwise the
# delayed Home settings action reports a nonexistent missing ROM.
finish_entry = lib.split("void Launcher::finish_scan(", 1)[1].split(
    "void Launcher::start_home_media()", 1)[0]
assert "games_loaded_ = true;" not in finish_entry
assert "if (!games_loaded_ && !pending_settings_file_.empty())" in finish_entry
assert "pending_settings_file_.clear();" in finish_entry

assert "apply_games(std::move(games));" in lib

assert "#include <new>" in lib
assert "services_.mods(game.title_id)" not in apply_entry
assert "home_.last_mods = game.mods;" in lib
assert "home_.last_mods_on = game.mods_on;" in lib
# Preserve UI responsiveness without pruning a ROM based on one stale
# asynchronous filesystem snapshot (e.g. an atomic replacement during scan).
assert "std::vector<std::string> previous_missing_;" in hdr
assert "std::set_intersection(observed_missing.begin()" in lib
assert "previous_missing_ = observed_missing;" in lib
assert 'previous_missing_.clear();' in lib
assert "#include <iterator>" in lib
def stable_absence(previous, observed):
    return sorted(set(previous) & set(observed))
assert stable_absence([], ["game.nsp"]) == []
assert stable_absence(["game.nsp"], []) == []
assert stable_absence(["game.nsp"], ["game.nsp"]) == ["game.nsp"]


assert "if (presence_scan_.valid())" in nav
assert "drop_missing_games(&missing);" in lib
assert "if (known_missing)" in lib
assert "bool drop_missing_games(const std::vector<std::string>* known_missing = nullptr);" in hdr

print("Nlib and four PS5 capture regressions: SOURCE CONTRACT PASS")
