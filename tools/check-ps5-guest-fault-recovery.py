#!/usr/bin/env python3
"""Regression guard for PS5 guest-fault session recovery."""
from pathlib import Path

s = (Path(__file__).resolve().parents[1] / "headless/main.cpp").read_text()
assert 'if (!completion->guest_fault.empty() && !return_to_menu)' in s
assert 'Eden::Report("guest fault", completion->guest_fault.c_str());' in s
assert 'throw std::runtime_error("The game stopped: " + completion->guest_fault +' in s
assert 'selected_game = SelectProsperoEdenGame(launch_error)' in s
assert 'std::string relaunch_game;' not in s
assert 'guest_fault_retries' not in s
assert 'EDEN_GUEST_FAULT_RETRY' not in s
# A one-shot executable range allows the saved LR to be qualified against
# the exact title mapping rather than guessing a module base from its value.
assert 'EDEN_GUEST_CODE_RANGE entry=0x%llx end=0x%llx bytes=%llu' in s
assert 'const u64 code_start = GetInteger(process->GetEntryPoint());' in s
assert 'code_end = info.m_address + info.m_size;' in s
# G12 has one maintained PhysicalCore translation unit per build profile.
# Both must capture the fatal guest context at the actual stopped prefetch path.
base = Path(__file__).resolve().parents[1]
cmake = (base / "headless/CMakeLists.txt").read_text()
assert 'configure_file("${EDEN_PHYSICAL_CORE_SOURCE}" "${PORT_BUILD_DIR}/physical_core.cpp" COPYONLY)' in cmake
for mode in ("standard", "dev"):
    source = (base / f"vendor/encore-active/eden-core/src/core/hle/kernel/physical_core_{mode}.cpp").read_text()
    prefetch = source.split('if (prefetch_abort) {', 1)[1].split('::Eden::RecordGuestFault(eden_fault);', 1)[0]
    assert "interface->GetContext(thread->GetContext());" in prefetch
    assert "thread->GetThreadId()" in prefetch
    assert "const auto& fault_context = thread->GetContext();" in prefetch
    assert "process->GetPageTable().QueryInfo(" in prefetch
    assert "&lr_info, &lr_page, fault_context.lr" in prefetch
    assert "Kernel::KMemoryInfo lr_info{};" in prefetch
    assert "Kernel::Svc::PageInfo lr_page{};" in prefetch
    assert "EDEN_GUEST_FAULT_LR_MAP lr=0x%llx query=%s" in prefetch
    for reg in ("pc", "lr", "sp", "fp"):
        assert f"{reg}=0x%llx" in prefetch
    assert prefetch.index("interface->GetContext(thread->GetContext());") < prefetch.index("const auto& fault_context")
    assert prefetch.index("const auto& fault_context") < prefetch.index("GetPageTable().QueryInfo(")
    assert '#include "guest_fault.h"' in source
    assert '#include <cstdio>' in source
print("PASS PS5 guest fault returns to library without automatic restart")
print("CI is source evidence only; FC27 on-console GPU and launcher tests still required")
