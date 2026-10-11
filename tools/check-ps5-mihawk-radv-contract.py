#!/usr/bin/env python3
"""R338: source-only gate against misidentifying PS5_Vulkan's two drivers.

This checks Eden's integrated contract; it does NOT prove the GPU is smooth.
"""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def source(name):return (root/name).read_text()
deps=json.loads(source('tools/deps.json'))
items={item['name']:item for item in deps['items']}
for key,repo in (('ps5-vulkan-tools','mihawk-99/PS5_Vulkan'),
                 ('ps5-mesa','mihawk-99/PS5_Mesa'),
                 ('ps5-payload-sdk-fork','mihawk-99/PS5_PayloadSDK')):
    assert key in items,key
    assert repo in items[key]['url'],(key,items[key]['url'])
    assert len(items[key]['commit'])==40,key
pin=items['ps5-mesa']['commit']; assert pin=='0b2d6d1a61d9bbf89cf8beb88a696144f67c61f8',pin
integration=items['ps5-vulkan-tools']['commit']; assert integration=='3f3ee69607013b345d2baa6d6a37c86745649a08',integration
cmake=source('headless/CMakeLists.txt'); assert 'EDEN_VULKAN_DRIVER "CUSTOM"' in cmake
assert 'EDEN_VULKAN_DRIVER STREQUAL "RADV"' in cmake
native=source('tools/check-radv-native.py')
for required in ('libvulkan_radeon.ps5.a','libps5vk.a','radv_GetInstanceProcAddr','__wrap_pthread_create'):
    assert required in native,required
package=source('tools/build-package.sh'); assert 'EDEN_VULKAN_DRIVER=RADV' in package
build=source('tools/build-radv-dependencies.sh')
for required in ('tools/deps.json','mihawk-vulkan-review','mihawk-mesa-review','PS5_MESA_FORK',
                 'tools/build-radv.sh','release','patch-radv-wsi.py','EDEN_WSI_SHA256'):
    assert required in build,required
wsi=source('tools/patch-radv-wsi.py')
assert 'wsi_common_videoout.c' in wsi and 'videoout_unref' in wsi
assert 'EDEN_VIDEOOUT_120HZ' in wsi and 'sceVideoOutSetFlipRate' in wsi
runtime=source('headless/main.cpp')
assert 'MESA_SHADER_CACHE_DIR' in runtime and 'MESA_SHADER_CACHE_MAX_SIZE' in runtime
assert '/cache' in runtime and '/radv' in runtime
vulkan=source('headless/dev_vulkan.h')
assert 'inline bool compute_barriers = true;' in vulkan
assert 'inline bool sync_submissions = false;' in vulkan
assert 'inline bool disable_custom_border = true;' in vulkan
print('R338 PASS: pinned Mihawk RADV, not ps5vk; driver/WSI provenance, shader cache and PS5 feature-switch contracts')
print('R338 NOTE: this source-only gate cannot establish physical VideoOut flip timing or FC27 texture correctness')
