#!/usr/bin/env python3
"""A routine source push must not preempt an explicit native debug build."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
workflow=(root / ".github/workflows/build-040-zbic.yml").read_text()
assert "group: encore-native-${{ github.ref }}-${{ github.event_name }}" in workflow
assert "group: encore-native-${{ github.ref }}\n" not in workflow
assert "cancel-in-progress: true" in workflow
assert "github.event_name == 'workflow_dispatch'" in workflow
assert "contains(github.event.head_commit.message || '', '[full-build]')" in workflow
assert "branches:" in workflow and "- dev/ps5-sparse-jit" in workflow
print("NATIVE_MANUAL_RUN_ISOLATION_PASS event-separated concurrency")
