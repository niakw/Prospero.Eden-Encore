#!/usr/bin/env python3
"""Single-authoritative screenshot contract for Eden Encore Home (1920x1080).

Reference: user-approved 'maquetteunique.png' (Zelda hero / seven covers).
This is a geometry/state preflight, NOT a substitute for PS5 screenshot review.
No synthetic CPU/GPU/RAM/FPS or non-installed game artwork may be fabricated.
"""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
ui = root / "headless/prosperoeden/pe/ui"
home = (ui / "home.cpp").read_text()
nav = (ui / "launcher.cpp").read_text()
controller = (ui / "launcher.hpp").read_text()
theme = (ui / "theme.hpp").read_text()
service = (root / "headless/prosperoeden/eden_services.cpp").read_text()

# One cinematic scene, behind the nav, and no framed right-column dashboard.
assert "const Rect hero{0.0f, 0.0f, 1920.0f, 1080.0f}" in home
assert "const Cover hero_picture = c.textures.cover(hero_artwork, 1920.0f)" in home
assert "list.image(hero_picture.texture, hero, uv" in home
assert "list.gradient_rect(hero, 0.0f" not in home
assert "const Rect quick_sheet{" in home  # overlay only, not permanent
assert "if (quick_open)" in home
assert "const Rect system{" not in home and "const Rect status{" not in home
assert home.index("const Rect hero{") < home.index("draw_top_nav(c, 0, header_focus")

# Seven real recent games maximum, consistently sized for TV.
assert "kHomeRecentMax = 7" in home
assert "std::array<tween::Spring, 23> home_springs_" in controller
assert "if (home.recents.size() == 7) break" in service
assert "const std::string& art = !recent.cover.empty() ? recent.cover" in home
assert "constexpr float available = 1770.0f" in home
assert "constexpr float gap = 16.0f" in home
assert "constexpr float card_h = 214.0f" in home
assert "card_w = (available - gap * 6.0f) / 7.0f" in home
rail_left, rail_width, gap, count = 76, 1770, 16, 7
card_width = (rail_width - gap*(count-1))/count
assert rail_left + (card_width + gap)*(count-1) + card_width <= 1860
rail_top, rail_bottom = 551, 551 + 214
title_baseline_top = rail_bottom + 6
utility_top, utility_bottom = 825, 825 + 96
assert title_baseline_top + 32 < utility_top  # no overlap
assert utility_bottom < 940  # footer begins below utilities
assert "utility_card(3, kHomeFullSettings" in home
assert "list.push_transform(1.65f, r.x + 41.0f, r.y + r.h * 0.5f" in home

# The reference uses a light cyan focus and a smaller 'eden' wordmark.
assert 'text(c, "eden", 145.0f' in nav
assert "theme::kFocusBlue" in nav
assert "Color::rgb(0x12b7ff)" in theme
assert "push_transform(1.0f, cx, cy, 0.0f, 90.0f" not in nav  # no fictitious rotation

# Game's actual resolution/output and real cache data only; do not show 60 FPS
# merely because a 60 Hz output was selected in the renderer.
assert "home_diagnostics_.shader_caches" in home
assert "home_diagnostics_.storage_root" in home
for fabricated in ("CPU 17%", "GPU 28%", "60 FPS", "48.0 GB / 64.0 GB"):
    assert fabricated not in home
assert "hero_file.empty() ? tr(" in home
assert 'if (image.missing && c.textures.brand() != 0)' not in (ui / "widgets.cpp").read_text()
print("Sole Home screenshot geometry + dynamic media contract: PASS")
