"""Fail closed before artifact upload; never extract untrusted archive members.

Sources, Core/framework archives and test evidence are public. Plaintext IPA files
and Payload/*.app packages belong only in authorized GitHub Releases. Private
delivery uses the existing encrypted envelope; this is not a cryptographic audit.
Artifact exclusions are intentionally ignored during inspection (a conservative
superset), and hidden files are inspected even when the uploader excludes them.
"""
from __future__ import annotations

import argparse
import bz2
import glob
import gzip
import io
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile


class UnsafeArtifact(ValueError):
    """Confirmed plaintext application disclosure."""


class InspectionError(ValueError):
    """Inspection incomplete; do not upload or automatically delete."""


class Budget:
    def __init__(self, max_bytes=8 * 1024**3, max_members=200_000, seconds=180):
        self.max_bytes = max_bytes
        self.bytes = 0
        self.members = 0
        self.max_members = max_members
        self.deadline = time.monotonic() + seconds

    def consume(self, size=0, member=False):
        self.bytes += size
        self.members += bool(member)
        if (self.bytes > self.max_bytes or self.members > self.max_members
                or time.monotonic() > self.deadline):
            raise InspectionError('Artifact inspection exceeded its safety budget')


def check_name(name):
    name = str(name).replace('\\', '/')
    leaf = name.lower().rstrip('/')
    for _ in range(8):
        suffix = Path(leaf).suffix
        if suffix in ('.zip', '.tar', '.gz', '.bz2', '.xz', '.zst', '.tgz', '.tbz2', '.txz'):
            leaf = leaf[:-len(suffix)]
        else:
            break
    if leaf.endswith('.ipa'):
        raise UnsafeArtifact('Plaintext IPA: ' + name)
    if re.search(r'(?:^|/)payload/[^/]+\.app(?:/|$)', name, re.I):
        raise UnsafeArtifact('Unencrypted application Payload: ' + name)
    if re.search(r'\.xcarchive/products/applications/[^/]+\.app(?:/|$)', name, re.I):
        raise UnsafeArtifact('Unencrypted device application archive: ' + name)


