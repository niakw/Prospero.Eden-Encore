#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned build inputs of ProsperoEden (tools/deps.json).

  tools/deps.py status          list every input, where it lives and whether it matches its pin
  tools/deps.py fetch [NAME...] fetch what is missing (all inputs, or the named ones)
  tools/deps.py path NAME       print where an input lives
  tools/deps.py verify          fail unless every git checkout matches its pinned commit
  tools/deps.py clean           remove the fetched inputs inside .deps (sibling checkouts stay)

Optional immutable source vault: vendor/source-vault (or PROSPEROEDEN_DEPS_VAULT).
Verified blobs and Git bundles are preferred to all network fetching.
PROSPEROEDEN_DEPS_OFFLINE=1 refuses network access when a pinned input is missing.

Nothing that already exists is modified: an existing checkout stays at whatever revision it
has (status reports it), an existing file or folder is not downloaded again. Downloads are
cached in $PROSPEROEDEN_DEPS_CACHE (default ~/.cache/prosperoeden-deps) and verified against
their pinned SHA-256/SHA-512 before use; git inputs are fetched at their pinned commit.
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'tools/deps.json').read_text())
CACHE = pathlib.Path(os.environ.get('PROSPEROEDEN_DEPS_CACHE') or
                     pathlib.Path(os.environ.get('XDG_CACHE_HOME') or pathlib.Path.home() / '.cache')
                     / 'prosperoeden-deps')
VAULT = pathlib.Path(os.environ.get('PROSPEROEDEN_DEPS_VAULT') or ROOT / 'vendor').expanduser()
OFFLINE = os.environ.get('PROSPEROEDEN_DEPS_OFFLINE', '').lower() in ('1', 'true', 'yes')


def vault_source(item):
    return VAULT / 'sources' / item['name']


def restore_chunked_object(item):
    """Reconstruct an immutable original tarball or Git bundle from tracked chunks."""
    specpath = VAULT / 'objects' / item['name'] / 'chunks.json'
    if not specpath.is_file():
        return None
    spec = json.loads(specpath.read_text())
    if spec.get('name') != item['name']:
        fail(f'vault manifest mismatch for {item["name"]}')
    cache_file = CACHE / ('vault-' + item['name'] + '-' + spec['sha256'][:16])
    if cache_file.is_file() and digest(cache_file, 'sha256') == spec['sha256']:
        return cache_file
    CACHE.mkdir(parents=True, exist_ok=True)
    staged = cache_file.with_name(cache_file.name + f'.partial-{os.getpid()}')
    hashed = hashlib.sha256()
    try:
        with open(staged, 'wb') as output:
            total = 0
            for chunk in spec['chunks']:
                source = specpath.parent / chunk['file']
                if not source.is_file() or source.stat().st_size != chunk['size']:
                    fail(f'missing or truncated vendored chunk: {source}')
                if digest(source, 'sha256') != chunk['sha256']:
                    fail(f'corrupted vendored chunk: {source}')
                with open(source, 'rb') as inp:
                    for block in iter(lambda: inp.read(1 << 20), b''):
                        hashed.update(block)
                        output.write(block)
                        total += len(block)
        if total != spec['size'] or hashed.hexdigest() != spec['sha256']:
            fail(f'reassembled vendored archive hash mismatch: {item["name"]}')
        staged.replace(cache_file)
    finally:
        staged.unlink(missing_ok=True)
    return cache_file


def vault_bundle(item):
    return restore_chunked_object(item)



def fail(message):
    print(f'deps: {message}', file=sys.stderr)
    sys.exit(1)


def items(names=()):
    known = {item['name']: item for item in MANIFEST['items']}
    unknown = [name for name in names if name not in known]
    if unknown:
        fail(f'unknown input(s): {", ".join(unknown)} (known: {", ".join(known)})')
    return [known[name] for name in names] if names else list(known.values())


def location(item):
    key = {'git': 'path', 'files': 'dest'}.get(item['kind'])
    if item['kind'] == 'git' and item.get('path', '').startswith('../'):
        cache_root = os.environ.get('PROSPEROEDEN_GIT_DEPS_ROOT')
        if cache_root:
            base = pathlib.Path(cache_root)
            if not base.is_absolute():
                base = ROOT / base
            return (base / pathlib.Path(item['path']).name).resolve()
    return (ROOT / item[key]).resolve() if key else (ROOT / item['creates']).resolve()


def present(item):
    marker = item.get('creates')
    return (ROOT / marker).exists() if marker else location(item).exists()


def digest(path, algorithm):
    hasher = hashlib.new(algorithm)
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            hasher.update(block)
    return hasher.hexdigest()


def pinned_hash(entry):
    for algorithm in ('sha256', 'sha512'):
        if algorithm in entry:
            return algorithm, entry[algorithm]
    fail(f'no pinned hash for {entry.get("url")}')


