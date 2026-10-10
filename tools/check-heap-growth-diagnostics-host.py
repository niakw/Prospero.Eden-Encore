#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile the actual PS5 heap-growth formatter with host UBSan.

This is a source-extracted formatter test, NOT a Sony SDK/firmware test and
NOT a PS5 compilation. It must not edit working-tree files or start a build.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "headless/heap_arenas.inc").read_text()
begin = source.index("static int eden_heap_append_decimal(")
end = source.index("/* Adds a space with room for", begin)
body = source[begin:end]
assert "static void eden_heap_log_growth(" in body
assert "snprintf(" not in body and "sprintf(" not in body
assert "malloc(" not in body and "free(" not in body
compiler = next((c for c in ("clang-18", "clang", "cc") if shutil.which(c)), None)
if compiler is None:
    raise SystemExit("A C compiler is required; refusing a source-only PASS")

prefix = r"""
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define EDEN_HEAP_PIECE_SHIFT 27u
static char last_message[256];
static unsigned messages;
static int sceKernelDebugOutText(int channel, const char* line) {
    assert(channel == 0);
    size_t size = strlen(line);
    assert(size < sizeof(last_message));
    memcpy(last_message, line, size + 1);
    ++messages;
    return (int)size;
}
"""
suffix = r"""
int main(void) {
    char tiny[4] = {0};
    size_t used = 0;
    /* A zero-capacity formatter must not underflow capacity-1 or write. */
    assert(!eden_heap_append_decimal(tiny, 0, &used, "", 1));
    assert(!eden_heap_append_decimal(tiny, sizeof(tiny), NULL, "", 1));
    assert(!eden_heap_append_decimal(NULL, sizeof(tiny), &used, "", 1));
    used = sizeof(tiny);
    assert(!eden_heap_append_decimal(tiny, sizeof(tiny), &used, "", 1));
    used = 0;
    assert(!eden_heap_append_decimal(tiny, sizeof(tiny), &used,
                                     "abc", 123456789));
    assert(used < sizeof(tiny));
    used = 0;
    char normal[128] = {0};
    assert(eden_heap_append_decimal(normal, sizeof(normal), &used, "n=", SIZE_MAX));
    char comparison[128] = {0};
    snprintf(comparison, sizeof(comparison), "n=%zu", (size_t)SIZE_MAX);
    assert(strcmp(normal, comparison) == 0);

    eden_heap_log_growth((size_t)192 << 20, 1, 2, 2);
    assert(messages == 1);
    assert(strcmp(last_message,
        "EDEN_HEAP_GROW req_bytes=201326592 root=1 pieces=2 spaces=2 committed_mib=384\n") == 0);
    eden_heap_log_growth(SIZE_MAX, 23, 1, 24);
    assert(messages == 2);
    assert(strstr(last_message, "req_bytes=") != NULL);
    assert(last_message[strlen(last_message) - 1] == '\n');
    puts("PASS extracted PS5 heap growth formatter: no libc formatting, bounds and records");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="eden-growth-format-") as tmp:
    path = Path(tmp)
    cpp = path / "growth.c"
    exe = path / "growth"
    cpp.write_text(prefix + body + suffix)
    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=undefined", "-fno-sanitize-recover=all",
                    str(cpp), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("Host-only extraction/formatter ABI qualified; Sony direct memory remains untested")
