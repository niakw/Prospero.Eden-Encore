#!/usr/bin/env python3
"""Materialize and validate every actual PS5 Eden CPM source cache entry.

Capture only from a PS5 build that already populated and version-verified its
CPM cache. Never fetch moving network sources. Every readable file is committed
in Eden's own Git, with a deterministic full-directory content fingerprint.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,sys,tarfile,functools

ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/'vendor/sources/eden-cpm/VENDOR-CPM-LOCK.json'
SOURCES=LOCK.parent
FILE=ROOT/'vendor/sources/eden/cpmfile.json'
PIN='5f142c7926d0c7fcbbd0ce30794d72f638a43b2a'
EOL_ARCHIVE=ROOT/'vendor/objects/eden-cpm-eol-originals.tar.gz'
EOL_META=ROOT/'vendor/objects/eden-cpm-eol-originals.json'

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

@functools.lru_cache(maxsize=1)
def original_eol_files():
 if not EOL_ARCHIVE.is_file() or not EOL_META.is_file():
  # During first, deliberate source capture there is no original EOL archive.
  return {}
 specs=json.loads(EOL_META.read_text())
 assert specs['format']=='cpm-original-line-endings-1'
 originals={}
 with tarfile.open(EOL_ARCHIVE,'r:gz') as f:
  for member in f.getmembers():
   if not member.isfile() or member.name not in specs['entries'] or member.name.startswith('/') or '..' in Path(member.name).parts:
    raise RuntimeError(f'Unexpected original CPM EOL record {member.name}')
   raw=f.extractfile(member).read()
   if hashlib.sha256(raw).hexdigest()!=specs['entries'][member.name]['original_sha256']:
    raise RuntimeError('Corrupt original EOL byte record '+member.name)
   originals[member.name]=raw
 if set(originals)!=set(specs['entries']):
  raise RuntimeError('Original CPM EOL overlay is incomplete')
 return originals

def tree(path):
 h=hashlib.sha256();number=0;size=0
 try:relative_package=path.resolve().relative_to(SOURCES.resolve()).as_posix()
 except ValueError:relative_package=None
 overrides=original_eol_files() if relative_package is not None else {}
 for f in sorted(path.rglob('*')):
  if f.is_dir() and not f.is_symlink():continue
  relative=f.relative_to(path).as_posix()
  if f.is_symlink():
   target=os.readlink(f)
   if not (path/relative).resolve().is_relative_to(path.resolve()):
    raise RuntimeError(f'CPM source symlink escapes its package: {f} -> {target}')
   h.update(b'L'+relative.encode()+b'\0'+target.encode()+b'\0')
  elif f.is_file():
   h.update(b'F'+relative.encode()+b'\0')
   key=relative_package+'/'+relative if relative_package is not None else None
   original=overrides.get(key)
   if original is not None:
    present=f.read_bytes()
    if present!=original and present!=original.replace(b'\r\n',b'\n'):
     raise RuntimeError('Corrupt or unknown LF-normalized CPM source '+str(f))
    h.update(original);size+=len(original)
   else:
    with f.open('rb') as stream:
     for block in iter(lambda:stream.read(1024*1024),b''):
      h.update(block);size+=len(block)
   number+=1
  else:raise RuntimeError(f'Unexpected CPM source entry {f}')
 return {'sha256':h.hexdigest(),'files':number,'bytes':size}

def capture(cache):
 source_pins=json.loads(FILE.read_text())
 if not cache.is_dir():raise RuntimeError(f'Missing populated PS5 CPM source cache {cache}')
 results={}
 for folder in sorted(cache.iterdir()):
  if not folder.is_dir():continue
  names=[p for p in folder.iterdir() if p.is_dir()]
  if len(names)!=1:raise RuntimeError(f'Unknown/ambiguous CPM versions: {folder}: {names}')
  src=names[0];version=src.name
  matches=[key for key,val in source_pins.items() if val.get('version')==version]
  # Different upstream header packages can share version tags; identify the
  # actual package by its known CPM cache namespace, never by release alone.
  namespace={'boost':'boost','vulkanheaders':'vulkan-headers',
             'vulkanutilitylibraries':'vulkan-utility-libraries',
             'vulkanmemoryallocator':'vulkan-memory-allocator',
             'nlohmann_json':'nlohmann','nx_tzdb':'tzdb'}
  chosen=namespace.get(folder.name,folder.name)
  if chosen in matches:matches=[chosen]
  if len(matches)!=1:raise RuntimeError(f'Unmatched or ambiguous CPM revision {folder.name}/{version}: {matches}')
  vendor=SOURCES/folder.name/version
  vendor.parent.mkdir(parents=True,exist_ok=True)
  # A capture can be restarted after a transient issue without attempting to
  # re-create framework symlinks that the first pass already copied. Cached
  # trees are checked by their complete hash below; never merge over an older
  # vendored snapshot with conflicting symlinks.
  if not vendor.exists():
   shutil.copytree(src,vendor,symlinks=True)
  got=tree(vendor)
  # A deliberate re-capture must reject cache content drift rather than
  # silently accept a stale snapshot at the same package version/tag.
  if got!=tree(src):
   raise RuntimeError(f'CPM source cache changed since snapshot: {folder.name}/{version}')
  results[folder.name]={'version':version,'cpm_key':matches[0],
                        'source_repo':source_pins[matches[0]].get('repo'),
                        'upstream_sha512':source_pins[matches[0]].get('hash'),
                        **got}
  print(f'CPM_VENDOR_CAPTURED {folder.name}/{version} files={got["files"]} bytes={got["bytes"]}',flush=True)
 obj={'original_eden_commit':PIN,'cpmfile_sha256':digest(FILE),
      'entries':results,'excluded_unfetched_cpm_pins':sorted(set(source_pins)-{v['cpm_key'] for v in results.values()})}
 LOCK.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
 print(f'CPM_VENDOR_COMPLETE source_roots={len(results)} files={sum(v["files"] for v in results.values())} bytes={sum(v["bytes"] for v in results.values())}',flush=True)

def check():
 obj=json.loads(LOCK.read_text())
 if obj['original_eden_commit']!=PIN or obj['cpmfile_sha256']!=digest(FILE):
  raise RuntimeError('Pinned Eden cpmfile.json unexpectedly changed')
 pins=json.loads(FILE.read_text())
 if len(obj['entries'])<20:raise RuntimeError('Expected 20+ cached PS5 CPM input packages')
 for name,record in obj['entries'].items():
  folder=SOURCES/name/record['version']
  v=pins[record['cpm_key']]
  if v['version']!=record['version'] or v.get('hash')!=record['upstream_sha512']:
   raise RuntimeError(f'Wrong CPM package or archive pin {name}')
  observed=tree(folder)
  if any(observed[k]!=record[k] for k in ('sha256','files','bytes')):
   raise RuntimeError(f'CPM source tree changed: {name}')
 print('CPM_VENDOR_COMPLETE_OK',len(obj['entries']),'cached PS5 CPM packages; original EOL bytes restored',len(original_eol_files()),'; unused platform/test pins',len(obj['excluded_unfetched_cpm_pins']))
 return obj

def stage(target):
 obj=check()
 destination=target/'.cache/cpm'
 for name,record in obj['entries'].items():
  dst=destination/name/record['version']
  if dst.is_dir():continue
  if dst.exists():raise RuntimeError(f'CPM target not a directory {dst}')
  dst.parent.mkdir(parents=True,exist_ok=True)
  shutil.copytree(SOURCES/name/record['version'],dst,symlinks=True)
  # Nested upstream .gitattributes may normalize CRLF even though our root
  # declares -text. Restore exact original bytes for all 69 proven cases.
  prefix=f'{name}/{record["version"]}/'
  for rel,raw in original_eol_files().items():
   if rel.startswith(prefix):
    (destination/rel).write_bytes(raw)
  print('CPM_SOURCE_RESTORED',name,record['version'],flush=True)
 print('CPM_SOURCE_STAGE_COMPLETE pinned packages',len(obj['entries']))

if __name__=='__main__':
 ap=argparse.ArgumentParser()
 ap.add_argument('--capture',type=Path)
 ap.add_argument('--check',action='store_true')
 ap.add_argument('--stage',type=Path)
 a=ap.parse_args()
 if a.capture:capture(a.capture)
 if a.check:check()
 if a.stage:stage(a.stage)
 if not (a.capture or a.check or a.stage):ap.error('action required')
