#!/usr/bin/env python3
"""Check application runtime policy/header consumers without changing launcher code.

This is a static ownership and source-contract test, not console validation.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADLESS = ROOT / "headless"
owners = [
  {
    "id": "U46",
    "header": "assets_dir.h",
    "symbols": [
      "inline std::string ResolveAssetsDir()",
      "inline std::string AssetsPath("
    ],
    "consumers": [
      "headless/main.cpp",
      "headless/graphics.cpp",
      "headless/prosperoeden/frontend.cpp"
    ]
  },
  {
    "id": "U47",
    "header": "audio_out_init.h",
    "symbols": [
      "inline bool AudioOutReady()"
    ],
    "consumers": [
      "headless/audio.cpp",
      "headless/prosperoeden/frontend.cpp"
    ]
  },
  {
    "id": "U48",
    "header": "crash_report.h",
    "symbols": [
      "void Install(",
      "void SetSession("
    ],
    "consumers": [
      "headless/main.cpp",
      "headless/performance.cpp",
      "headless/crash_report.cpp"
    ]
  },
  {
    "id": "U49",
    "header": "crash_trigger.h",
    "symbols": [
      "inline void BadWrite()",
      "inline void DevelopmentRequest("
    ],
    "consumers": [
      "headless/main.cpp",
      "headless/prosperoeden/frontend.cpp"
    ]
  },
  {
    "id": "U50",
    "header": "dev_launch_policy.h",
    "symbols": [
      "struct BootIntent",
      "constexpr bool ShouldAutoboot("
    ],
    "consumers": [
      "headless/main.cpp"
    ]
  },
  {
    "id": "U51",
    "header": "development_input.h",
    "symbols": [
      "struct DevelopmentInput",
      "std::optional<ps5::pad::Data> Sample("
    ],
    "consumers": [
      "headless/main.cpp",
      "headless/prosperoeden/frontend.cpp"
    ]
  },
  {
    "id": "U52",
    "header": "devices.h",
    "symbols": [
      "class PadEngine final",
      "void ResetControllers()"
    ],
    "consumers": [
      "headless/main.cpp",
      "headless/pad.cpp",
      "headless/audio.cpp"
    ]
  },
  {
    "id": "U53",
    "header": "display_refresh.h",
    "symbols": [
      "inline void ResetSkipFrameTracking()",
      "inline bool SkipFrame()"
    ],
    "consumers": [
      "headless/main.cpp",
      "headless/graphics.cpp"
    ]
  },
  {
    "id": "U54",
    "header": "encore_overrides_runtime.h",
    "symbols": [
      "inline bool ParseManifestText(",
      "inline State LoadCachedState()"
    ],
    "consumers": [
      "headless/main.cpp"
    ]
  },
  {
    "id": "U55",
    "header": "encore_performance_policy.h",
    "symbols": [
      "struct Policy",
      "inline constexpr Policy ForTier("
    ],
    "consumers": [
      "headless/main.cpp"
    ]
  },
  {
    "id": "U56",
    "header": "hle_counters.h",
    "symbols": [
      "class HleCounters",
      "void Record("
    ],
    "consumers": [
      "headless/performance.cpp"
    ]
  },
  {
    "id": "U57",
    "header": "hud.h",
    "symbols": [
      "struct HudClock",
      "inline HudSnapshot MakeHudSnapshot("
    ],
    "consumers": [
      "headless/graphics.cpp"
    ]
  }
]

assert len(owners) == 12
assert len({item["header"] for item in owners}) == 12
for entry in owners:
    name = entry["header"]
    source = (HEADLESS / name).read_text(encoding="utf-8")
    assert source.strip(), name
    for symbol in entry["symbols"]:
        assert symbol in source, (name, "missing source contract", symbol)
    include = '#include "' + name + '"'
    for consumer in entry["consumers"]:
        body = (ROOT / consumer).read_text(encoding="utf-8")
        assert include in body, (name, "owner/consumer mismatch", consumer)
assert "std::call_once(once," in (HEADLESS/"audio_out_init.h").read_text()
assert "std::atomic" in (HEADLESS/"crash_report.h").read_text()
assert "std::remove(marker.c_str())" in (HEADLESS/"crash_trigger.h").read_text()
assert "force_launcher" in (HEADLESS/"dev_launch_policy.h").read_text()
assert "static inline std::atomic<std::uint64_t> taken{0};" in (HEADLESS/"development_input.h").read_text()
assert "kPlayers = 10;" in (HEADLESS/"devices.h").read_text()
assert "requested_hz{60}" in (HEADLESS/"display_refresh.h").read_text()
assert "inline bool ParseManifest(" in (HEADLESS/"encore_overrides_runtime.h").read_text()
assert "std::clamp(tier, 0," in (HEADLESS/"encore_performance_policy.h").read_text()
assert "kCapacity = 4096;" in (HEADLESS/"hle_counters.h").read_text()
assert "struct StartupGate" in (HEADLESS/"hud.h").read_text()
print("ENCORE_HEADLESS_APP_POLICY_OWNERS_PASS",
      "headers=12", "direct_consumers=" + str(sum(len(r["consumers"]) for r in owners)),
      "launcher_code_changes=0", "native_runtime_unqualified=1")
