#!/usr/bin/env python3
"""Pin KProcess DEV-only teardown timing to the complete maintained TU."""
from pathlib import Path
import json
root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/core/hle/kernel/k_process.cpp").read_text()
active = (root / "vendor/encore-active/eden-core/src/core/hle/kernel/k_process.cpp").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
edits = json.loads(r'''[["void KProcess::Finalize(KernelCore& kernel) {\n    // Delete the process local region.\n    this->DeleteThreadLocalRegion(kernel, m_plr_address);\n","void KProcess::Finalize(KernelCore& kernel) {\n    auto eden_last = std::chrono::steady_clock::now();\n    const auto eden_mark = [&eden_last](const char* step) {\n        const auto now = std::chrono::steady_clock::now();\n        const double ms = std::chrono::duration<double, std::milli>(now - eden_last).count();\n        if (ms >= 20.0) std::fprintf(stderr, \"EDEN_SHUTDOWN_PROCESS step=%s ms=%.1f\\n\", step, ms);\n        eden_last = std::chrono::steady_clock::now();\n    };\n    // Delete the process local region.\n    this->DeleteThreadLocalRegion(kernel, m_plr_address);\n    eden_mark(\"local_region\");\n"],["    m_page_table.Finalize();\n","    eden_mark(\"used_memory_size\");\n    m_page_table.Finalize();\n    eden_mark(\"page_table\");\n"],["    // Free all shared memory infos.\n","    eden_mark(\"system_resource\");\n    // Free all shared memory infos.\n"],["    // Our thread local page list must be empty at this point.\n","    eden_mark(\"shared_memory\");\n    // Our thread local page list must be empty at this point.\n"],["    // Clear expensive resources, as the destructor is not called for guest objects.\n    for (auto& interface : m_arm_interfaces) {\n        interface.reset();\n    }\n    m_exclusive_monitor.reset();\n","    eden_mark(\"resource_limit\");\n    // Clear expensive resources, as the destructor is not called for guest objects.\n    for (auto& interface : m_arm_interfaces) {\n        interface.reset();\n    }\n    eden_mark(\"arm_interfaces\");\n    m_exclusive_monitor.reset();\n    eden_mark(\"exclusive_monitor\");\n"]]''')
anchor = "void KProcess::Finalize(KernelCore& kernel) {"
assert pinned.count(anchor) == 1
expected = "#include <chrono>\n#include <cstdio>\n" + pinned
for before, after in edits:
    start = expected.index(anchor)
    loc = expected.find(before, start)
    assert loc >= 0, ("pinned KProcess finalization changed", before[:70])
    expected = expected[:loc] + after + expected[loc+len(before):]
assert active == expected, "Maintained KProcess differs from retired DEV CMake generator"
assert active.count("EDEN_SHUTDOWN_PROCESS step=%s ms=%.1f") == 1
assert 'if(EDEN_DEV_PROFILE)\n    # Select the complete Encore-maintained diagnostic variant' in cmake
assert 'list(APPEND process_core_sources "${EDEN_MAINTAINED_DEV_PROCESS}")' in cmake
assert 'write_derived("${PORT_BUILD_DIR}/k_process.cpp"' not in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/k_process.cpp" process_source)' not in cmake
assert "eden_patch_process(" not in cmake
print("VENDOR_MAINTAINED_KPROCESS_DEV_PARITY_PASS: 5 scoped edits, DEV-only selection")
