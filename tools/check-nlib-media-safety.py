#!/usr/bin/env python3
"""Nlib assets: complete eager title enrichment with bounded decode memory.

Static source gate complements real host-render checks. Title fetching stays
asynchronous to avoid freezing the launcher, but ALL screenshots are scheduled
with the banner/icon, for every installed game.
"""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
services = (root / "headless/prosperoeden/eden_services.cpp").read_text()
library = (root / "headless/prosperoeden/pe/ui/library.cpp").read_text()
source = services[services.index("bool WriteJpegTga("):services.index("std::string NlibPlayersPath(")]
assert "stbi_info_from_memory" in source
assert source.index("stbi_info_from_memory") < source.index("stbi_load_from_memory")
assert "encoded.size() > (16u << 20)" in source
assert "width > 4096 || height > 2160" in source
assert "3840u * 2160u" in source
section = services[services.index("NlibEnrichment EnsureNlibEnrichment("):
                   services.index("std::uintmax_t TreeBytes(")]
assert "std::vector<std::future<bool>> downloads;" in section
assert "std::async(std::launch::async" in section
assert "const int wanted_screens = std::clamp(screen_count, 0, 3);" in section
assert "/banner/1080p" in section and "/icon/512" in section and "/screen/" in section
assert "for (auto& pending : downloads)" in section
assert "CachedNlibEnrichment(title_id, language_choice)" in section
assert "home_priority" not in section
assert "for (std::size_t offset = 0; offset < games_.size(); ++offset)" in library
print("Nlib all-game full-media concurrency + bounded JPEG decode memory: PASS")
