#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-extracted launcher console mode precedence: live vs catalog snapshot.

Host-only native C++20 fixture. Does not launch PS5, download upstream, or
perform a native console build.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "headless/prosperoeden/eden_services.cpp").read_text()
start = source.index("namespace {\n// Share the exact override precedence")
end = source.index("bool EdenServices::docked(", start)
helper = source[start:end]
assert "EffectiveDockedMode(" in helper
assert "game.console_mode >= 0" in helper
assert "game.performance_profile >= 0" in helper
assert "global_profile >= 0" in helper
assert "EncoreOverridesRuntime::ProfileForTitle(title_id, tier).docked" in helper

compiler = next((c for c in ("clang++-18", "clang++", "g++") if shutil.which(c)), None)
if not compiler:
    raise SystemExit("C++20 compiler required for native launcher source contract")
prefix = r"""
#include <cassert>
#include <cstdint>
namespace Eden {
struct GameSettings { int console_mode = -1; int performance_profile = -1; };
namespace EncoreOverrides { constexpr int kAuthoredProfileCount = 3; }
namespace EncoreOverridesRuntime {
    struct Profile { bool docked; };
    Profile ProfileForTitle(std::uint64_t title, int tier) {
        assert(title == 0x1020304050607080ull);
        assert(tier >= 0 && tier < EncoreOverrides::kAuthoredProfileCount);
        return {tier != 1};
    }
}
}
"""
tail = r"""
int main() {
    constexpr std::uint64_t id = 0x1020304050607080ull;
    using Eden::GameSettings;
    // Explicit handheld/docked wins over authored or global profile.
    assert(!EffectiveDockedMode(id, GameSettings{0, 2}, 0));
    assert(EffectiveDockedMode(id, GameSettings{1, 1}, 1));
    // Title-authored performance profile wins over global snapshot.
    assert(!EffectiveDockedMode(id, GameSettings{-1, 1}, 2));
    assert(EffectiveDockedMode(id, GameSettings{-1, 2}, 1));
    // Invalid game profile falls through to global; invalid global to docked.
    assert(!EffectiveDockedMode(id, GameSettings{-1, 99}, 1));
    assert(EffectiveDockedMode(id, GameSettings{-1, 99}, 99));
    assert(EffectiveDockedMode(id, GameSettings{-1, -1}, -1));
    assert(EffectiveDockedMode(id, GameSettings{-1, -1}, 0));
}
"""
with tempfile.TemporaryDirectory(prefix="eden-mode-snapshot-") as folder:
    folder = Path(folder)
    src, exe = folder / "mode.cpp", folder / "mode"
    src.write_text(prefix + helper + tail)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("PASS: native library and live settings share explicit/game/global console mode precedence")
print("PS5 firmware test and native build NOT PERFORMED")
