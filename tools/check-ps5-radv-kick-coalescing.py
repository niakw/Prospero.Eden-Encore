#!/usr/bin/env python3
"""Host stress for the real PS5 RADV AGC kick/submit code, no PS5 SDK required.

R396: submitters must not take a mutex or signal a condition for every DCB
when a kick is already pending. This test extracts the actual compiled native
functions rather than testing a separate hand-written algorithm.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "vendor/encore-active/ps5-mesa/src/amd/vulkan/winsys/ps5/radv_ps5_platform.c"
GENERATOR = ROOT / "tools/patch-radv-wsi.py"
source = SRC.read_text()
generator = GENERATOR.read_text()
assert "#include <stdatomic.h>" in source
assert "static atomic_bool radv_ps5_kick_pending = ATOMIC_VAR_INIT(false);" in source
assert "atomic_exchange_explicit(&radv_ps5_kick_pending, true, memory_order_acq_rel)" in source
assert "atomic_load_explicit(&radv_ps5_kick_pending, memory_order_acquire)" in source
assert "atomic_store_explicit(&radv_ps5_kick_pending, false, memory_order_release)" in source
assert "p_atomic_add(&radv_ps5_submit_ns[0], flushed - started);" in source
assert "p_atomic_add(&radv_ps5_submit_ns[1], submitted - flushed);" in source
assert "radv_ps5_submit_ns[0] +=" not in source
assert "radv_ps5_submit_ns[1] +=" not in source
assert "atomic_exchange_explicit(&radv_ps5_kick_pending" in generator
# No speculative batching of DCBs or GPU fences: this only coalesces redundant
# userspace mutex/condition wakeups, not any actual driver command submissions.
assert source.count("sceAgcDriverSubmitDcb(&description)") == 1
assert source.count("sceAgcSuspendPoint()") == 1
start = source.index("static uint64_t radv_ps5_submit_ns[3];")
stop = source.index("\nvoid\nradv_ps5_submit_times(", start)
native = source[start:stop]
assert native.count("radv_ps5_submit(") == 1

host = r"""
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdatomic.h>
#include <threads.h>
#include <time.h>
#include <stdlib.h>

struct ps5_agc_submit_description {
    uint32_t *words;
    uint32_t word_count;
};
static atomic_ullong posted = ATOMIC_VAR_INIT(0);
static atomic_ullong visible = ATOMIC_VAR_INIT(0);
static atomic_uint kicks = ATOMIC_VAR_INIT(0);
static uint64_t os_time_get_nano(void) {
    struct timespec now;
    assert(clock_gettime(CLOCK_MONOTONIC, &now) == 0);
    return (uint64_t)now.tv_sec * 1000000000ull + (uint64_t)now.tv_nsec;
}
#define p_atomic_add(p, n) ((void)__atomic_fetch_add((p), (n), __ATOMIC_RELAXED))
static void radv_ps5_cpu_flush(const void *address, size_t bytes) {
    (void)address; (void)bytes;
}
static int32_t sceAgcDriverSubmitDcb(
    const struct ps5_agc_submit_description *description) {
    assert(description && description->words && description->word_count == 4);
    atomic_fetch_add_explicit(&posted, 1, memory_order_release);
    return 0;
}
static int32_t sceAgcSuspendPoint(void) {
    // A kick makes every DCB submitted before this point visible.
    atomic_fetch_add_explicit(&kicks, 1, memory_order_relaxed);
    atomic_store_explicit(&visible, atomic_load_explicit(&posted, memory_order_acquire),
                          memory_order_release);
    const struct timespec delay = {0, 150000};
    thrd_sleep(&delay, NULL);
    return 0;
}
""" + native + r"""
static int producer(void *arg) {
    (void)arg;
    uint32_t commands[4] = {1, 2, 3, 4};
    for (int i=0; i<3000; ++i)
        assert(radv_ps5_submit(commands, 4, NULL, 0) == 0);
    return 0;
}
static void drain_accepted(void) {
    for (unsigned i=0; i<3000; ++i) {
        if (atomic_load_explicit(&visible, memory_order_acquire) ==
            atomic_load_explicit(&posted, memory_order_acquire)) return;
        const struct timespec delay={0, 1000000};
        thrd_sleep(&delay,NULL);
    }
    fprintf(stderr,"kick liveness failed: visible=%llu submitted=%llu\n",
        (unsigned long long)atomic_load(&visible),
        (unsigned long long)atomic_load(&posted));
    abort();
}
int main(void) {
    thrd_t producers[4];
    for (int i=0; i<4; ++i)
        assert(thrd_create(&producers[i], producer, NULL) == thrd_success);
    for (int i=0; i<4; ++i) {
        int code=-1;
        assert(thrd_join(producers[i], &code) == thrd_success);
        assert(code == 0);
    }
    drain_accepted();
    const unsigned kicks_first=atomic_load(&kicks);
    assert(atomic_load(&posted) == 12000);
    assert(kicks_first != 0 && kicks_first < 3000);
    // A submit after the previous request has drained MUST get a new kick.
    // An atomic coalescing implementation with a missed wake fails here.
    const struct timespec delay={0,20000000};
    thrd_sleep(&delay,NULL);
    assert(radv_ps5_submit((uint32_t[4]){1,2,3,4},4,NULL,0)==0);
    drain_accepted();
    assert(atomic_load(&posted)==12001 && atomic_load(&visible)==12001);
    assert(atomic_load(&kicks)>kicks_first);
    puts("PASS PS5 RADV actual kick source: 12K parallel DCBs, coalesced wakeups, idle-to-active liveness");
    return 0;
}
"""

compiler = shutil.which("clang-18") or shutil.which("clang") or shutil.which("cc")
assert compiler, "C11 compiler unavailable"
with tempfile.TemporaryDirectory(prefix="eden-r396-radv-kick-") as directory:
    work = Path(directory)
    (work / "kick.c").write_text(host)
    binary = work / "kick"
    subprocess.run([compiler, "-std=c11", "-O1", "-Wall", "-Wextra",
                    "-Werror", "-pthread", "-fsanitize=address,undefined",
                    str(work / "kick.c"), "-o", str(binary)], check=True, timeout=30)
    subprocess.run([str(binary)], check=True, timeout=30)
