#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Aggregate exact keyed F07 cold shader CPU miss/retry diagnostics.

These samples measure the GPU-owner CPU work in CreateGraphicsPipeline /
CreateComputePipeline. They exclude the Vulkan worker wait and GPU execution.
There is no frame ID in this marker: never attribute a miss to a late frame.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re

MARKER = "EDEN_VULKAN_SHADER_MISS "
RECORD = re.compile(
    r"\bEDEN_VULKAN_SHADER_MISS kind=(graphics|compute) "
    r"key=([0-9a-fA-F]{16}) retry=([01]) success=([01]) cpu_ns=([0-9]+)"
    r"(?: env_ns=([0-9]+) pool_ns=([0-9]+) cfg_ns=([0-9]+) "
    r"ir_ns=([0-9]+) spirv_ns=([0-9]+) module_ns=([0-9]+))?(?=\s|$)"
)


@dataclass(frozen=True)
class Miss:
    kind: str
    key: str
    retry: bool
    success: bool
    cpu_ns: int
    stages: tuple[int, int, int, int, int, int] | None = None


def parse(lines: list[str]) -> tuple[list[Miss], int]:
    records: list[Miss] = []
    malformed = 0
    for line in lines:
        if MARKER not in line:
            continue
        match = RECORD.search(line)
        if match is None:
            malformed += 1
            continue
        kind, key, retry, success, ns, *stage_fields = match.groups()
        if "env_ns=" in line and stage_fields[0] is None:
            malformed += 1
            continue
        stages = tuple(int(v) for v in stage_fields) if stage_fields[0] is not None else None
        records.append(Miss(kind, key.lower(), retry == "1", success == "1", int(ns), stages))
    return records, malformed


def nearest_rank_95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[(95 * len(ordered) + 99) // 100 - 1]


def report(records: list[Miss], malformed: int = 0) -> str:
    if not records:
        return f"NO_VALID_SHADER_MISSES malformed={malformed}"
    out = [f"shader_miss_records={len(records)} malformed={malformed}"]
    by_kind: dict[str, list[Miss]] = defaultdict(list)
    for record in records:
        by_kind[record.kind].append(record)
    for kind in ("graphics", "compute"):
        items = by_kind[kind]
        if not items:
            out.append(f"{kind}: attempts=0")
            continue
        first = [item for item in items if not item.retry]
        retry = [item for item in items if item.retry]
        failures = sum(not item.success for item in items)
        total_ns = sum(item.cpu_ns for item in items)
        out.append(
            f"{kind}: attempts={len(items)} unique_keys={len({item.key for item in items})} "
            f"cold={len(first)} retry={len(retry)} failures={failures} "
            f"cpu_sum_ms={total_ns / 1_000_000:.3f} "
            f"cold_cpu_ms={sum(item.cpu_ns for item in first) / 1_000_000:.3f} "
            f"retry_cpu_ms={sum(item.cpu_ns for item in retry) / 1_000_000:.3f} "
            f"p95_attempt_ms={nearest_rank_95([item.cpu_ns for item in items]) / 1_000_000:.3f} "
            f"max_attempt_ms={max(item.cpu_ns for item in items) / 1_000_000:.3f}"
        )
        staged = [item for item in items if item.stages is not None]
        if staged:
            stage_totals = tuple(sum(item.stages[i] for item in staged) for i in range(6))
            out.append(
                f"  staged_attempts={len(staged)}/{len(items)} "
                + " ".join(
                    f"{name}_sum_ms={value / 1_000_000:.3f}"
                    for name, value in zip(
                        ("env", "pool", "cfg", "ir", "spirv", "module"), stage_totals
                    )
                )
            )
        slowest = sorted(items, key=lambda item: item.cpu_ns, reverse=True)[:5]
        for item in slowest:
            out.append(
                f"  slow_key={item.key} retry={int(item.retry)} "
                f"success={int(item.success)} cpu_ms={item.cpu_ns / 1_000_000:.3f}"
                + (
                    " " + " ".join(
                        f"{name}_ms={value / 1_000_000:.3f}"
                        for name, value in zip(
                            ("env", "pool", "cfg", "ir", "spirv", "module"), item.stages
                        )
                    ) if item.stages is not None else " stages=not_recorded"
                )
            )
    out.append(
        "NOTE: CPU miss costs include synchronous translation/admission, not "
        "Vulkan worker waits or GPU completion. No frame IDs: this is not "
        "per-frame causality or proof of an FPS gain."
    )
    out.append(
        "NOTE: repeated log capture may duplicate records; counts are "
        "observed log events, not guaranteed distinct pipeline creations."
    )
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.logs:
        records, malformed = parse(path.read_text(encoding="utf-8", errors="replace").splitlines())
        print(path)
        print(report(records, malformed))


if __name__ == "__main__":
    main()
