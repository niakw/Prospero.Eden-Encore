#!/usr/bin/env python3
"""Verify exact maintained allocator sources and the legacy heap injection.

The source identities and four host C syntax variants are tested; hardware is not.
"""
from pathlib import Path
import hashlib
import platform
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
active = root / "vendor/encore-active/eden-build/tooling/native"
pinned = (root / "third_party/app_heap.c").read_text()
flat = (active / "app_heap_flat.c").read_text()
arenas = (active / "app_heap_arenas.c").read_text()
guard = (active / "heap_guard.h").read_bytes()
cmake = (root / "headless/CMakeLists.txt").read_text()
assert not (root / "headless/heap_arenas.inc").exists()
assert not (root / "headless/heap_guard.h").exists()

def git_blob(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()

assert git_blob(guard) == "56e4b920c93878d15c05a920f0119c1a23934a80"
for old, new in (
    ("128 MiB", "3072 MiB"),
    ("(128u * 1024u * 1024u)", "(3072u * 1024u * 1024u)"),
    ("#include <sys/mman.h>", "#include <sys/mman.h>\nvoid *eden_heap_pages(size_t);\nvoid eden_heap_pages_free(void *, size_t);\nsize_t eden_heap_pages_physical_size(void *);"),
    ("mmap(NULL, PS5_OPENGL_HEAP_SIZE, PROT_READ | PROT_WRITE,\n                    MAP_PRIVATE | MAP_ANON, -1, 0)", "eden_heap_pages(PS5_OPENGL_HEAP_SIZE)"),
    ("if (base == MAP_FAILED)", "if (base == NULL)"),
    ("munmap(base, PS5_OPENGL_HEAP_SIZE)", "eden_heap_pages_free(base, PS5_OPENGL_HEAP_SIZE)"),
    ('"PS5-OpenGL"', '"Eden-headless"'),
):
    assert old in pinned, ("pinned app heap drift", old)
    pinned = pinned.replace(old, new)
assert pinned.count("static atomic_int ps5_heap_state;") == 1
pinned = pinned.replace(
    "static atomic_int ps5_heap_state;",
    '#ifdef EDEN_HEAP_GUARD\n#include "heap_guard.h"\n#endif\nstatic atomic_int ps5_heap_state;',
)
assert flat == pinned, "flat source differs from former CMake output"
start = pinned.index("static int ps5_heap_ready(void) {")
end = pinned.index("void ps5_opengl_heap_stats_print(unsigned iteration) {", start)
assert arenas.startswith(pinned[:start]) and arenas.endswith(pinned[end:])
historical = arenas[len(pinned[:start]):len(arenas)-len(pinned[end:])]
assert git_blob(historical.encode()) == "939cba30d8838ffea10d307f27ca67b098d168cc", "arena fragment drift"
assert 'write_derived("${PORT_BUILD_DIR}/app_heap.c"' not in cmake
assert 'set(EDEN_ACTIVE_HEAP_DIR "${PORT_ROOT}/vendor/encore-active/eden-build/tooling/native")' in cmake
assert 'set(EDEN_HEAP_UNIT "app_heap_arenas.c")' in cmake
assert 'set(EDEN_HEAP_UNIT "app_heap_flat.c")' in cmake
assert '"${EDEN_HEAP_SOURCE}")' in cmake
assert 'APPEND PROPERTY COMPILE_DEFINITIONS EDEN_HEAP_GUARD=1' in cmake
assert 'file(READ "${EDEN_PORT_DIR}/heap_arenas.inc"' not in cmake
compiler = next((c for c in ("clang-18", "clang", "cc") if shutil.which(c)), None)
if compiler is None or platform.machine().lower() not in ("x86_64", "amd64"):
    raise SystemExit("Cannot verify x86_64 native heap syntax")
for path in (active / "app_heap_flat.c", active / "app_heap_arenas.c"):
    for guarded in (False, True):
        args = [compiler, "-std=gnu11", "-fsyntax-only", "-I", str(active)]
        if guarded:
            args.append("-DEDEN_HEAP_GUARD=1")
        subprocess.run([*args, str(path)], check=True, timeout=45)
print("ENCORE_HEAP_SINGLE_SOURCE_PASS variants=2 guards=2 historic_blob=exact")
