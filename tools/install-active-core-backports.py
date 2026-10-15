#!/usr/bin/env python3
"""Install validated CPU I-cache and host service-wait patches unconditionally.

Unlike the old opt-in experiments, these are now part of every *active*
native source tree. Fail closed if the pinned baseline or an existing staged
file differs. Do not include the quarantined dummy-thread wait patch, which
can leave a dangling scheduler wait-queue pointer.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "vendor/sources/eden"
PATCHES = (
    ROOT / "headless/backports/eden-dynarmic-icache-coherence.patch",
    ROOT / "headless/backports/eden-sm-host-wait.patch",
)
PIN = "5f142c7926d0c7fcbbd0ce30794d72f638a43b2a"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def affected() -> list[str]:
    names = set()
    for patch in PATCHES:
        data = patch.read_text(encoding="utf-8")
        for line in data.splitlines():
            if line.startswith("+++ b/"):
                rel = line[6:]
                if not rel.startswith("src/") or ".." in Path(rel).parts:
                    raise RuntimeError(f"Invalid target in {patch}: {rel}")
                names.add(rel)
    if len(names) != 6:
        raise RuntimeError(f"Expected exactly six core patch sources: {sorted(names)}")
    return sorted(names)


def derive() -> dict[str, tuple[bytes, bytes]]:
    files = affected()
    with tempfile.TemporaryDirectory(prefix="encore-active-core-") as temp:
        stage = Path(temp)
        for relative in files:
            source = ORIGINAL / relative
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        for patch in PATCHES:
            result = subprocess.run(
                ["patch", "--batch", "--fuzz=0", "-p1", "-d", str(stage)],
                input=patch.read_bytes(), capture_output=True, timeout=20,
            )
            if result.returncode:
                raise RuntimeError(
                    f"{patch.name}: pinned source does not accept patch: "
                    f"{result.stderr.decode(errors='replace')[-1200:]} "
                    f"{result.stdout.decode(errors='replace')[-1200:]}"
                )
        result = {}
        for relative in files:
            old = (ORIGINAL / relative).read_bytes()
            new = (stage / relative).read_bytes()
            if old == new:
                raise RuntimeError(f"Unapplied active patch: {relative}")
            result[relative] = (old, new)
        return result


def stage_source(destination: Path, expected: dict[str, tuple[bytes, bytes]], *, check: bool) -> None:
    if (destination / "GIT-COMMIT").read_text().strip() != PIN:
        raise RuntimeError("Wrong pinned core revision")
    changed = 0
    for relative, (old, new) in expected.items():
        target = destination / relative
        current = target.read_bytes()
        if current == new:
            continue
        if check or current != old:
            raise RuntimeError(
                f"Active patch missing/unknown revision: {relative} "
                f"current={sha(current)} base={sha(old)} active={sha(new)}"
            )
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            tmp = Path(handle.name)
        try:
            tmp.write_bytes(new)
            tmp.replace(target)
        finally:
            tmp.unlink(missing_ok=True)
        changed += 1
    print(f"EDEN_ACTIVE_CORE_BACKPORTS files={len(expected)} changed={changed} "
          "icache=on service_wait=on dummy_wait=quarantined")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", nargs="?", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = derive()
    if args.destination:
        stage_source(args.destination, expected, check=args.check)
    else:
        print(f"EDEN_ACTIVE_CORE_PATCH_REPLAY_OK files={len(expected)} "
              "icache=on service_wait=on")
if __name__ == "__main__":
    main()
