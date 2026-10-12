#!/usr/bin/env python3
"""R399 source-backed Mesa immutable sampler lifetime with ASan/UBSan proof.

Source/replay equivalence and extracted C copy/advance test are useful
regressions; they do not establish FC27 runtime usage or native PS5 results.
"""
from pathlib import Path
from radv_official_immutable_sampler_fix import patch_c, patch_h
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'vendor/sources/ps5-mesa/src/amd/vulkan'
ACTIVE = ROOT/'vendor/encore-active/ps5-mesa/src/amd/vulkan'
NAMES = ('radv_descriptor_update_template.c', 'radv_descriptor_update_template.h')
base_c, base_h = ((BASE/n).read_text() for n in NAMES)
active_c, active_h = ((ACTIVE/n).read_text() for n in NAMES)
assert patch_c(base_c) == active_c
assert patch_h(base_h) == active_h
assert 'const uint32_t *immutable_samplers;' in base_h
assert 'const uint8_t *immutable_samplers;' in active_h
assert active_c.count('immutable_sampler_count += entry->descriptorCount;') == 1
assert active_c.count('memcpy(immutable_samplers_data, src_samplers, entry->descriptorCount * RADV_SAMPLER_DESC_SIZE);') == 1
assert active_c.count('templ->entry[i].immutable_samplers + RADV_SAMPLER_DESC_SIZE * j') == 2
assert 'templ->entry[i].immutable_samplers + 4 * j' not in active_c
assert active_c.index('immutable_sampler_count += entry->descriptorCount') < active_c.index('templ = vk_alloc2')
generator = (ROOT/'tools/patch-radv-wsi.py').read_text()
installer = (ROOT/'tools/install-vendored-radv.py').read_text()
for n in NAMES:
    path = 'src/amd/vulkan/' + n
    assert "'"+path+"': []" in generator
    assert "'"+path+"'," in installer

# Compile and run the exact Mesa statements extracted from active source.
# The source descriptor layout is poisoned and freed before all reads.
copy = next(x.strip() for x in active_c.splitlines() if 'memcpy(immutable_samplers_data, src_samplers,' in x)
advance = next(x.strip() for x in active_c.splitlines() if 'immutable_samplers_data += entry->descriptorCount' in x)
fixture = r'''#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#define RADV_SAMPLER_DESC_SIZE 16
struct entry { unsigned descriptorCount; const uint8_t *immutable_samplers; };
int main(void) {
    struct entry items[2] = {{2, 0}, {3, 0}};
    uint8_t copied[80] = {0};
    uint8_t *immutable_samplers_data = copied;
    uint32_t *layout = malloc(24 * sizeof(uint32_t));
    if (!layout) return 10;
    for (unsigned i=0; i<24; i++) layout[i] = i+101;
    for (unsigned i=0; i<2; i++) {
        struct entry *entry = &items[i];
        const uint32_t *src_samplers = layout + (i ? 12 : 0);
        COPY_LINE
        entry->immutable_samplers = immutable_samplers_data;
        ADVANCE_LINE
    }
    memset(layout, 0xcc, 24 * sizeof(uint32_t));
    free(layout);
    for (unsigned i=0; i<2; i++) {
        for (unsigned j=0; j<items[i].descriptorCount * 4; j++) {
            uint32_t value = 0;
            memcpy(&value, items[i].immutable_samplers + j*4, sizeof(value));
            if (value != (i ? 12 : 0) + j + 101) return 11;
        }
    }
    if (immutable_samplers_data != copied+sizeof(copied)) return 12;
    puts("PASS retained immutable descriptors after layout release");
    return 0;
}
'''.replace('COPY_LINE',copy).replace('ADVANCE_LINE',advance)
cc = shutil.which('clang-18') or shutil.which('clang') or shutil.which('cc')
assert cc, 'Host C compiler is required'
with tempfile.TemporaryDirectory(prefix='encore-r399-') as td:
    src,exe = Path(td)/'fixture.c',Path(td)/'fixture'
    src.write_text(fixture)
    subprocess.run([cc,'-std=c11','-O1','-g','-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer',str(src),'-o',str(exe)],
                   check=True,capture_output=True,text=True,timeout=30)
    subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=30)
print('R399 PASS: immutable sampler original/active replay and ASan/UBSan lifetime')
