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
print("Nlib and four PS5 capture regressions: SOURCE CONTRACT PASS")
