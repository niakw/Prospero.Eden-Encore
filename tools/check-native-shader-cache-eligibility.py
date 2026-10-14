#!/usr/bin/env python3
"""Report whether the pinned native shader disk cache can be used.

A configured directory and an environment variable are not proof of hits.
The original 2efd8b3c logs predate the eligibility counter: unknown != true.
The report is read-only and deliberately never changes process credentials.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EVENT = "EDEN_GPU_DISK_CACHE_ELIGIBILITY"
FIELDS = ("uid_match", "gid_match", "directory_ready", "disable_env_present")
LINE = re.compile(r"\b([a-z_]+)=(\d+)\b")


def evaluate(log: str) -> dict:
    matches = [line for line in log.splitlines() if line.startswith(EVENT+" ")]
    if not matches:
        return {"status": "NOT_MEASURED", "usable_proven": False}
    values = dict(LINE.findall(matches[-1]))
    if any(key not in values for key in FIELDS):
        return {"status": "INVALID_SAMPLE", "usable_proven": False}
    flags = {k: int(values[k]) for k in FIELDS}
    if any(val not in (0, 1) for val in flags.values()):
        return {"status": "INVALID_SAMPLE", "usable_proven": False}
    if not flags["uid_match"] or not flags["gid_match"]:
        status = "DRIVER_CACHE_REJECTED_CREDENTIALS"
    elif not flags["directory_ready"]:
        status = "DIRECTORY_MISSING"
    elif flags["disable_env_present"]:
        status = "DISABLE_ENV_VALUE_UNCHECKED"
    else:
        status = "ELIGIBLE_NOT_HIT_VERIFIED"
    # Even perfect credentials cannot establish a cache write/hit.
    return {"status": status, "flags": flags, "usable_proven": False}


def self_test():
    native = (ROOT / "headless/main.cpp").read_text()
    mesa = (ROOT / "vendor/sources/ps5-mesa/src/util/u_debug.h").read_text()
    cache = (ROOT / "vendor/sources/ps5-mesa/src/util/disk_cache_os.c").read_text()
    assert "return geteuid() == getuid() && getegid() == getgid();" in mesa
    assert "if (!__normal_user())" in cache
    assert "Eden::DirectoryExists(cache)" in native
    assert native.count(EVENT) == 1
    assert "const bool cache_uid_match = getuid() == geteuid();" in native
    assert "const bool cache_gid_match = getgid() == getegid();" in native
    assert "setenv(\"MESA_SHADER_CACHE_DIR\", cache.c_str(), 1);" in native
    assert native.index(EVENT) < native.index('setenv("MESA_SHADER_CACHE_DIR"')
    assert evaluate("EDEN_RADV_DISK_CACHE limit_mib=2048 free_mib=16384")["status"] == "NOT_MEASURED"
    prefix=EVENT+" uid_match={uid_match} gid_match={gid_match} directory_ready={directory_ready} disable_env_present={disable_env_present}"
    def check(status, **kwargs):
        flags=dict(uid_match=1, gid_match=1, directory_ready=1, disable_env_present=0)
        flags.update(kwargs)
        assert evaluate(prefix.format(**flags))["status"] == status
    check("ELIGIBLE_NOT_HIT_VERIFIED")
    check("DRIVER_CACHE_REJECTED_CREDENTIALS", uid_match=0)
    check("DRIVER_CACHE_REJECTED_CREDENTIALS", gid_match=0)
    check("DIRECTORY_MISSING", directory_ready=0)
    check("DISABLE_ENV_VALUE_UNCHECKED", disable_env_present=1)
    assert evaluate(EVENT+" uid_match=1")["status"] == "INVALID_SAMPLE"
    print("SHADER_CACHE_ELIGIBILITY_PASS source=pinned_driver missing_measurement=unknown")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("log", nargs="?", type=Path)
    args=parser.parse_args()
    if args.self_test:self_test()
    elif args.log:print(json.dumps(evaluate(args.log.read_text(errors="replace")),indent=2))
    else:parser.error("Provide --self-test or a read-only log path")


if __name__ == "__main__":
    main()
