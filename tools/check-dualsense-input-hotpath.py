#!/usr/bin/env python3
"""Source contract for PS5 DualSense gameplay input event deduplication.

This is a read-only guard; no PS5 SDK/physical-input tests are run.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
header = (root / "headless/devices.h").read_text()
source = (root / "headless/pad.cpp").read_text()
upstream_contract = (
    'SetButton(Identifier(player), button, value);',
    'SetAxis(Identifier(player), physical_axis, value);',
)
assert "static constexpr int kTrackedButtons = 22;" in header
assert "std::array<std::array<std::uint8_t, kTrackedButtons>, kPlayers> button_cache{};" in header
assert "std::array<std::array<float, 4>, kPlayers> axis_cache{};" in header
assert "std::array<std::array<bool, 4>, kPlayers> axis_known{};" in header
assert "buttons.fill(2);" in source   # first even-neutral state must be published

button = source.split("void PadEngine::SetButtonState(std::size_t player, int button, bool value)", 1)[1].split(
    "void PadEngine::SetButtonState(std::size_t player, VirtualButton", 1)[0]
assert "if (player >= kPlayers) return;" in button
assert "button >= 0 && button < kTrackedButtons" in button
assert "if (previous == state) return;" in button
assert "SetButton(Identifier(player), button, value);" in button

sticks = source.split("void PadEngine::SetStickPosition(", 1)[1].split(
    "void PadEngine::SetMotionState(", 1)[0]
assert "physical_axis >= 0 && physical_axis < 4" in sticks
assert "axis_known[player][index] && axis_cache[player][index] == value" in sticks
assert "axis_cache[player][index] = value;" in sticks
assert "axis_known[player][index] = true;" in sticks
assert "SetAxis(Identifier(player), physical_axis, value);" in sticks
assert "publish(base, x);" in sticks and "publish(base + 1, y);" in sticks

# No state-based elision on gyroscope samples: timestamp/accelerations
# must continue propagating in their existing asynchronous cadence.
motion = source.split("void PadEngine::SetMotionState(", 1)[1].split(
    "void PadEngine::ResetControllers()", 1)[0]
assert "SetMotion(Identifier(player), 0," in motion
# A no-rumble poll should not take the same mutex used by guest
# vibration requests. Acquire/release ordering and the producer mutex
# ensure that a concurrent command is never cleared after being written.
assert "std::array<std::atomic<bool>, kPlayers> rumble_pending{};" in header
producer = source.split("PadEngine::SetVibration(", 1)[1].split(
    "bool PadEngine::TakeRumble(", 1)[0]
consumer = source.split("bool PadEngine::TakeRumble(", 1)[1].split(
    "Pad::Pad(", 1)[0]
assert "rumble_pending[player].store(true, std::memory_order_release);" in producer
assert producer.index("sides.changed = true;") < producer.index("rumble_pending[player].store(true")
assert "if (!rumble_pending[player].load(std::memory_order_acquire))" in consumer
assert consumer.index("rumble_pending[player].load(") < consumer.index("std::scoped_lock lock(rumble_mutex);")
assert "rumble_pending[player].store(false, std::memory_order_release);" in consumer
assert consumer.index("sides.changed = false;") < consumer.index("rumble_pending[player].store(false")
assert "std::scoped_lock lock(rumble_mutex);" in producer
assert "std::scoped_lock lock(rumble_mutex);" in consumer
assert "SetMotionAtRest(player);" in source
assert "engine->ResetControllers();" in source
assert "if (!is_usable(raw))" in source

# Illustrative event count model, not an executed physical input test.
def events(values):
    previous = None
    publishes = []
    for value in values:
        if value != previous:
            publishes.append(value)
        previous = value
    return publishes

assert events([False, False, True, True, False, False]) == [False, True, False]
assert events([0.0, 0.0, 0.5, 0.5, 0.0]) == [0.0, 0.5, 0.0]
print("SOURCE CONTRACT: first neutral state, transitions and releases preserved; unchanged HID callbacks skipped")
print("Native SDK compilation / controller interaction / FC27 FPS: NOT TESTED")
