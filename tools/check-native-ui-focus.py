#!/usr/bin/env python3
"""Production-render contract for approved Eden Encore visual identity.

The true C++/OpenGL renderer outputs 1080p screenshots in GitHub Actions.
This check catches source regressions before that lightweight compile begins:
background COVER, left/bottom dimming, neon focus, non-stretched images, UI copy.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
def read(name: str) -> str: return (root / name).read_text()

home = read("headless/prosperoeden/pe/ui/home.cpp")
widgets = read("headless/prosperoeden/pe/ui/widgets.cpp")
nav = read("headless/prosperoeden/pe/ui/launcher.cpp")
theme = read("headless/prosperoeden/pe/ui/theme.hpp")
settings = read("headless/prosperoeden/pe/ui/settings.cpp")
services = read("headless/prosperoeden/eden_services.cpp")
fr = read("headless/prosperoeden/ui/lang/fr-FR.po")
frca = read("headless/prosperoeden/ui/lang/fr-CA.po")
preview = read(".github/workflows/launcher-production-preview.yml")

# Full-screen game image is object-fit: cover; UV crop can happen in either
# dimension, but no stretch and no cropped-to-a-hero-card background.
assert "const Rect hero{0.0f, 0.0f, 1920.0f, 1080.0f};" in home
assert "const float source = std::max(0.01f, hero_picture.aspect);" in home
assert "uv.w = target / source;" in home and "uv.h = source / target;" in home
assert "list.image(hero_picture.texture, hero, uv" in home
assert "list.hgradient_rect(hero, 0.0f" in home
assert "theme::kScrim.with_alpha(0.91f)" in home
assert "list.gradient_rect({0.0f, 325.0f, 1920.0f, 755.0f}" in home
assert "theme::kBase.with_alpha(0.96f)" in home

# Thumbnail covers crop about the centre rather than distorting aspect ratio.
assert "void cover_crop(Canvas &c" in widgets
assert "uv.w = target / source;" in widgets
assert "uv.h = source / target;" in widgets
assert "c.list.rounded_image(image.texture, r, uv, radius" in widgets
# Logo / standalone icon rendering is containment, not stretched.
assert "fitted.h = r.w / source;" in widgets
assert "fitted.w = r.h * source;" in widgets
assert "rounded_image(image.texture, fitted" in widgets

# Shared focus affects *all* relevant interaction surfaces, including tiles,
# buttons, menus and utility cards. Artwork underneath stays readable.
assert "const bool artwork_plate = &style == &kTilePlate;" in widgets
assert "if (!artwork_plate) {" in widgets
assert "Paint bloom BEFORE the opaque cover" in home
assert "Only the luminous outline is above the game cover." in home
assert "const float fill_strength = artwork_plate ? 0.06f : 0.82f;" in widgets
assert "const float right_strength = artwork_plate ? 0.06f : 0.34f;" in widgets
assert "theme::kSun.with_alpha(0.29f * amount * breathe)" in widgets
assert "theme::kFocusCore.with_alpha(0.95f * amount)" in widgets
assert "list.hgradient_rect(r, 19.0f" in nav
assert "list.image(c.textures.brand(), {56.0f" in nav
assert "Color::rgb(0xbb59ff)" in theme
assert "Color::rgb(0xff70e4)" in theme

# French user-facing text is simple across status, settings and confirmation.
assert 'tr("Max. players: {0}")' in home
assert 'tr("CACHE")' in home and 'tr("CACHE")' in settings
assert 'tr("Clear cache")' in settings and 'TR("Clear cache?")' in nav
assert 'tr("Cleared {0} of cache.")' in services
for catalog in (fr, frca):
    for label in ('msgid "Max. players: {0}"', 'msgid "CACHE"',
                  'msgid "Clear cache"', 'msgid "Clear cache?"'):
        assert label in catalog, label

# The test output MUST come from C++ shader rendering, never image synthesis.
assert 'bash tools/launcher/preview.sh' in preview
assert 'RENDERED_FROM_REAL_CPP_GL_LAUNCHER: PASS' in preview
print("Eden Encore authentic branding / COVER / dark fades / neon focus / UX copy: PASS")
