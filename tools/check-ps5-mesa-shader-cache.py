#!/usr/bin/env python3
"""R414: exercise actual vendored Mesa disk cache policy, PS5 vs ordinary host."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
rel = 'src/util/disk_cache_os.c'
original = (root/'vendor/sources/ps5-mesa'/rel).read_text()
active = (root/'vendor/encore-active/ps5-mesa'/rel).read_text()
old = '''   /* If running as a users other than the real user disable cache */
   if (!__normal_user())
      return false;'''
new = '''   /* A PS5 title can use launcher-assigned credentials (not setuid).
    * A host-only effective/real-user mismatch disabled RADV shader cache
    * silently on homebrew titles. Keep the safety guard on other OSes.
    * Source: mpereiraesaa/PS5_Mesa 2026-10-09 (MIT). */
#if !defined(__PROSPERO__)
   if (!__normal_user())
      return false;
#endif'''
assert original.count(old) == 1
assert active == original.replace(old, new, 1), 'Only the OS-specific guard is allowed to change'
start = active.index('bool\ndisk_cache_enabled()\n{')
end = active.index('\nvoid *\ndisk_cache_load_item_foz', start)
body = active[start:end]
assert '#if !defined(__PROSPERO__)' in body
assert 'MESA_SHADER_CACHE_DISABLE' in body
assert 'MESA_GLSL_DISABLE_IO_OPT' in body
source = r'''
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define DETECT_OS_ANDROID 0
static int normal_user = 1;
static int cache_disabled = 0, io_disabled = 0;
static int __attribute__((unused)) __normal_user(void) {return normal_user;}
static char *os_get_option(const char *key) {
    if (!strcmp(key, "MESA_SHADER_CACHE_DISABLE")) return cache_disabled ? "1" : NULL;
    if (!strcmp(key, "MESA_GLSL_DISABLE_IO_OPT")) return io_disabled ? "1" : NULL;
    return NULL;
}
static bool debug_get_bool_option(const char *key, bool fallback) {
    const char *v = os_get_option(key);
    return v ? !strcmp(v,"1") : fallback;
}
''' + body + r'''
int main(void) {
    if (!disk_cache_enabled()) return 1;
    normal_user = 0;
#if defined(__PROSPERO__)
    if (!disk_cache_enabled()) return 2;
#else
    if (disk_cache_enabled()) return 2;
#endif
    normal_user = 1;
    cache_disabled = 1;
    if (disk_cache_enabled()) return 3;
    cache_disabled = 0;
    io_disabled = 1;
    if (disk_cache_enabled()) return 4;
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="eden-mesa-shader-cache-") as td:
    file = Path(td)/'check.c'
    file.write_text(source)
    for variant, macros in [('host', []), ('ps5', ['-D__PROSPERO__'])]:
        exe = Path(td)/variant
        subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined',*macros,str(file),'-o',str(exe)],
                       check=True,timeout=30,capture_output=True,text=True)
        subprocess.run([str(exe)],check=True,timeout=20,capture_output=True,text=True)
print('PASS R414: exact complete Mesa file, PS5 assigned credentials, host setuid guard, cache-off and IO-opt overrides (ASan/UBSan)')
