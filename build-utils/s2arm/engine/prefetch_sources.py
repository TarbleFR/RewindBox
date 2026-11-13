#!/usr/bin/env python3
"""Prefetch only pinned Opus/dav1d source archives; rehash every cache hit."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

CODECS = (
    ('opus', 'tar.gz', 'https://downloads.xiph.org/releases/opus/opus-{version}.tar.gz'),
    ('dav1d', 'tar.xz', 'https://downloads.videolan.org/pub/videolan/dav1d/{version}/dav1d-{version}.tar.xz'),
)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, path):
    subprocess.run(['curl', '-fsSL', '--retry', '8', '--retry-all-errors', '--retry-delay', '10',
                    '--connect-timeout', '30', '-o', str(path), url], check=True)


def prefetch(source, cache, fetch=download):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    if cache.is_symlink():
        raise ValueError('Source cache root must not be a symlink')
    results = []
    for codec, extension, template in CODECS:
        recipe = (Path(source) / 'services' / codec / 'build.sh').read_text()
        match = re.search(r'^VER=([A-Za-z0-9_.+-]+); SHA=([0-9a-f]{64})(?:\s|;|$)', recipe, re.M)
        if not match:
            raise ValueError('Missing safe pinned codec version/digest: ' + codec)
        version, digest = match.groups()
        folder = cache / digest
        if folder.is_symlink():
            folder.unlink()
        folder.mkdir(exist_ok=True)
        target = folder / f'{codec}-{version}.{extension}'
        if target.is_symlink():
            target.unlink()
        hit = target.is_file() and sha(target) == digest
        if not hit:
            # A unique regular temporary file cannot follow a restored symlink.
            with tempfile.NamedTemporaryFile(dir=folder, suffix='.part', delete=False) as stream:
                temporary = Path(stream.name)
            try:
                fetch(template.format(version=version), temporary)
                if temporary.is_symlink() or sha(temporary) != digest:
                    raise ValueError('Downloaded source digest differs: ' + codec)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        results.append(f'{"cached" if hit else "prefetched"} {target.name} {digest}')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('cache', type=Path)
    args = parser.parse_args()
    print('\n'.join(prefetch(args.source, args.cache)))
