#!/usr/bin/env python3
"""Fetch existing physical retail scans for a host-only OpenGL visual fixture.

Not bundled with the emulator or committed to the repository. All screenshots
are rendered by the real launcher C++/GL pipeline, never an image generator.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
from pathlib import Path
import urllib.request

from PIL import Image

# GameFAQs original EU box scan first; LaunchBox serves a smaller public
# thumbnail on some CDN routes and is an explicitly lower-resolution fallback.
# None of these files are committed, bundled or used by the native executable.
MEDIA = {
    "botw-front.tga": (
        # Original 1447x2343 press-cover asset; do not use a thumbnail when
        # this source is reachable. The cover remains a host-only test fixture.
        "https://cdn.wikimg.net/en/zeldawiki/images/c/c7/BotW_NA_Switch_Box_Art.png",
        "https://gamefaqs.gamespot.com/a/box/6/6/4/599664_front.jpg",
        "https://images.launchbox-app.com/a8bcb4cc-a3b0-4cf0-82f3-cb10dd18b27c.jpg",
    ),
    "botw-spine.tga": (
        "https://images.launchbox-app.com/61b12a95-c917-42ff-9c25-b265732204fe.jpg",
    ),
    "botw-back.tga": (
        # User-identified alternate actual Box - Back scan. Compare decoded
        # ORIGINAL pixels, not the LaunchBox page's advertised dimensions.
        "https://images.launchbox-app.com/4b815db4-d2d1-4587-89c7-f82524750914.jpg",
        "https://gamefaqs.gamespot.com/a/box/6/6/4/599664_back.jpg",
        "https://images.launchbox-app.com/b5f2899a-717f-4544-b63f-ee5d13e24483.jpg",
    ),
    "botw-hero.tga": (
        # Existing 2560x1440 downloadable desktop wallpaper from Nintendo.
        # Host-only art fixture; native Encore still uses its cached Nlib Hero.
        "https://www.nintendo.com/eu/media/images/08_content_images/games_6/nintendo_switch_7/nswitch_thelegendofzeldabreathofthewild/NSwitch_TheLegendOfZeldaBreathOfTheWild_wp_desktop_01.jpg",
        "https://images.launchbox-app.com/9ec55095-ae9a-4da6-b1a4-025dfe92ca4b.jpg",
    ),
}


def download(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    receipts = []
    for filename, candidates in MEDIA.items():
        selected = None
        errors = []
        for url in candidates:
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0 (EdenEncore Preview; host)"})
                with urllib.request.urlopen(request, timeout=35) as response:
                    body = response.read(12 * 1024 * 1024 + 1)
                if len(body) > 12 * 1024 * 1024:
                    raise ValueError("image too large")
                with Image.open(BytesIO(body)) as source_image:
                    source_image.load()
                    if (source_image.width < (12 if filename == "botw-spine.tga" else 150) or
                            source_image.height < 210):
                        raise ValueError(f"image is not a usable scan: {source_image.size}")
                    if source_image.width * source_image.height > 12_000_000:
                        raise ValueError("pixel budget exceeded")
                    image = source_image.convert("RGB")
                # Never accept the first file just because it responds.
                # Comparing native pixel counts prevents low-res previews
                # from superseding clearer scans of the same physical side.
                score = image.width * image.height
                if selected is None or score > selected[3]:
                    selected = (url, body, image, score)
            except Exception as error:
                errors.append(f"{url}: {error}")
        if selected is None:
            raise RuntimeError(f"No usable source for {filename}: " + "; ".join(errors))
        url, body, image, score = selected
        original = image.size
        if filename == "botw-spine.tga" and (image.width < 64 or image.height < 600):
            # LaunchBox's tiny 18x281 preview cannot display crisp printed
            # letters. Exercise the production blank-red-side fallback.
            print(f"{filename}: no legible original ({original[0]}x{original[1]}), using clean empty spine")
            continue
        image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
        # This is deliberately not upscaled: a 18px-wide "Box - Spine"
        # thumbnail cannot become legible ink by enlarging the pixels.
        image.save(destination / filename, format="TGA")
        receipts.append(
            f"{filename}\\t{url}\\tsha256:{hashlib.sha256(body).hexdigest()}\\t"
            f"source={original[0]}x{original[1]}\\n")
        print(f"{filename} from {url} native size={original[0]}x{original[1]}")
    (destination / "source-receipts.txt").write_text("".join(receipts))
    print("HOST_RETAIL_SCANS: fetched 2 physical faces and 1 game background")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("directory", type=Path)
    args = cli.parse_args()
    download(args.directory)
