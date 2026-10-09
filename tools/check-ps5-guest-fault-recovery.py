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
print("PASS PS5 guest fault returns to library without automatic restart")
