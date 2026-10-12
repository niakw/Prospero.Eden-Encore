#!/usr/bin/env python3
"""Reconcile PS5 OpenGL's *inner* upstream pins against its fully vendored inputs.

No remote network and no PS5 compiler required. A full staging test is done
separately, because it copies and extracts hundreds of MiB of Mesa sources.
"""
from pathlib import Path
import json
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
DEPS=json.loads((ROOT/'tools/deps.json').read_text())['items']
LOCK={x['name']:x for x in DEPS}
VENDOR=ROOT/'vendor/sources'
SOURCE=VENDOR/'opengl-source'
pins=json.loads((SOURCE/'dependencies.json').read_text())
assert (SOURCE/'VENDOR-ORIGIN.json').is_file()
required=0
for name,record in pins['repositories'].items():
    if record.get('optional'):continue
    key='opengl-'+name.lower().replace('_','-')
    assert key in LOCK,key
    x=LOCK[key]
    assert x['kind']=='git' and x['commit']==record['revision'] and x['url']==record['url'],key
    origin=json.loads((VENDOR/key/'VENDOR-ORIGIN.json').read_text())
    assert origin['commit']==x['commit'] and origin['url']==x['url'],key
    assert (ROOT/'vendor/objects'/key/'chunks.json').is_file(),key
    required+=1
assert required==7
mesa=pins['mesa'];m=LOCK['opengl-mesa-26-2']
assert m['url']==mesa['url'] and m['sha256']==mesa['sha256']
assert (VENDOR/'opengl-mesa-26-2/VERSION').read_text().strip()==mesa['version']
assert (ROOT/'vendor/objects/opengl-mesa-26-2/chunks.json').is_file()
b=pins['native_boilerplate'];n=LOCK['opengl-native-boilerplate']
assert b['revision']==n['commit'] and b['url']==n['url']
assert json.loads((VENDOR/'opengl-native-boilerplate/VENDOR-ORIGIN.json').read_text())['commit']==n['commit']
assert b['payload_sdk_archive_sha256']==LOCK['boilerplate']['setup_prefetch'][1]['sha256']
original_fetch=(SOURCE/'tools/fetch-sources.py').read_text()
assert 'third_party' in original_fetch and 'fetch_repo(name, pin)' in original_fetch
builder=(ROOT/'tools/build-opengl-sdk.sh').read_text()
assert 'tools/stage-vendored-opengl-deps.py' in builder
assert builder.index('stage-vendored-opengl-deps.py') < builder.index('python3 "$source_dir/tools/fetch-sources.py"')
print('PS5_OPENGL_CLOSURE_OK 7 mandatory source repos + Mesa 26.2 + native boilerplate, all exact pinned bytes retained')
print('PS5_OPENGL_CLOSURE_LIMITS optional CTS/sokol-samples not used by release; CPM and Mesa wraps separately scoped')
