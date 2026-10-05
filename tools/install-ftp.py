#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Copies a built PPSA99008 folder to a console over FTP (make install).

  tools/install-ftp.py HOST APP_DIR [--port 2121]

Needs a running FTP server on the console (for example the Payload SDK's ftpsrv) and
ProsperoEden closed. Every file goes to /data/homebrew/PPSA99008 under a temporary name and is
renamed into place once complete. Executables are read back and compared when the server offers
raw SELF transfers. Files already on the console that the package does not contain (your
settings, saves and logs live elsewhere) are left alone.
"""
import argparse
import ftplib
import hashlib
import pathlib
import sys

REMOTE = '/data/homebrew/PPSA99008'
EXECUTABLES = {'eboot.bin', 'sce_module/libc.prx', 'sandbox-elevator.elf'}


def connect(host, port):
    client = ftplib.FTP()
    client.connect(host, port, timeout=60)
    client.login()
    return client


def ensure_directories(client, relative):
    path = REMOTE
    for part in pathlib.PurePosixPath(relative).parent.parts:
        path += '/' + part
        try:
            client.mkd(path)
        except ftplib.error_perm:
            pass  # already there


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('host')
    parser.add_argument('app', type=pathlib.Path)
    parser.add_argument('--port', type=int, default=2121)
    options = parser.parse_args(argv)
    host, port, app = options.host, options.port, options.app
    if not (app / 'eboot.bin').is_file():
        sys.exit(f'{app} is not a built PPSA99008 folder (run make package)')
    files = sorted(p for p in app.rglob('*') if p.is_file())
    with connect(host, port) as client:
        try:
            client.mkd(REMOTE)
        except ftplib.error_perm:
            pass
        for local in files:
            relative = local.relative_to(app).as_posix()
            ensure_directories(client, relative)
            target = f'{REMOTE}/{relative}'
            with local.open('rb') as source:
                client.storbinary(f'STOR {target}.partial', source)
            try:
                client.delete(target)
            except ftplib.error_perm:
                pass
            client.rename(f'{target}.partial', target)
            print(f'copied {relative}', flush=True)
    with connect(host, port) as client:
        # First verify the complete install inventory by size. This catches partial folder copies
        # (notably ui/lang/*.po): a build can be valid while a manual FTP transfer silently omits
        # nested files, leaving the launcher in English.
        client.voidcmd('TYPE I')
        missing = []
        mismatched = []
        for local in files:
            relative = local.relative_to(app).as_posix()
            try:
                remote_size = client.size(f'{REMOTE}/{relative}')
            except (ftplib.error_perm, OSError):
                remote_size = None
            if remote_size is None:
                missing.append(relative)
            elif remote_size != local.stat().st_size:
                mismatched.append((relative, local.stat().st_size, remote_size))
        if missing or mismatched:
            sys.exit(f'Incomplete FTP install: missing={missing[:12]} size_mismatch={mismatched[:12]}')
        language_files = [p for p in files if p.relative_to(app).as_posix().startswith('ui/lang/') and p.suffix == '.po']
        if language_files and not any(p.name == 'fr-FR.po' for p in language_files):
            sys.exit('Package has language catalogs but fr-FR.po is missing')

        try:
            client.sendcmd('SELF')  # raw transfers of executables, where supported
        except ftplib.error_perm:
            print(f'Installed and size-verified {len(files)} files in {REMOTE} on {host}; raw SELF verification unavailable.')
            return
        for relative in sorted(EXECUTABLES):
            local = app / relative
            if not local.is_file():
                continue
            digest = hashlib.sha256()
            client.retrbinary(f'RETR {REMOTE}/{relative}', digest.update)
            if digest.hexdigest() != hashlib.sha256(local.read_bytes()).hexdigest():
                sys.exit(f'{relative} differs on the console after the copy')
    print(f'Installed and verified {len(files)} files in {REMOTE} on {host}.')


if __name__ == '__main__':
    main(sys.argv[1:])
