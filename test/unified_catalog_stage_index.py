#!/usr/bin/env python3
"""Stage only the immutable final index for a Foundation-only CI preflight.

--verify-local checks reuse without networking. A successful earlier Apple run
must still be reviewed by the maintainer before using [unified-index-verified].
No packs, branch publication, or application build is performed here.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BLOB_SHA = "bbb58e422c42c026a5097b9070c430d51508f0f5"
GZIP_SHA256 = "cf8959bfd6b20b4ef2516e1e235723b1a5048b2fc2c98033d05ad0d48cf84e57"
SIZE = 6_574_067
URL = "https://api.github.com/repos/TarbleFR/neostation-ios/git/blobs/" + BLOB_SHA
PATHS = ("native/cheats/catalogue/manifest.json.gz",
         "packages/neo_cheat_catalog/ios/Resources/manifest.json.gz")


def verify(data: bytes) -> None:
    if len(data) != SIZE:
        raise ValueError("Final index size does not match the frozen blob")
    if hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() != BLOB_SHA:
        raise ValueError("Final index Git blob SHA does not match")
    if hashlib.sha256(data).hexdigest() != GZIP_SHA256:
        raise ValueError("Final gzip SHA256 does not match")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        raise ValueError("The immutable GitHub blob request must not redirect")


def download() -> bytes:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("A read-only GITHUB_TOKEN is required to stage the index")
    request = urllib.request.Request(URL, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github.raw+json",
        "Accept-Encoding": "identity",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "NeoStation-Unified-Index-Preflight",
    })
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=45) as response:
        if response.status != 200:
            raise ValueError("GitHub did not return the immutable blob")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > SIZE:
            raise ValueError("GitHub blob response exceeds the frozen size")
        data = response.read(SIZE + 1)
    verify(data)
    return data


def check_local(root: Path) -> None:
    for relative in PATHS:
        path = root / relative
        if path.stat().st_size != SIZE:
            raise ValueError("Local index size differs from the verified preflight")
        with path.open("rb") as stream:
            verify(stream.read(SIZE + 1))


def stage(root: Path) -> None:
    data = download()  # All bytes and both hashes verified before any writes.
    for relative in PATHS:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            os.replace(temporary, destination)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
    check_local(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--verify-local", action="store_true")
    args = parser.parse_args()
    try:
        check_local(args.root) if args.verify_local else stage(args.root)
    except (OSError, ValueError, urllib.error.URLError) as error:
        # Credentials and response bodies are never included in diagnostics.
        raise SystemExit("Frozen index validation failed: " + str(error)) from None
    print(f"Frozen index verified: bytes={SIZE}, git={BLOB_SHA}, gzip_sha256={GZIP_SHA256}; two copies match")


if __name__ == "__main__":
    main()
