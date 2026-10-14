#!/usr/bin/env python3
"""Exact pinned service parity plus bounded guest version metadata diagnostic."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
base=(root/"vendor/sources/eden/src/core/hle/service/am/service/application_functions.cpp").read_text()
current=(root/"vendor/encore-active/eden-core/src/core/hle/service/am/service/application_functions.cpp").read_text()
seed="    auto const seed = res.first->raw.seed_for_pseudo_device_id;"
assert base.count(seed)==1
assert current.count("res.first != nullptr ? res.first->raw.seed_for_pseudo_device_id : u64_le{0};")==1
assert 'EDEN_GUEST_TITLE_VERSION title={:016X} metadata={} version={}' in current
assert current.count("last_reported_title.exchange(title_id, std::memory_order_relaxed)") == 1
assert '#ifdef EDEN_GUEST_TITLE_VERSION_DIAG' in current
assert '"unknown"' in current
assert "GetDisplayVersion" in current
cmake=(root/"headless/CMakeLists.txt").read_text()
assert 'list(APPEND core_sources "__DOLLAR__{EDEN_APP_FUNCTION_SOURCE}")'.replace("__DOLLAR__","$") in cmake
assert 'target_compile_definitions(core PRIVATE EDEN_GUEST_TITLE_VERSION_DIAG=1)' in cmake
assert 'write_derived("__DOLLAR__{PORT_BUILD_DIR}/application_functions.cpp"'.replace("__DOLLAR__","$") not in cmake
print("GUEST_TITLE_VERSION_SOURCE_PASS parity=guarded dev-only=1")
