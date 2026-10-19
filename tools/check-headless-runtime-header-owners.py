#!/usr/bin/env python3
"""Prove exact application-runtime header owners without moving them to Encore.

Static consumer/include and source invariants; not a hardware qualification.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADLESS = ROOT / "headless"

owners = [
    {
        "id": "U34",
        "header": "boot_trace.h",
        "symbols": [
            "inline void Begin(",
            "inline void OnFatal("
        ],
        "consumers": [
            "headless/main.cpp"
        ]
    },
    {
        "id": "U35",
        "header": "filesystem_probe.h",
        "symbols": [
            "inline bool ProbeWritableRoot("
        ],
        "consumers": [
            "headless/main.cpp"
        ]
    },
    {
        "id": "U36",
        "header": "diagnostics.h",
        "symbols": [
            "inline void Report(",
            "inline void ReportStep("
        ],
        "consumers": [
            "headless/main.cpp",
            "headless/graphics.cpp",
            "headless/metadata_bridge.cpp"
        ]
    },
    {
        "id": "U37",
        "header": "log_pipe.h",
        "symbols": [
            "bool Attach(",
            "void Detach()"
        ],
        "consumers": [
            "headless/main.cpp",
            "headless/graphics.cpp"
        ]
    },
    {
        "id": "U38",
        "header": "network_domain_rules.h",
        "symbols": [
            "int eden_network_filter_load(",
            "int eden_network_host_blocked("
        ],
        "consumers": [
            "headless/main.cpp",
            "headless/network_domain_rules.c"
        ]
    },
    {
        "id": "U39",
        "header": "network_audit.h",
        "symbols": [
            "int eden_network_audit_init(",
            "void eden_network_audit_event("
        ],
        "consumers": [
            "headless/main.cpp",
            "headless/network_audit.c",
            "headless/network_audit_sockets.c"
        ]
    },
    {
        "id": "U40",
        "header": "title_id_fallback.h",
        "symbols": [
            "TitleIdFromRomFilename(",
            "ResolveGameTitleId("
        ],
        "consumers": [
            "headless/main.cpp"
        ]
    },
    {
        "id": "U41",
        "header": "native_directory.h",
        "symbols": [
            "ReadNativeDirectory("
        ],
        "consumers": [
            "headless/main.cpp",
            "headless/metadata_bridge.cpp"
        ]
    },
    {
        "id": "U42",
        "header": "present_interval_witness.h",
        "symbols": [
            "struct PresentIntervalWitness",
            "void Observe("
        ],
        "consumers": [
            "headless/graphics.cpp"
        ]
    },
    {
        "id": "U43",
        "header": "direct_pool_probe_policy.h",
        "symbols": [
            "ProbeIntervalNs("
        ],
        "consumers": [
            "headless/performance.cpp"
        ]
    },
    {
        "id": "U44",
        "header": "direct_pool_region_scan.h",
        "symbols": [
            "struct RegionScan",
            "FreeUpperBound("
        ],
        "consumers": [
            "headless/performance.cpp"
        ]
    },
    {
        "id": "U45",
        "header": "dev_replay_policy.h",
        "symbols": [
            "ReplayRequestedAfter(",
            "ScriptedReplayEnabled("
        ],
        "consumers": [
            "headless/main.cpp"
        ]
    }
]
assert len(owners) == 12
for record in owners:
    name = record["header"]
    owner = HEADLESS / name
    assert owner.is_file(), name
    source = owner.read_text(encoding="utf-8")
    for symbol in record["symbols"]:
        assert symbol in source, (name, "missing function/contract", symbol)
    include = '#include "' + name + '"'
    for target in record["consumers"]:
        implementation = ROOT / target
        assert implementation.is_file(), target
        assert include in implementation.read_text(encoding="utf-8"), (
            name, "direct consumer missing", target)
# Runtime policy checks prevent catalog-only ownership with a weakened API.
assert "S_ISLNK(info.st_mode)" in (HEADLESS/"filesystem_probe.h").read_text()
assert "%.900s" in (HEADLESS/"diagnostics.h").read_text()
assert "std::thread worker;" in (HEADLESS/"log_pipe.h").read_text()
assert "std::vector<char> buffer(65536);" in (HEADLESS/"native_directory.h").read_text()
assert "close - open != 17" in (HEADLESS/"title_id_fallback.h").read_text()
assert "kProbeHighHeadroomBytes = 4ULL << 30" in (HEADLESS/"direct_pool_probe_policy.h").read_text()
assert "constexpr bool Include(" in (HEADLESS/"direct_pool_region_scan.h").read_text()
assert "return requested && title_id == profile_title_id;" in (HEADLESS/"dev_replay_policy.h").read_text()
assert "void OnFatal(" in (HEADLESS/"boot_trace.h").read_text()
# This is application-owned runtime policy, not an upstream vendor patch.
for record in owners:
    assert record["header"] not in ("gpu_probe.inc", "gpu_native_probe.inc")
print("ENCORE_HEADLESS_RUNTIME_HEADER_OWNERS_PASS",
      "headers=12", "direct_consumers=" + str(sum(len(x["consumers"]) for x in owners)),
      "vendor_override_sources=0", "native_runtime_unqualified=1")
