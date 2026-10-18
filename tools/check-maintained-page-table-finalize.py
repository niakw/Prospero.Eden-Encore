#!/usr/bin/env python3
"""Verify exact pinned G16 page-table replacement and source ownership."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/core/hle/kernel/k_page_table_base.cpp").read_text()
maintained = (root / "vendor/encore-active/eden-core/src/core/hle/kernel/k_page_table_base.cpp").read_text()
cm = (root / "headless/CMakeLists.txt").read_text()
original = """        // Get physical pages.
        KPageGroup pg(m_system.Kernel(), m_block_info_manager);
        this->MakePageGroup(pg, addr, size / PageSize);

        // Free the pages.
        pg.CloseAndReset(m_system.Kernel());
    };"""
replacement = """        // The memory manager is recreated after a kernel shutdown.
        if (m_system.Kernel().IsShuttingDown()) {
            return;
        }

""" + original
assert pinned.count(original) == 1, "upstream finalizer changed"
assert maintained == pinned.replace(original, replacement), "G16 source parity broken"
assert maintained.count("m_system.Kernel().IsShuttingDown()") >= 1
assert 'write_derived("${PORT_BUILD_DIR}/k_page_table_base.cpp"' not in cm
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/kernel/k_page_table_base.cpp"' not in cm
assert 'list(REMOVE_ITEM page_table_core_sources hle/kernel/k_page_table_base.cpp)' in cm
assert 'list(APPEND page_table_core_sources "${EDEN_MAINTAINED_PAGE_TABLE}")' in cm
assert 'set_property(TARGET core PROPERTY SOURCES "${page_table_core_sources}")' in cm
assert 'vendor/encore-active/eden-core/src/core/hle/kernel/k_page_table_base.cpp' in cm
print("ENCORE_MAINTAINED_PAGE_TABLE_FINALIZE_PASS G16=retired parity=exact")
