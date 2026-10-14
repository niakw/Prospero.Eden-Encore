#!/usr/bin/env python3
"""Read-only native shader-cache context; never infer cache hits from setup.

The production driver bypasses Mesa's real/effective credential gate on
__PROSPERO__, while preserving it on other OSes. A stale source pin is not
evidence of the active driver behavior. A configured directory is not proof
of shader cache writes or hits.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EVENT = "EDEN_GPU_DISK_CACHE_CONTEXT"
FIELDS = ("uid_match", "gid_match", "directory_ready", "disable_env_present")
LINE = re.compile(r"\b([a-z_]+)=(\d+)\b")


def evaluate(log: str) -> dict:
    matches = [line for line in log.splitlines() if line.startswith(EVENT+" ")]
    if not matches:
        return {"status": "NOT_MEASURED", "cache_hits_proven": False}
    values = dict(LINE.findall(matches[-1]))
    if any(key not in values for key in FIELDS):
        return {"status": "INVALID_SAMPLE", "cache_hits_proven": False}
    flags = {k: int(values[k]) for k in FIELDS}
    if any(val not in (0, 1) for val in flags.values()):
        return {"status": "INVALID_SAMPLE", "cache_hits_proven": False}
    if not flags["directory_ready"]:
        status = "DIRECTORY_MISSING"
    elif flags["disable_env_present"]:
        status = "DISABLE_ENV_VALUE_UNCHECKED"
    elif not flags["uid_match"] or not flags["gid_match"]:
        # The native port bypasses __normal_user on PS5 specifically.
        status = "NATIVE_CREDENTIAL_MISMATCH_ALLOWED_NOT_HIT_VERIFIED"
    else:
        status = "NATIVE_CREDENTIALS_MATCH_NOT_HIT_VERIFIED"
    return {"status": status, "flags": flags, "cache_hits_proven": False}


def self_test():
    native = (ROOT / "headless/main.cpp").read_text()
    base = (ROOT / "vendor/sources/ps5-mesa/src/util/disk_cache_os.c").read_text()
    active = (ROOT / "vendor/encore-active/ps5-mesa/src/util/disk_cache_os.c").read_text()
    mesa = (ROOT / "vendor/sources/ps5-mesa/src/util/u_debug.h").read_text()
    assert "return geteuid() == getuid() && getegid() == getgid();" in mesa
    old = "   if (!__normal_user())\n      return false;"
    assert base.count(old) == 1
    assert active.count(old) == 1
    assert "#if !defined(__PROSPERO__)\n"+old+"\n#endif" in active
    assert 'MESA_SHADER_CACHE_DISABLE' in active
    assert native.count(EVENT) == 1
    assert "const bool cache_uid_match = getuid() == geteuid();" in native
    assert "const bool cache_gid_match = getgid() == getegid();" in native
    assert native.index(EVENT) < native.index('setenv("MESA_SHADER_CACHE_DIR"')
    assert "setegid(getgid())" not in native
    assert evaluate("EDEN_RADV_DISK_CACHE limit_mib=2048 free_mib=16384")["status"] == "NOT_MEASURED"
    line = EVENT+" uid_match={uid_match} gid_match={gid_match} directory_ready={directory_ready} disable_env_present={disable_env_present}"
    def check(status, **overrides):
        flags=dict(uid_match=1,gid_match=1,directory_ready=1,disable_env_present=0)
        flags.update(overrides)
        assert evaluate(line.format(**flags))["status"] == status
    check("NATIVE_CREDENTIALS_MATCH_NOT_HIT_VERIFIED")
    check("NATIVE_CREDENTIAL_MISMATCH_ALLOWED_NOT_HIT_VERIFIED", uid_match=0)
    check("NATIVE_CREDENTIAL_MISMATCH_ALLOWED_NOT_HIT_VERIFIED", gid_match=0)
    check("DIRECTORY_MISSING", directory_ready=0)
    check("DISABLE_ENV_VALUE_UNCHECKED", disable_env_present=1)
    assert evaluate(EVENT+" uid_match=1")["status"] == "INVALID_SAMPLE"
    print("NATIVE_SHADER_CACHE_CONTEXT_PASS native_guard_bypassed host_guard_kept no_cache_hits_assumed")


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
