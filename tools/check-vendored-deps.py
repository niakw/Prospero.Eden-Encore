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
print(f'VENDOR_COMPLETE_OK pinned={len(ITEMS)} source_roots={sum((V / 'sources' / i['name']).is_dir() for i in ITEMS)} archive_bundles={sum((V / 'objects' / i['name'] / 'chunks.json').is_file() for i in ITEMS)} bootstrap_objects={sum(len(i.get('setup_prefetch',())) for i in ITEMS)} all_hashes_valid')

# Prove the actual loader can hydrate a new build checkout without user cache,
# DNS, or original upstream. Leave canonical sources untouched: compilers and
# backport generators must receive disposable working trees, not symlinks.
import tempfile
import sys
sys.path.insert(0,str(ROOT/'tools'))
import deps
with tempfile.TemporaryDirectory(prefix='eden-vendor-airgap-') as tmp:
 isolated=Path(tmp)
 # Keep the extra git dependency inside this temporary airgap, not in /tmp
 # next to unrelated build jobs and not on the user's persistent filesystem.
 import os
 os.environ['PROSPEROEDEN_GIT_DEPS_ROOT']=str(isolated/'repos')
 deps.ROOT=isolated
 deps.CACHE=isolated/'empty-source-cache'
 deps.OFFLINE=True
 for name in ('eden','fmt','compiler-rt','zbic','encore-overrides'):
  dep=next(x for x in ITEMS if x['name']==name)
  deps.fetch(dep)
  assert deps.present(dep),name
  target=deps.location(dep) if dep['kind'] in ('git','files') else isolated/dep['creates']
  assert not target.is_symlink(),f'{name}: source must be a mutable isolated copy'
 assert (isolated/'.deps/eden-5f142c79.tar.gz').is_file()
 assert (isolated/'.deps/fmt-12.1.0.tar.gz').is_file()
 assert deps.revision(isolated/'.deps/zbic-11b08f27')=='11b08f2712264bbed731545085cbd9702096ceb7'
 assert deps.revision(isolated/'repos/encore-overrides-review')=='4fdb329e732a71878c1936b24759e58937c1ac18'
 boilerplate=next(x for x in ITEMS if x['name']=='boilerplate')
 sdk=boilerplate['setup_prefetch'][1]
 archive=deps.download(sdk['url'],'sha256',sdk['sha256'],'boilerplate-ps5-payload-sdk.zip')
 assert archive.is_file() and hashlib.sha256(archive.read_bytes()).hexdigest()==sdk['sha256']
print('VENDOR_AIRGAP_OK empty-cache Eden tar + isolated source, fmt, compiler-rt, original Git SHA, PS5 SDK 0.42')
# Upstream source files cannot be rewritten just to satisfy our own formatting
# policy. GitHub source CI must validate our changes while exempting only
# verbatim third-party sources and binary Git/archive objects.
preflight=(ROOT/'.github/workflows/encore-core-preflight.yml').read_text()
assert 'git diff --check FETCH_HEAD HEAD -- .' in preflight
assert "':(exclude)vendor/sources/**'" in preflight
assert "':(exclude)vendor/objects/**'" in preflight
assert "':(exclude)vendor/encore-active/**'" in preflight
print('VENDOR_SOURCE_DIFF_POLICY_OK native Encore changes checked, pristine upstream excluded')
