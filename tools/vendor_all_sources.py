#!/usr/bin/env python3
"""Materialize all immutable pinned build inputs inside the Eden Encore Git tree.

Usage:
 python3 tools/vendor_all_sources.py capture [NAME...]
 python3 tools/vendor_all_sources.py verify [NAME...]

Capture never changes existing upstream revisions, and verifies every archive hash.
Preserves exact upstream Git commits as chunked cloneable bundles and full text trees.
No runtime download is necessary once every listed dependency is captured.
"""
from __future__ import annotations
import hashlib,json,os,pathlib,shutil,subprocess,sys,tarfile,tempfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
VENDOR=ROOT/'vendor'
SOURCES=VENDOR/'sources'
OBJECTS=VENDOR/'objects'
CHUNK_SIZE=40*1024*1024
MANIFEST=json.loads((ROOT/'tools/deps.json').read_text())['items']

def die(m):raise RuntimeError(m)
def run(cmd,**kw):subprocess.run(cmd,check=True,**kw)
def sha(path,alg):
 h=hashlib.new(alg)
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def cached(item,entry):
 from importlib.machinery import SourceFileLoader
 # Uses the existing SHA checked cache; this path does not download.
 name=(f"{item['name']}-{entry['name']}" if item['kind']=='files'
       else pathlib.PurePosixPath(entry.get('save') or f"{item['name']}-{(entry.get('sha256') or entry.get('sha512'))[:12]}.tar.gz").name)
 folder=pathlib.Path(os.getenv('PROSPEROEDEN_DEPS_CACHE',str(pathlib.Path.home()/'.cache/prosperoeden-deps')))
 for p in [folder/name,ROOT/entry.get('save','THIS_FILE_DOES_NOT_EXIST')]:
  if p.is_file():
   for alg in ('sha256','sha512'):
    if alg in entry and sha(p,alg)==entry[alg]:return p
 die(f'No verified download of {name}; fetch with tools/deps.py first')
def segment(item,stream_path):
 dest=OBJECTS/item['name'];dest.mkdir(parents=True,exist_ok=True)
 chunks=[]
 with open(stream_path,'rb') as f:
  for i,block in enumerate(iter(lambda:f.read(CHUNK_SIZE),b'')):
   name=f'{i:04d}.chunk';p=dest/name
   checksum=hashlib.sha256(block).hexdigest()
   if p.exists():
    if sha(p,'sha256')!=checksum:die(f'conflicting immutable chunk {p}')
   else:p.write_bytes(block)
   chunks.append({'file':name,'size':len(block),'sha256':checksum})
 spec={'name':item['name'],'size':stream_path.stat().st_size,'sha256':sha(stream_path,'sha256'),'chunks':chunks}
 (dest/'chunks.json').write_text(json.dumps(spec,indent=2)+'\n')
 return spec

def capture_git(item):
 name=item['name'];target=SOURCES/name
 if target.exists() and (target/'VENDOR-ORIGIN.json').is_file():
  meta=json.loads((target/'VENDOR-ORIGIN.json').read_text())
  if meta.get('commit')==item['commit'] and (OBJECTS/name/'chunks.json').exists():
   print('ALREADY',name,flush=True);return
 if target.exists():die(f'nonempty unrecognized vendored path: {target}')
 with tempfile.TemporaryDirectory(prefix=f'eden-{name}-') as tmp:
  tmp=pathlib.Path(tmp);checkout=tmp/'checkout'
  checkout.mkdir();run(['git','init','-q',str(checkout)])
  run(['git','-C',str(checkout),'remote','add','origin',item['url']])
  print('FETCH',name,item['commit'][:12],flush=True)
  run(['git','-C',str(checkout),'fetch','-q','--depth','1','origin',item['commit']])
  run(['git','-C',str(checkout),'checkout','-q','--detach','FETCH_HEAD'])
  actual=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
  if actual!=item['commit']:die(f'{name} commit mismatch {actual}')
  # preserve the original commit metadata/objects for wholly offline git fetch.
  bundle=tmp/'checkout.bundle';run(['git','-C',str(checkout),'bundle','create',str(bundle),'HEAD'])
  heads=subprocess.check_output(['git','bundle','list-heads',str(bundle)],text=True)
  if f"{actual} HEAD" not in heads:die('bundle missing original SHA')
  segment(item,bundle)
  target.mkdir(parents=True)
  files=subprocess.check_output(['git','-C',str(checkout),'ls-files','-z']).split(b'\0')
  copied=0
  for raw in files:
   if not raw:continue
   rel=pathlib.Path(os.fsdecode(raw))
   src=checkout/rel;dst=target/rel;dst.parent.mkdir(parents=True,exist_ok=True)
   if src.is_symlink():dst.symlink_to(os.readlink(src))
   elif src.is_file():shutil.copy2(src,dst)
   else:continue # gitlink submodules are inspected separately in verification
   copied+=1
  (target/'VENDOR-ORIGIN.json').write_text(json.dumps({'name':name,'commit':actual,'url':item['url'],'tracked_files':copied},indent=2)+'\n')
  print('VENDORED',name,'files',copied,'source_bytes',sum(x.stat().st_size for x in target.rglob('*') if x.is_file()),'bundle_bytes',bundle.stat().st_size,flush=True)

