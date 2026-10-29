#!/usr/bin/env python3
"""F07 V01: join cold shader CPU misses and genuinely blocked Vulkan worker waits.

Both markers use exact pipeline-cache keys, but have no common frame identifier.
Do not sum overlapped CPU/worker time or infer FC27 frame causality.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
import re

WAIT_MARKER = "EDEN_VULKAN_PIPELINE_WAIT "
MISS_MARKER = "EDEN_VULKAN_SHADER_MISS "
WAIT = re.compile(
    r"\bEDEN_VULKAN_PIPELINE_WAIT kind=(graphics|compute) "
    r"key=([0-9a-fA-F]{16}) wait_ns=([0-9]+) usable=([01])(?=\s|$)"
)
SPLIT = re.compile(r"^\s+mutex_ns=([0-9]+) post_mutex_ns=([0-9]+)\s*$")
MISS = re.compile(
    r"\bEDEN_VULKAN_SHADER_MISS kind=(graphics|compute) "
    r"key=([0-9a-fA-F]{16}) retry=([01]) success=([01]) cpu_ns=([0-9]+)(?=\s|$)"
    r"|"
    r"\bEDEN_VULKAN_SHADER_MISS kind=(graphics|compute) "
    r"key=([0-9a-fA-F]{16}) retry=([01]) success=([01]) cpu_ns=([0-9]+)(?=\s| env_ns=)"
)

def parse(lines: list[str]):
    waits = []
    cpu_by_key = defaultdict(list)
    malformed_waits = 0
    for line in lines:
        if WAIT_MARKER in line:
            m = WAIT.search(line)
            if not m:
                malformed_waits += 1
                continue
            kind, key, wait_ns, usable = m.groups()
            tail = line[m.end():]
            lock_ns = post_ns = None
            if "mutex_ns=" in tail or "post_mutex_ns=" in tail:
                split = SPLIT.fullmatch(tail)
                if not split:
                    malformed_waits += 1
                    continue
                lock_ns, post_ns = map(int, split.groups())
                if lock_ns + post_ns != int(wait_ns):
                    malformed_waits += 1
                    continue
            waits.append((kind, key.lower(), int(wait_ns), usable == "1",
                          lock_ns, post_ns))
        if MISS_MARKER in line:
            m = MISS.search(line)
            if m:
                parts = m.group(1, 2, 3, 4, 5) if m.group(1) else m.group(6, 7, 8, 9, 10)
                kind, key, retry, success, cpu_ns = parts
                cpu_by_key[(kind, key.lower())].append((int(cpu_ns), retry == "1", success == "1"))
    return waits, cpu_by_key, malformed_waits

def report(lines: list[str]) -> str:
    waits, cpu_by_key, malformed = parse(lines)
    out = [f"worker_waits={len(waits)} malformed_waits={malformed}"]
    for kind in ("graphics", "compute"):
        own = [w for w in waits if w[0] == kind]
        matched = sum((w[0], w[1]) in cpu_by_key for w in own)
        out.append(
            f"{kind}: blocked_callbacks={len(own)} matched_cpu_key={matched} "
            f"wait_sum_ms={sum(w[2] for w in own) / 1_000_000:.3f} "
            f"failed_pipeline={sum(not w[3] for w in own)}"
        )
        for _, key, wait_ns, usable, lock_ns, post_ns in sorted(own, key=lambda v: v[2], reverse=True)[:5]:
            cpu = cpu_by_key.get((kind, key), [])
            cost = f"{sum(x[0] for x in cpu)/1_000_000:.3f}" if cpu else "not_recorded"
            out.append(
                f"  key={key} waited_ms={wait_ns/1_000_000:.3f} "
                f"usable={int(usable)} cold_cpu_ms={cost} cpu_attempts={len(cpu)} "
                f"mutex_ms={lock_ns / 1_000_000:.3f} post_mutex_ms={post_ns / 1_000_000:.3f}"
                if lock_ns is not None else
                f"  key={key} waited_ms={wait_ns/1_000_000:.3f} "
                f"usable={int(usable)} cold_cpu_ms={cost} cpu_attempts={len(cpu)} "
                "mutex_ms=not_recorded post_mutex_ms=not_recorded"
            )
    out.append(
        "NOTE: CPU work and Vulkan worker wait can overlap; totals are NOT "
        "a single-frame duration. Callbacks already ready before execution "
        "do not emit a wait event. FC27/PS5 causality remains unmeasured."
    )
    return "\n".join(out)

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("logs", type=Path, nargs="+")
    args = ap.parse_args()
    for log in args.logs:
        print(log)
        print(report(log.read_text(encoding="utf-8", errors="replace").splitlines()))

if __name__ == "__main__":
    main()
