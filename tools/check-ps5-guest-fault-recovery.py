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
# A prefetch abort used to report only the thread name. Require the native
# CMake replacement to capture the stopped guest context exactly once on the
# fault path, never per guest JIT entry or normal frame.
cmake = (Path(__file__).resolve().parents[1] / "headless/CMakeLists.txt").read_text()
prefetch = cmake.split('string(REPLACE "${prefetch_old}" [=[', 1)[1].split(']=]', 1)[0]
assert 'if (prefetch_abort) {' in prefetch
assert 'interface->GetContext(thread->GetContext());' in prefetch
assert 'thread->GetThreadId()' in prefetch
assert 'thread->GetContext().pc' in prefetch
assert 'RecordGuestFault(eden_fault);' in prefetch
assert prefetch.index('interface->GetContext(thread->GetContext());') < prefetch.index('RecordGuestFault(eden_fault);')
assert '#include <cstdio>' in cmake
print("PASS PS5 guest fault returns to library without automatic restart")
print("CI is source evidence only; FC27 on-console GPU and launcher tests still required")
