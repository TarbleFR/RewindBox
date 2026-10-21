#!/usr/bin/env python3
"""Retrieve exact locked pub.dev source archives without running package hooks.

Archives remain compressed. Their inclusion does not attest source closure for
native libraries that a Dart package downloads or vendors as compiled code.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/evidence/package-sources-license-audit-2026-10-21.json"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def checked_entries(manifest: dict) -> list[dict]:
    if manifest.get("schema") != 1 or not manifest.get("hosted_packages"):
        raise ValueError("Expected a nonempty schema-1 hosted package source inventory")
    entries = manifest["hosted_packages"]
    seen = set()
    for entry in entries:
        name, version = entry["name"], entry["version"]
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", name) or not re.fullmatch(r"[0-9A-Za-z.+-]+", version):
            raise ValueError("Unsafe package name or version")
        if name in seen:
            raise ValueError("Duplicate package: " + name)
        seen.add(name)
        if not re.fullmatch(r"[0-9a-f]{64}", entry["archive_sha256"]):
            raise ValueError("Invalid locked archive digest for " + name)
        url = urlparse(entry["archive_url"])
        if url.scheme != "https" or url.hostname != "pub.dev" or not url.path.startswith("/api/archives/") or url.username or url.password:
            raise ValueError("Expected an official public pub.dev archive URL for " + name)
    return sorted(entries, key=lambda entry: entry["name"])


def retrieve(entry: dict, output: Path, cache: Path | None = None, timeout: int = 45) -> dict:
    name = entry["name"] + "-" + entry["version"] + ".tar.gz"
    target = output / name
    expected = entry["archive_sha256"]
    if target.exists():
        if target.is_symlink() or not target.is_file() or digest(target) != expected:
            raise ValueError("Existing output differs; left untouched: " + name)
        return {"name": entry["name"], "version": entry["version"], "file": name,
                "sha256": expected, "bytes": target.stat().st_size, "result": "verified_existing"}
    output.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output, prefix=".source-", suffix=".part", delete=False) as destination:
            temporary = Path(destination.name)
            cached = cache / name if cache else None
            if cached is not None and not cached.exists():
                cached = cache / (entry["name"] + "-" + entry["version"]) / "package.tar.gz"
            if cached is not None:
                if not cached.is_file() or cached.is_symlink():
                    raise ValueError("Source cache lacks a regular archive: " + name)
                with cached.open("rb") as source:
                    shutil.copyfileobj(source, destination, 1024 * 1024)
            else:
                request = Request(entry["archive_url"], headers={"User-Agent": "NeoStation-source-retrieval/1"})
                with urlopen(request, timeout=timeout) as source:
                    if urlparse(source.geturl()).scheme != "https":
                        raise ValueError("Non-HTTPS archive redirect for " + name)
                    shutil.copyfileobj(source, destination, 1024 * 1024)
        if digest(temporary) != expected:
            raise ValueError("Downloaded source archive does not match the locked SHA-256: " + name)
        # No decompression, dependency resolution, build or hook execution.
        temporary.replace(target)
        temporary = None
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return {"name": entry["name"], "version": entry["version"], "file": name,
            "sha256": expected, "bytes": target.stat().st_size, "result": "verified_copy" if cache else "verified_download"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--package", action="append", default=[], help="Select a package; repeat as needed. Default: all locked hosted packages")
    parser.add_argument("--source-cache", type=Path, help="Copy verified name-version.tar.gz or name-version/package.tar.gz files from this directory instead of using the network")
    parser.add_argument("--list", action="store_true", help="Print names, exact versions and archive URLs without downloading")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=3)
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    entries = checked_entries(json.loads(manifest_bytes))
    if args.package:
        wanted = set(args.package)
        missing = wanted - {entry["name"] for entry in entries}
        if missing:
            parser.error("Packages absent from the reviewed lock: " + ", ".join(sorted(missing)))
        entries = [entry for entry in entries if entry["name"] in wanted]
    if args.list:
        for entry in entries:
            print(f"{entry['name']} {entry['version']} {entry['archive_url']} {entry['archive_sha256']}")
        return 0
    if args.output is None:
        parser.error("--output is required when retrieving sources")

    def one(entry):
        try:
            return retrieve(entry, args.output, args.source_cache)
        except Exception as exc:
            return {"name": entry["name"], "version": entry["version"], "result": "failed", "error": str(exc)}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(one, entries))
    receipt = {
        "schema": 1, "source_inventory_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "archives_extracted": False, "package_hooks_executed": False,
        "native_binary_correspondence_attested": False,
        "packages": results,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "hosted-source-download-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    failures = [entry for entry in results if entry["result"] == "failed"]
    print(f"Verified {len(results) - len(failures)} of {len(results)} locked source archives; no package code executed.")
    for failure in failures:
        print(f"{failure['name']}: {failure['error']}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
