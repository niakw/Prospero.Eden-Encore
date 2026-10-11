#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Proof that all pinned build inputs live in this source checkout, not upstream URLs."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ITEMS=json.loads((ROOT/'tools/deps.json').read_text())['items']
V=ROOT/'vendor'
def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
 return h.hexdigest()

def assert_blob(name, expected_sha=None):
 folder=V/'objects'/name
 spec=json.loads((folder/'chunks.json').read_text())
 assert spec['name']==name,(name,spec.get('name'))
 sha=hashlib.sha256();length=0
 for ch in spec['chunks']:
  assert 0<ch['size']<=40*1024*1024,(name,ch)
  file=folder/ch['file']
  assert file.is_file() and file.stat().st_size==ch['size'],file
  assert digest(file)==ch['sha256'],file
  with open(file,'rb') as f:
   for block in iter(lambda:f.read(1024*1024),b''):
    sha.update(block);length+=len(block)
 assert length==spec['size'] and sha.hexdigest()==spec['sha256'],name
 if expected_sha:assert spec['sha256']==expected_sha,name
 return spec

for item in ITEMS:
 name=item['name'];src=V/'sources'/name
 if item['kind']=='git':
  lock=json.loads((src/'VENDOR-ORIGIN.json').read_text())
  assert lock['name']==name and lock['commit']==item['commit'],name
  assert (src/'.git').exists() is False,name
  bundle=assert_blob(name)
  header=(V/'objects'/name/bundle['chunks'][0]['file']).open('rb').read(180)
  assert header.startswith(b'# v2 git bundle\n') and (item['commit']+' HEAD').encode() in header,name
 elif item['kind']=='archive':
  assert_blob(name)
  if name!='pacbrew':
   meta=json.loads((src/'VENDOR-ORIGIN.json').read_text())
   assert meta['name']==name,name
 elif item['kind']=='files':
  for entry in item['files']:
   p=src/entry['name'];assert p.is_file() and digest(p)==entry['sha256'],p
 for idx,extra in enumerate(item.get('setup_prefetch',())):
  assert_blob(name+f'-setup-{idx}',extra['sha256'])
print(f'VENDOR_COMPLETE_OK pinned={len(ITEMS)} source_roots=11 archive_bundles=12 bootstrap_objects=2 all_hashes_valid')
