#!/usr/bin/env python3
"""Fail closed if a PS5 development artifact silently reverted to release mode.

This is a build-output verification, not proof that physical PS5 firmware
supports sparse RX/RW aliases, the game runs smoothly, or in-game PS art works.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "build/headless-native/CMakeCache.txt"
FRONTEND = ROOT / "build/headless-native/frontend.json"
REQUIRED = {
    "EDEN_DEV_PROFILE:BOOL": "ON",
    "EDEN_SPARSE_JIT_DEV:BOOL": "ON",
    "EDEN_PS5_VULKAN:BOOL": "ON",
    "EDEN_DEV_VULKAN:BOOL": "ON",
    "EDEN_VULKAN_DRIVER:STRING": "RADV",
    "EDEN_SHARED_JIT:BOOL": "OFF",
    "EDEN_JIT_COMPILE_BATCH:BOOL": "OFF",
}


def audit(app: Path, title_id: str) -> dict:
    if app.resolve() != (ROOT / "build/dev/PPSA99008").resolve():
        raise ValueError("not the isolated test app staging path")
    if not re.fullmatch(r"[0-9a-fA-F]{16}", title_id):
        raise ValueError("invalid requested title ID")
    if not app.is_dir() or not CACHE.is_file() or not FRONTEND.is_file():
        raise ValueError("missing compiled app/receipt")
    profile = {}
    for line in CACHE.read_text("utf-8").splitlines():
        if not line.startswith(("#", "//")) and "=" in line:
            name, value = line.split("=", 1)
            profile[name] = value
    for key, expected in REQUIRED.items():
        if profile.get(key) != expected:
            raise ValueError(f"compiled profile mismatch: {key} wanted {expected}, got {profile.get(key)!r}")
    if profile.get("EDEN_DEV_ROM_ID:STRING", "").upper() != title_id.upper() or \
       profile.get("EDEN_DEV_PROFILE_TITLE:STRING", "").upper() != title_id.upper():
        raise ValueError("test build compiled a different game autoboot ID")
    receipt = json.loads(FRONTEND.read_text("utf-8"))
    if receipt.get("development_backend") != "Vulkan" or \
       receipt.get("vulkan_driver") != "RADV" or \
       receipt.get("hardware_qualified") is not False or \
       receipt.get("development_rom_id", "").upper() != title_id.upper():
        raise ValueError("development frontend receipt mismatch")
    if not (app / "eboot.bin").is_file() or (app / "eboot.bin").stat().st_size < 1048576:
        raise ValueError("missing compiled PS5 executable")
    return {
        "status": "compiled_test_artifact_flags_verified",
        "title_id": title_id.upper(),
        "jit_sparse_compiled": True,
        "dev_frame_diagnostics_compiled": True,
        "native_ps5_execution_verified": False,
        "sparse_alias_probe_result": None,
        "gpu_shader_pixels_verified": False,
        "playstation_game_art_verified": False,
        "shipping_branch_changed": False,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check-all-on-test-binary.py build/dev/PPSA99008 TITLE_ID", file=sys.stderr)
        return 2
    try:
        app = Path(sys.argv[1])
        data = audit(app, sys.argv[2])
        print("EDEN_PS5_TEST_BUILD " + json.dumps(data, sort_keys=True))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(f"EDEN_PS5_TEST_BUILD_REJECTED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