def kind(header):
    if header.startswith((b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08')):
        return 'zip'
    if len(header) == 512 and header.strip(b'\0'):
        try:
            # Legacy/V7 tar has no ustar magic but has a verifiable checksum.
            tarfile.TarInfo.frombuf(header, 'utf-8', 'surrogateescape')
            return 'tar'
        except tarfile.HeaderError:
            pass
    if header.startswith(b'\x1f\x8b'):
        return 'gzip'
    if header.startswith(b'BZh'):
        return 'bzip'
    if header.startswith(b'\xfd7zXZ\x00'):
        return 'xz'
    if header.startswith(b'\x28\xb5\x2f\xfd'):
        return 'zstd'
    if header.startswith((b'7z\xbc\xaf\x27\x1c', b'Rar!')):
        return 'unsupported'
    return None


def spool(source, budget):
    result = tempfile.SpooledTemporaryFile(max_size=8 * 1024**2)
    try:
        while True:
            data = source.read(1024**2)
            if not data:
                break
            budget.consume(len(data))
            result.write(data)
        result.seek(0)
        return result
    except BaseException:
        result.close()
        raise


def scan_child(source, name, budget, depth):
    check_name(name)
    budget.consume(member=True)
    # Examine both ends of every nested member, including renamed ZIPs with a
    # prefix. Bounded temporary storage avoids unbounded seek/decompression and
    # never writes archive-controlled paths to disk.
    with spool(source, budget) as copy:
        scan_stream(copy, name, budget, depth)


def scan_stream(stream, name, budget=None, depth=0):
    budget = budget or Budget()
    budget.consume()
    check_name(name)
    if depth > 8:
        raise InspectionError('Nested archive depth exceeds 8: ' + name)
    stream.seek(0)
    header = stream.read(512)
    stream.seek(0)
    archive_kind = kind(header)
    suffix = Path(name.lower()).suffix
    # zipfile also recognizes self-extracting ZIPs when their archive extension
    # is retained. Ordinary binary blobs are inspected by their magic header.
    is_zip = archive_kind == 'zip' or suffix == '.zip' or zipfile.is_zipfile(stream)
    stream.seek(0)
    if is_zip:
        try:
            with zipfile.ZipFile(stream) as archive:
                entries = archive.infolist()
                if len(entries) + budget.members > budget.max_members:
                    raise InspectionError('Too many archive members: ' + name)
                for item in entries:
                    full_name = name + '!' + item.filename
                    check_name(item.filename)
                    if item.flag_bits & 1:
                        raise InspectionError('Password-protected ZIP is not an approved delivery envelope: ' + full_name)
                    if item.is_dir():
                        budget.consume(member=True)
                        continue
                    if item.file_size > budget.max_bytes:
                        raise InspectionError('Archive member exceeds size budget: ' + full_name)
                    with archive.open(item) as child:
                        scan_child(child, full_name, budget, depth + 1)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as error:
            raise InspectionError('Cannot inspect ZIP: ' + name) from error
    elif archive_kind == 'tar' or suffix == '.tar':
        try:
            with tarfile.open(fileobj=stream, mode='r|') as archive:
                for item in archive:
                    budget.consume(member=True)
                    check_name(item.name)
                    if item.issym() or item.islnk():
                        check_name(item.linkname)
                    if item.isfile():
                        if item.size > budget.max_bytes:
                            raise InspectionError('Tar member exceeds size budget: ' + name)
                        with archive.extractfile(item) as child:
                            scan_child(child, name + '!' + item.name, budget, depth + 1)
        except tarfile.TarError as error:
            raise InspectionError('Cannot inspect tar: ' + name) from error
    elif archive_kind in ('gzip', 'bzip', 'xz'):
        opener = {'gzip': gzip.GzipFile, 'bzip': bz2.BZ2File, 'xz': lzma.LZMAFile}[archive_kind]
        try:
            source = opener(fileobj=stream, mode='rb') if archive_kind == 'gzip' else opener(stream, 'rb')
            with source:
                # Fully consume compressed data within the bound; this also
                # verifies CRCs and handles compressed, renamed nested archives.
                with spool(source, budget) as decoded:
                    stem = name.rsplit('.', 1)[0]
                    if suffix in ('.tgz', '.tbz2', '.txz'):
                        stem = name + '.tar'
                    scan_stream(decoded, stem, budget, depth + 1)
        except (EOFError, OSError, lzma.LZMAError) as error:
            raise InspectionError('Cannot inspect compressed file: ' + name) from error
    elif archive_kind == 'zstd':
        binary = shutil.which('zstd')
        if not binary:
            raise InspectionError('zstd is required to inspect this archive: ' + name)
        with tempfile.TemporaryDirectory() as folder:
            packed = Path(folder) / 'input.zst'
            with packed.open('wb') as output:
                stream.seek(0)
                while block := stream.read(1024**2):
                    budget.consume(len(block))
                    output.write(block)
            process = subprocess.Popen([binary, '-q', '-d', '-c', str(packed)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                with spool(process.stdout, budget) as decoded:
                    if process.wait(timeout=max(1, int(budget.deadline - time.monotonic()))) != 0:
                        raise InspectionError('Invalid zstd archive: ' + name)
                    scan_stream(decoded, name.rsplit('.', 1)[0], budget, depth + 1)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
    elif archive_kind == 'unsupported' or suffix in ('.7z', '.rar', '.zip', '.tar', '.tgz', '.tbz2', '.txz', '.gz', '.bz2', '.xz', '.zst'):
        raise InspectionError('Unsupported or malformed archive: ' + name)


def scan_paths(patterns, budget=None):
    budget = budget or Budget()
    seen_files = set()
    scanned = 0

    def scan_file(path):
        nonlocal scanned
        check_name(path)
        real = path.resolve(strict=True)
        check_name(real)
        if real in seen_files:
            return
        seen_files.add(real)
        budget.consume(member=True)
        with real.open('rb') as source:
            scan_stream(source, str(path), budget)
        scanned += 1

    for raw in patterns.splitlines():
        pattern = raw.strip()
        if not pattern or pattern.startswith(('!', '#')):
            continue
        if any(token in pattern for token in ('${{', '{', '}', '@(', '!(', '+(')):
            raise InspectionError('Unresolved or unsupported artifact glob: ' + pattern)
        expanded = os.path.expanduser(pattern)
        for value in glob.iglob(expanded, recursive=True, include_hidden=True):
            path = Path(value)
            check_name(path)
            if path.is_dir():
                visited_dirs = set()
                for parent, dirs, files in os.walk(path, followlinks=True):
                    real_parent = Path(parent).resolve(strict=True)
                    check_name(parent)
                    check_name(real_parent)
                    if real_parent in visited_dirs:
                        # Alias directories and cycles have already been inspected.
                        # Prune traversal, after checking their logical names.
                        dirs[:] = []
                        continue
                    visited_dirs.add(real_parent)
                    budget.consume()
                    for file in files:
                        scan_file(Path(parent) / file)
            elif path.is_file():
                scan_file(path)
            else:
                raise InspectionError('Unreadable artifact path: ' + str(path))
    return {'result': 'no-plaintext-ipa', 'filesInspected': scanned, 'archiveMembersVisited': budget.members,
            'nestedBytesRead': budget.bytes}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='*')
    args = parser.parse_args()
    try:
        paths = '\n'.join(args.paths) if args.paths else os.environ.get('IPA_ARTIFACT_PATHS', '')
        if not paths.strip():
            raise InspectionError('Artifact paths are required')
        print(json.dumps(scan_paths(paths), sort_keys=True))
    except (UnsafeArtifact, InspectionError, OSError, ValueError) as error:
        # No file content or credentials are printed.
        print('IPA upload blocked: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