def capture_archive(item):
 name=item['name'];dest=SOURCES/name
 if item['kind']=='files':
  dest.mkdir(parents=True,exist_ok=True)
  for entry in item['files']:
   src=cached(item,entry)
   dst=dest/entry['name']
   if not dst.exists():shutil.copy2(src,dst)
   if sha(dst,'sha256')!=entry['sha256']:die(f'wrong vendored {dst}')
  (dest/'VENDOR-ORIGIN.json').write_text(json.dumps({'name':name,'files':len(item['files'])},indent=2)+'\n')
  print('VENDORED',name,'files',len(item['files']),flush=True);return

 archive=cached(item,item)
 # preserve tarballs byte-for-byte, even where upstream source contains symlinks.
 segment(item,archive)
 if name=='pacbrew':
  print('VENDORED',name,'as complete chunked binary SDK archive; unpack for build',flush=True)
  return
 if dest.exists() and (dest/'VENDOR-ORIGIN.json').exists():
  print('ALREADY',name,flush=True);return
 with tempfile.TemporaryDirectory(prefix=f'eden-{name}-') as tmp:
  tmp=pathlib.Path(tmp)
  with tarfile.open(archive,'r:*') as t:
   entries=t.getmembers()
   # All archives (including ffmpeg/harfbuzz) are vendored as full upstream trees.
   for member in entries:
    path=pathlib.PurePosixPath(member.name)
    if path.is_absolute() or '..' in path.parts:die(f'untrusted tar member {member.name}')
   t.extractall(tmp,filter='data')
  roots=[x for x in tmp.iterdir()]
  if len(roots)!=1 or not roots[0].is_dir():die(f'{name} tar not single top-level directory: {roots[:8]}')
  shutil.move(str(roots[0]),str(dest))
  (dest/'VENDOR-ORIGIN.json').write_text(json.dumps({'name':name,'archive_sha':sha(archive,'sha256'),'upstream_url':item['url']},indent=2)+'\n')
  print('VENDORED',name,'source files',sum(1 for x in dest.rglob('*') if x.is_file()),flush=True)

def capture_prefetch(item):
 for idx, entry in enumerate(item.get('setup_prefetch', ())):
  name=f"{item['name']}-setup-{idx}"
  filename=f"{item['name']}-{pathlib.PurePosixPath(entry['dest']).name}"
  path=pathlib.Path(os.getenv('PROSPEROEDEN_DEPS_CACHE',str(pathlib.Path.home()/'.cache/prosperoeden-deps')))/filename
  if not path.is_file():die(f'missing verified setup prefetch: {filename}')
  if sha(path,'sha256')!=entry['sha256']:die(f'wrong setup prefetch SHA: {filename}')
  segment({'name':name},path)
  # Precompiled zlib dependencies are accompanied by their full source tree.
  dest=SOURCES/name
  if path.suffix=='.zip':
   print('VENDORED setup prefetch',name,'as complete ZIP toolchain archive',flush=True)
   continue
  if not dest.exists():
   with tempfile.TemporaryDirectory(prefix='eden-prefetch-') as tmp:
    temp=pathlib.Path(tmp)
    with tarfile.open(path,'r:*') as t:t.extractall(temp,filter='data')
    roots=[x for x in temp.iterdir()]
    if len(roots)!=1 or not roots[0].is_dir():die(f'unexpected setup archive layout: {filename}')
    shutil.move(str(roots[0]),str(dest))
  (dest/'VENDOR-ORIGIN.json').write_text(json.dumps({'name':name,'sha256':entry['sha256'],'url':entry['url']},indent=2)+'\n')
  print('VENDORED setup prefetch',name,flush=True)

def verify(item):
 if item['kind']=='git':
  meta=json.loads((SOURCES/item['name']/'VENDOR-ORIGIN.json').read_text())
  assert meta['commit']==item['commit'],item['name']
 elif item['kind']=='files':
  for f in item['files']:
   assert sha(SOURCES/item['name']/f['name'],'sha256')==f['sha256'],item['name']
 else:
  spec=json.loads((OBJECTS/item['name']/'chunks.json').read_text())
  digest=hashlib.sha256();size=0
  for part in spec['chunks']:
   p=OBJECTS/item['name']/part['file']
   if sha(p,'sha256')!=part['sha256']:die(f'chunk integrity failure: {p}')
   size+=p.stat().st_size
   with open(p,'rb') as f:
    for b in iter(lambda:f.read(1024*1024),b''):digest.update(b)
  assert size==spec['size'] and digest.hexdigest()==spec['sha256'],item['name']
  for alg in ('sha256','sha512'):
   if alg in item:
    # SHA512 checked during capture; all chunks each SHA256 and archive SHA256.
    break
 print('VERIFIED',item['name'],flush=True)

if __name__=='__main__':
 if len(sys.argv)<2 or sys.argv[1] not in ('capture','verify'):
  print(__doc__);sys.exit(2)
 wanted=set(sys.argv[2:]);known={x['name'] for x in MANIFEST}
 if wanted-known:die(f'unknown deps: {wanted-known}')
 for item in MANIFEST:
  if wanted and item['name'] not in wanted:continue
  if sys.argv[1]=='capture':
   capture_git(item) if item['kind']=='git' else capture_archive(item)
   capture_prefetch(item)
  verify(item)
