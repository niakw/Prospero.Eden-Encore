#!/usr/bin/env python3
"""Guard exact owners and direct includes for remaining native app/GPU headers.

A source-consumer/contract check only; no native compile, runtime proof,
launcher modification or assumption of actual device execution.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNERS = [
  {
    "id": "U66",
    "header": "button_mapping.h",
    "symbols": [
      "inline constexpr SessionButtonMapping ResolveSessionButtonMapping(",
      "inline ButtonMapping Assign("
    ],
    "consumers": [
      "headless/devices.h",
      "headless/settings_store.h"
    ]
  },
  {
    "id": "U67",
    "header": "game_liveness.h",
    "symbols": [
      "class Probe",
      "Result Observe("
    ],
    "consumers": [
      "headless/stall_watchdog.h"
    ]
  },
  {
    "id": "U68",
    "header": "glyph_sha256.h",
    "symbols": [
      "class Sha256",
      "inline std::optional<std::string> FileSha256("
    ],
    "consumers": [
      "headless/glyph_overrides_runtime.h"
    ]
  },
  {
    "id": "U69",
    "header": "glyph_version.h",
    "symbols": [
      "namespace Eden::GlyphVersion",
      "inline std::string FromNacp("
    ],
    "consumers": [
      "headless/metadata_bridge.cpp"
    ]
  },
  {
    "id": "U70",
    "header": "image_pages.h",
    "symbols": [
      "inline void Mark(",
      "inline bool NeverHeld("
    ],
    "consumers": [
      "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h",
      "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp"
    ]
  },
  {
    "id": "U71",
    "header": "pad_diagnostics.h",
    "symbols": [
      "struct PadEdgeDiagnostics",
      "void Observe("
    ],
    "consumers": [
      "headless/devices.h"
    ]
  },
  {
    "id": "U72",
    "header": "pipeline_trace_registry.h",
    "symbols": [
      "class FirstUseRegistry final",
      "std::size_t Record("
    ],
    "consumers": [
      "vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp"
    ]
  },
  {
    "id": "U73",
    "header": "preferences.h",
    "symbols": [
      "#include \"settings_store.h\""
    ],
    "consumers": [
      "headless/main.cpp",
      "headless/graphics.cpp",
      "headless/audio.cpp"
    ]
  },
  {
    "id": "U74",
    "header": "ps5_guest_system_button_route.h",
    "symbols": [
      "struct GuestSystemButtonRoute",
      "bool Observe("
    ],
    "consumers": [
      "headless/devices.h"
    ]
  },
  {
    "id": "U75",
    "header": "settings_store.h",
    "symbols": [
      "inline Preferences LoadPreferences(",
      "inline bool SavePreferences("
    ],
    "consumers": [
      "headless/preferences.h",
      "headless/assets_dir.h",
      "headless/encore_performance_policy.h"
    ]
  },
  {
    "id": "U76",
    "header": "storage_paths.h",
    "symbols": [
      "inline std::string ConfigDir()",
      "inline std::string ConfigFile("
    ],
    "consumers": [
      "headless/settings_store.h",
      "headless/assets_dir.h",
      "headless/jit_list.h"
    ]
  },
  {
    "id": "U77",
    "header": "vulkan_gc_budget.h",
    "symbols": [
      "constexpr std::uint64_t AfterProjectedEviction(",
      "constexpr std::uint64_t OldestEvictionTick("
    ],
    "consumers": [
      "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h"
    ]
  },
  {
    "id": "U78",
    "header": "vulkan_pool_capacity.h",
    "symbols": [
      "class PoolCapacityLatch",
      "std::uint64_t Observe("
    ],
    "consumers": [
      "vendor/encore-active/eden-vulkan/vulkan_device.cpp"
    ]
  }
]

assert len(OWNERS) == 13
assert len({row["id"] for row in OWNERS}) == len(OWNERS)
for owner in OWNERS:
    body = (ROOT / "headless" / owner["header"]).read_text(encoding="utf-8")
    assert body.strip(), owner["id"]
    for symbol in owner["symbols"]:
        assert symbol in body, (owner["id"], "symbol drift", symbol)
    expected = '#include "' + owner["header"] + '"'
    for path in owner["consumers"]:
        consumer = (ROOT / path).read_text(encoding="utf-8")
        assert expected in consumer, (owner["id"], "direct include missing", path)
# The last unlinked native-app topology helper is not promoted to a
# compiled/runtime owner without a qualified direct consumer.
orphan = (ROOT / "headless/ps5_amd_topology_evidence.h").read_text()
assert "ValidateAmdSmtEvidence(" in orphan
assert "std::uint64_t permitted" in orphan
assert "class FirstUseRegistry final" in (ROOT/"headless/pipeline_trace_registry.h").read_text()
assert "std::mutex mutex_" in (ROOT/"headless/pipeline_trace_registry.h").read_text()
assert "inline bool NeverHeld(" in (ROOT/"headless/image_pages.h").read_text()
print("ENCORE_HEADLESS_FINAL_OWNERS_PASS headers=13 direct_consumers=" +
      str(sum(len(row["consumers"]) for row in OWNERS)) +
      " unresolved_topology=1 native_runtime_unqualified=1")
