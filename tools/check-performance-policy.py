#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Encore owns all seven ProsperoEden performance controls through its profile policy."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
policy = (root / "headless/encore_performance_policy.h").read_text()
main = (root / "headless/main.cpp").read_text()

fields = (
    "compile_ahead",
    "async_shaders",
    "fast_gpu",
    "unsafe_cpu",
    "unsafe_dma",
    "reactive_flushing",
    "skip_invalidation",
)
body = policy.split("struct Policy {", 1)[1].split("};", 1)[0]
for field in fields:
    assert re.search(rf"\bbool\s+{field}\s*;", body), field

# Every authored video tier has an explicit seven-switch policy.
rows = re.findall(r"\{false,\s*(?:true|false),\s*(?:true|false),\s*(?:true|false),\s*(?:true|false),\s*(?:true|false),\s*(?:true|false)\}", policy)
assert len(rows) == 4, rows
assert "There is no manual" not in policy  # policy is generic, not whitelist-driven

checks = (
    "performance_policy.compile_ahead",
    "performance_policy.async_shaders",
    "performance_policy.fast_gpu",
    "performance_policy.unsafe_cpu",
    "performance_policy.unsafe_dma",
    "performance_policy.reactive_flushing",
    "performance_policy.skip_invalidation",
)
for needle in checks:
    assert needle in main, needle

# One app process launches multiple games: accuracy state is reset before applying a new policy.
for reset in (
    "Settings::values.cpu_accuracy = Settings::CpuAccuracy::Auto;",
    "Settings::values.dma_accuracy.SetValue(Settings::DmaAccuracy::Default);",
    "Settings::values.use_reactive_flushing.SetValue(true);",
    "Settings::values.skip_cpu_inner_invalidation.SetValue(false);",
):
    assert reset in main, reset

# Shipping compile-ahead must not be promised when its required shared-JIT architecture is absent.
assert "#if EDEN_SHARED_JIT_AVAILABLE" in main
assert "Eden::JitList::enabled = false;" in main
assert "saved-block compile-ahead disabled" in main

# Custom visible settings derive a runtime tier instead of silently becoming the heavy profile.
assert "runtime_performance_profile" in main
assert "effective_resolution_for_tuning" in main
assert "effective_output_for_tuning" in main
print("Encore automatic performance policy: 7/7 controls owned by 4 tiers + Custom derivation PASS")
