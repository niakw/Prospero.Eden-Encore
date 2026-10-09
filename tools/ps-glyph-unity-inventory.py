#!/usr/bin/env python3
"""Read-only Unity Texture2D/Sprite name, dimensions and serialized rect inventory.

Requires an explicitly supplied, local authorized Unity assets file and
optional dependency UnityPy (install separately if needed).
Nothing is extracted, patched, repacked or redistributed. Serialized Sprite
m_Rect / m_RD.textureRect may expose real engine-side UI texture coordinates,
but their origin, sprite packing/rotation, name semantics, atlas asset identity,
game build and correct Switch prompt mapping need independent verification.

Supports newer UnityPy parse_as_object()/peek_name(), and older read() where
available. This is an offline *candidate* discovery stage, NOT an emulator hook.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

MAX_INPUT_BYTES = 512 * 1024 * 1024
MAX_OBJECTS = 50000
MAX_REPORTED = 12000
MAX_NAME = 256
HINTS = ("button", "buttons", "btn", "gamepad", "controller", "prompt", "key",
         "glyph", "dpad", "xbox", "playstation", "dualshock", "dualsense",
         "ps4", "ps5", "switch", "joycon", "hud", "input", "touchpad", "sprite")


def safe_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    result = "".join(c for c in value if c.isprintable()).strip()
    return result[:MAX_NAME] if result else None


def field(obj: object, key: str):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def sprite_rect(obj: object) -> list[float] | None:
    """Read original serialized Unity Rectf, without converting coordinate origin."""
    if obj is None:
        return None
    values = [field(obj, key) for key in ("x", "y", "width", "height")]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        return None
    x, y, width, height = values
    if x < -1000000 or y < -1000000 or width <= 0 or height <= 0 or \
            max(width, height) > 32768:
        return None
    return [float(x), float(y), float(width), float(height)]


def get_name(obj: object) -> str | None:
    if callable(getattr(obj, "peek_name", None)):
        try:
            return safe_string(obj.peek_name())
        except (ValueError, RuntimeError, AttributeError, TypeError):
            pass
    return None


def parse_object(obj: object):
    if callable(getattr(obj, "parse_as_object", None)):
        return obj.parse_as_object()
    if callable(getattr(obj, "read", None)):
        return obj.read()
    raise ValueError("unrecognized UnityPy ObjectReader API")


def digest(file: Path) -> str:
    h = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inspect(asset: Path, source_platform: str = "unverified") -> dict:
    if (not asset.is_file() or asset.is_symlink() or
            not 1 <= asset.stat().st_size <= MAX_INPUT_BYTES):
        raise ValueError("Unity assets file missing, linked or oversized")
    if not isinstance(source_platform, str) or not re.fullmatch(r"[A-Za-z0-9_ +./-]{1,80}", source_platform):
        raise ValueError("invalid source platform label")
    try:
        import UnityPy
    except ImportError as error:
        raise ValueError("UnityPy not installed; inspect its setup/license before installing separately") from error
    try:
        env = UnityPy.load(str(asset))
    except Exception as error:
        raise ValueError("UnityPy could not open the selected asset file") from error
    records = []
    count = 0
    truncated = False
    for obj in env.objects:
        count += 1
        if count > MAX_OBJECTS:
            raise ValueError("too many Unity serialized objects")
        try:
            kind = obj.type.name
        except (AttributeError, ValueError):
            continue
        if kind not in ("Texture2D", "Sprite"):
            continue
        name = get_name(obj)
        if name is None:
            try:
                data = parse_object(obj)
                name = safe_string(field(data, "m_Name") or field(data, "name"))
            except (ValueError, RuntimeError, TypeError, AttributeError):
                continue
        if not name:
            continue
        if len(records) >= MAX_REPORTED:
            truncated = True
            break
        likely = any(hint in name.casefold() for hint in HINTS)
        record = {
            "object_type": kind,
            "name": name,
            "path_id": getattr(obj, "path_id", None),
            "possible_ui_glyph": likely,
            "texture_dimensions": None,
            "serialized_sprite_rect": None,
            "serialized_texture_rect": None,
            "texture_pixel_data_sha256": None,
            "sprite_button_identity_verified": False,
        }
        # Reading only likely UI assets avoids parsing thousands of huge
        # unrelated objects; asset pixel decoding is never requested.
        if likely:
            try:
                data = parse_object(obj)
                if kind == "Texture2D":
                    width = field(data, "m_Width")
                    height = field(data, "m_Height")
                    if type(width) is int and type(height) is int and \
                            0 < width <= 16384 and 0 < height <= 16384:
                        record["texture_dimensions"] = [width, height]
                else:
                    record["serialized_sprite_rect"] = sprite_rect(field(data, "m_Rect"))
                    render_data = field(data, "m_RD")
                    if render_data is not None:
                        record["serialized_texture_rect"] = sprite_rect(
                            field(render_data, "textureRect") or
                            field(render_data, "m_TextureRect"))
            except (ValueError, RuntimeError, TypeError, AttributeError):
                record["parse_status"] = "metadata_unavailable"
        records.append(record)
    return {
        "schema": 1,
        "source": "unity_serialized_asset_metadata",
        "container_filename": asset.name,
        "container_sha256": digest(asset),
        "source_platform_declared": source_platform,
        "object_count_seen": count,
        "reported_texture_or_sprite_objects": len(records),
        "record_limit_reached": truncated,
        "objects": records,
        "warning": "Serialized Unity sprite rects are unverified engine metadata with platform-specific origin/packing. No image bytes decoded, no Switch layout or PS5 compatibility established.",
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--asset-file", type=Path, required=True, help="local Unity resources.assets or asset bundle")
    cli.add_argument("--platform", default="unverified", help="user-declared source platform")
    cli.add_argument("--out", type=Path, help="NEW JSON report only")
    args = cli.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("invalid or existing report path")
        data = json.dumps(inspect(args.asset_file, args.platform), indent=2) + "\n"
        if args.out:
            args.out.write_text(data, encoding="utf-8")
            print(f"UNITY UI METADATA {args.out}: read-only")
        else:
            print(data, end="")
        return 0
    except (ValueError, OSError, OverflowError) as error:
        print(f"REJECTED Unity inventory: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