def download(url, algorithm, expected, name):
    """The cached, verified download of url (downloaded when missing or corrupt)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / name
    if target.exists() and digest(target, algorithm) == expected:
        return target
    for item in MANIFEST['items']:
        if item['kind'] != 'archive':
            continue
        if name.startswith(item['name'] + '-'):
            restored = restore_chunked_object(item)
            if restored:
                if digest(restored, algorithm) != expected:
                    fail(f'vendored archive checksum mismatch: {item["name"]}')
                shutil.copyfile(restored, target)
                print(f'deps: restored {item["name"]} archive from tracked chunks', flush=True)
                return target
    # Some bootstrap checkouts have additional versioned tarballs (zlib).
    # These are immutable inputs too: archive them just like primary deps.
    for item in MANIFEST['items']:
        for index, prefetch in enumerate(item.get('setup_prefetch', ())):
            if prefetch['url'] != url:
                continue
            restored = restore_chunked_object({'name': f'{item["name"]}-setup-{index}'})
            if restored:
                if digest(restored, algorithm) != expected:
                    fail(f'vendored bootstrap archive checksum mismatch: {name}')
                shutil.copyfile(restored, target)
                print(f'deps: restored bootstrap archive from vendored source: {name}', flush=True)
                return target
    if OFFLINE:
        fail(f'offline pinned source missing in vendor/objects: {name}')
    partial = target.with_name(target.name + f'.partial-{os.getpid()}')
    for attempt in range(1, 4):
        try:
            print(f'deps: downloading {url}', flush=True)
            request = urllib.request.Request(url, headers={'User-Agent': 'prosperoeden-deps'})
            with urllib.request.urlopen(request, timeout=120) as response, open(partial, 'wb') as out:
                shutil.copyfileobj(response, out, 1 << 20)
            break
        except OSError as error:
            partial.unlink(missing_ok=True)
            if attempt == 3:
                fail(f'cannot download {url}: {error}')
            time.sleep(5 * attempt)
    actual = digest(partial, algorithm)
    if actual != expected:
        partial.unlink(missing_ok=True)
        fail(f'{url}: {algorithm} {actual} does not match the pinned {expected}')
    partial.replace(target)
    return target


def extract(archive, destination, strip, only=()):
    """Extracts into destination through a temporary folder beside it (no partial trees).
    `only` keeps the members whose path (after strip) is one of these files or lies in one of
    these folders."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = pathlib.Path(tempfile.mkdtemp(prefix='.deps-', dir=destination.parent))
    try:
        with tarfile.open(archive) as tar:
            members = []
            for member in tar.getmembers():
                parts = pathlib.PurePosixPath(member.name).parts[strip:]
                if not parts:
                    continue
                member.name = str(pathlib.PurePosixPath(*parts))
                if only and not any(member.name == keep or member.name.startswith(keep.rstrip('/') + '/')
                                    for keep in only):
                    continue
                members.append(member)
            tar.extractall(staging, members=members, filter='data')
        destination.mkdir(parents=True, exist_ok=True)
        for entry in staging.iterdir():
            target = destination / entry.name
            if target.exists():
                continue  # never replace what is already there
            entry.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def git(*args, cwd=None):
    subprocess.run(['git', *args], cwd=cwd, check=True)


def fetch_git(item):
    path = location(item)
    if not path.exists():
        print(f'deps: fetching {item["url"]} at {item["commit"][:12]} into {path}', flush=True)
        staging = path.with_name(path.name + f'.partial-{os.getpid()}')
        shutil.rmtree(staging, ignore_errors=True)
        git('init', '-q', str(staging))
        git('remote', 'add', 'origin', item['url'], cwd=staging)
        bundle = vault_bundle(item)
        if bundle is not None:
            # Our committed Git bundles are intentionally made from shallow,
            # exact-SHA snapshots. Standard `git fetch bundle` rejects their
            # absent ancestor objects. Extract the *self-contained pack* and
            # explicitly declare the original commit to be the shallow root.
            # This retains the true upstream SHA and the full pinned worktree.
            if not bundle.is_file():
                fail(f'invalid vendored Git pack: {bundle}')
            with open(bundle, 'rb') as stream:
                bundle_bytes = stream.read()
            try:
                header, pack_bytes = bundle_bytes.split(b'\n\n', 1)
            except ValueError:
                fail(f'vendored pack missing Git bundle header: {item["name"]}')
            if (b'# v2 git bundle' not in header or
                    item['commit'].encode() + b' HEAD' not in header.splitlines() or
                    not pack_bytes.startswith(b'PACK')):
                fail(f'vendored pack does not contain expected original HEAD: {item["name"]}')
            pack_path = staging / '.git/objects/pack/pack-vendor.pack'
            pack_path.write_bytes(pack_bytes)
            git('-C', str(staging), 'index-pack', str(pack_path))
            (staging / '.git/shallow').write_text(item['commit'] + '\n')
            git('-C', str(staging), '-c', 'advice.detachedHead=false',
                'checkout', '-q', '--detach', item['commit'])
            print(f'deps: restored {item["name"]} at original {item["commit"][:12]} from vendored Git pack', flush=True)
        else:
            if OFFLINE:
                shutil.rmtree(staging, ignore_errors=True)
                fail(f'offline Git source missing in vendor/objects: {item["name"]}')
            git('fetch', '-q', '--depth', '1', 'origin', item['commit'], cwd=staging)
            git('-c', 'advice.detachedHead=false', 'checkout', '-q', '--detach', 'FETCH_HEAD', cwd=staging)
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=staging, text=True).strip()
        if head != item['commit']:
            fail(f'{item["name"]}: fetched {head}, pinned {item["commit"]}')
        staging.rename(path)
    for entry in item.get('setup_prefetch', ()):
        target = path / entry['dest']
        if target.exists():
            algorithm, expected = pinned_hash(entry)
            if digest(target, algorithm) != expected:
                target.unlink()
        if not target.exists():
            algorithm, expected = pinned_hash(entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            cached = download(entry['url'], algorithm, expected,
                              f'{item["name"]}-{pathlib.PurePosixPath(entry["dest"]).name}')
            shutil.copyfile(cached, target)
        # The boilerplate bootstrap normally downloads the v0.42 SDK itself.
        # Expand the checksum-verified vendored ZIP before invoking it, so
        # its existing executable check takes the genuinely offline path.
        if entry['dest'].endswith('.zip'):
            import zipfile
            with zipfile.ZipFile(target) as archive:
                for member in archive.namelist():
                    parts = pathlib.PurePosixPath(member).parts
                    if member.startswith('/') or '..' in parts:
                        fail(f'unsafe ZIP entry in {target}: {member}')
                sdk_root = path / pathlib.PurePosixPath(entry['dest']).parent
                archive.extractall(sdk_root)
                # ZipFile.extractall does not restore Unix executable modes.
                # The native bootstrap probes `-x bin/prospero-lld` and would
                # otherwise attempt a network download even with this ZIP.
                for member in archive.infolist():
                    mode = (member.external_attr >> 16) & 0o777
                    if mode and not member.is_dir():
                        os.chmod(sdk_root / member.filename, mode)
    if 'setup' in item and not (path / item['setup_creates']).exists():
        print(f'deps: setting up {item["name"]}: {" ".join(item["setup"])}', flush=True)
        env = None
        if sys.platform == 'darwin' and item['name'] == 'boilerplate':
            # zlib's configure selects Apple's `libtool -o` archive convention on Darwin.
            # The pinned bootstrap deliberately replaces libtool with llvm-ar; make must
            # therefore use llvm-ar's `rcs` operation instead of the generated `-o` flag.
            env = os.environ.copy()
            env['ARFLAGS'] = 'rcs'
            env['MAKEFLAGS'] = '-e'
        subprocess.run(item['setup'], cwd=path, check=True, env=env)


def fetch(item):
    kind = item['kind']
    if kind == 'git':
        fetch_git(item)
        return
    if present(item):
        return
    # Source trees in the same Git checkout are complete, versioned, directly
    # searchable inputs. The old .deps path becomes a symlink to the vendored
    # tree, preserving existing CMake and source-generator paths without copies.
    if kind in ('archive', 'files') and item['name'] != 'pacbrew':
        source = vault_source(item)
        if (source / 'VENDOR-ORIGIN.json').is_file():
            if kind == 'archive':
                marker = (ROOT / item['creates']).resolve(strict=False)
                expected_dir = ROOT / item['extract']
                if pathlib.PurePosixPath(item['extract']) == pathlib.PurePosixPath('.deps'):
                    expected_dir = ROOT / '.deps' / pathlib.PurePosixPath(item['creates']).parts[1]
                if pathlib.PurePosixPath(item['extract']) != pathlib.PurePosixPath('.deps'):
                    expected_dir = ROOT / item['extract']
            else:
                expected_dir = ROOT / item['dest']
            expected_dir.parent.mkdir(parents=True, exist_ok=True)
            if not expected_dir.exists() and not expected_dir.is_symlink():
                expected_dir.symlink_to(source.resolve(), target_is_directory=True)
            if present(item):
                print(f'deps: {item["name"]} uses vendored source tree', flush=True)
                return
    if OFFLINE and kind not in ('archive', 'files'):
        fail(f'offline missing source for {item["name"]}')
    if kind == 'archive':
        algorithm, expected = pinned_hash(item)
        name = pathlib.PurePosixPath(item.get('save') or f'{item["name"]}-{expected[:12]}.tar.gz').name
        archive = download(item['url'], algorithm, expected, name)
        if 'save' in item:
            saved = ROOT / item['save']
            if not saved.exists():
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(archive, saved)
        extract(archive, ROOT / item['extract'], item.get('strip', 0), item.get('only', ()))
    elif kind == 'files':
        destination = ROOT / item['dest']
        destination.mkdir(parents=True, exist_ok=True)
        for entry in item['files']:
            target = destination / entry['name']
            if target.exists():
                continue
            algorithm, expected = pinned_hash(entry)
            shutil.copyfile(download(entry['url'], algorithm, expected, f'{item["name"]}-{entry["name"]}'), target)
    else:
        fail(f'{item["name"]}: unknown kind {kind}')
    if not present(item):
        fail(f'{item["name"]}: fetched, but {item["creates"]} is still missing')


def revision(path):
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
        return None


def tracked_changes(path):
    """Tracked/staged changes in a pinned checkout; generated/untracked build outputs are allowed."""
    try:
        return subprocess.check_output(
            ['git', 'status', '--porcelain', '--untracked-files=no'], cwd=path, text=True,
            stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
        return ''


def status():
    width = max(len(item['name']) for item in MANIFEST['items'])
    mismatched = 0
    for item in MANIFEST['items']:
        where = os.path.relpath(location(item), ROOT)
        if item['kind'] == 'git':
            path = location(item)
            if not path.exists():
                state = 'missing'
            else:
                head = revision(path)
                dirty = tracked_changes(path)
                if head == item['commit'] and not dirty:
                    state = 'ok (pinned commit, clean)'
                elif head == item['commit']:
                    mismatched += 1
                    state = 'pinned commit; tracked changes present'
                else:
                    mismatched += 1
                    state = f'present at {head[:12] if head else "no git checkout"}, pinned {item["commit"][:12]}'
                if 'setup' in item and not (path / item['setup_creates']).exists():
                    state += '; setup pending'
        else:
            state = 'ok' if present(item) else 'missing'
        print(f'{item["name"]:<{width}}  {state:<40}  {where}')
    if mismatched:
        print(f'\n{mismatched} checkout(s) differ from their pin or have tracked changes; release verification will fail.')


def verify():
    """Release preflight: every dependency must exist, and git inputs must match their pin."""
    problems = []
    for item in MANIFEST['items']:
        if not present(item):
            problems.append(f'{item["name"]}: missing')
            continue
        if item['kind'] == 'git':
            head = revision(location(item))
            if head != item['commit']:
                problems.append(
                    f'{item["name"]}: at {head[:12] if head else "no git checkout"}, '
                    f'pinned {item["commit"][:12]}')
            dirty = tracked_changes(location(item))
            if dirty:
                summary = '; '.join(dirty.splitlines()[:4])
                problems.append(f'{item["name"]}: tracked checkout changes: {summary}')
            if 'setup' in item and not (location(item) / item['setup_creates']).exists():
                problems.append(f'{item["name"]}: setup output missing: {item["setup_creates"]}')
    if problems:
        for problem in problems:
            print('deps:', problem, file=sys.stderr)
        fail('release dependency verification failed')
    print('deps: all release inputs match their pins and tracked git files are clean')


def clean():
    """Removes the fetched inputs inside this repository's .deps; sibling checkouts stay."""
    deps = (ROOT / '.deps').resolve()
    for item in MANIFEST['items']:
        targets = []
        if item['kind'] == 'files':
            targets.append(ROOT / item['dest'])
        elif item['kind'] == 'archive':
            if 'save' in item:
                targets.append(ROOT / item['save'])
            extract = pathlib.PurePosixPath(item['extract'])
            if extract == pathlib.PurePosixPath('.deps'):
                top = pathlib.PurePosixPath(item['creates']).relative_to(extract).parts[0]
                targets.append(ROOT / extract / top)
            else:
                targets.append(ROOT / extract)
        for target in targets:
            target = target.resolve()
            if deps not in target.parents or not target.exists():
                continue
            print(f'deps: removing {os.path.relpath(target, ROOT)}')
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__.strip())
        return
    command, names = argv[0], argv[1:]
    if command == 'status':
        status()
    elif command == 'clean':
        clean()
    elif command == 'verify':
        if names:
            fail('usage: tools/deps.py verify')
        verify()
    elif command == 'fetch':
        for item in items(names):
            fetch(item)
    elif command == 'path':
        if len(names) != 1:
            fail('usage: tools/deps.py path NAME')
        print(location(items(names)[0]))
    else:
        fail(f'unknown command {command} (status, verify, fetch, path, clean)')


if __name__ == '__main__':
    main(sys.argv[1:])
