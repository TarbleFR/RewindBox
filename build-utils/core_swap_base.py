#!/usr/bin/env python3
"""Start a Core-only delivery from the published IPA of its product instead of recompiling it.

A delivery whose recipe changes only the RPCS3 Core ships the base product
byte for byte: its own Core run builds and tests the dylib, and the recipe's
source contract proves that every other file equals the delivered base tree.
Recompiling Flutter and Xcode would rebuild the same Runner, plugins and Dart
image (the Xcode build does not read the Core: embed_rpcs3_core_lazy.py copies
it into the application after linking). This script puts the base application
where Xcode would have left it, so every later step of the delivery (Core and
engine embedding, receipts, legal bundle, packaging, sealing and every
validator) runs unchanged:

- the base IPA is a published release asset; its SHA-256 must equal the pinned
  value, the GitHub asset digest and the IPA of the base delivery receipt;
- the pinned product trees (lib, native, packages, assets, pubspec) must equal
  those of the base receipt: no shipped source changed since the base;
- the application is extracted with its permissions and symbolic links;
- every bundle version equal to the base build number becomes this build's,
  and the short version must be the pubspec one;
- the base's build-numbered identity receipts are removed: the embed steps
  write this build's;
- StikJIT, which Xcode embeds from the tested framework of the StikJIT steps
  and the packaging validators compare byte for byte with that artifact before
  the seal step signs it, is put back as the tested binary once its code, data
  sections and ABI metadata are proven equal to the published one (only the
  signature differs, and the seal step rewrites it).

The Runner keeps the base's Apple generic version string (PROJECT:Runner-<base>),
which iOS does not read; nothing of the compiled code is touched. The seal step
re-signs every image and proves that signing changed no code or data section.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ROOT / 'build/ios/DolphinDerivedData/Build/Products/Release-iphoneos'
APP = 'Runner.app'
BUNDLE = 'Payload/NeoStation.app'
# The shipped source trees, as the delivery tree modules define them.
TREES = ['lib', 'native', 'packages', 'assets', 'pubspec.yaml', 'pubspec.lock']
REPOSITORY = 'TarbleFR/RewindBox'
# The tested StikJIT framework that the StikJIT steps install for Xcode.
STIKJIT = 'Frameworks/StikJIT.framework/StikJIT'
STIKJIT_TESTED = ROOT / 'build/stikjit-current'


def demand(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def product_trees() -> dict:
    """Git object IDs of the shipped trees in the index in use (the pinned one)."""
    tree = git('write-tree')
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


def pubspec_version() -> str:
    match = re.search(r'^version:\s*([0-9][0-9.]*)', (ROOT / 'pubspec.yaml').read_text(), re.M)
    demand(match is not None, 'pubspec.yaml has no version')
    return match.group(1)


def base_receipt(path: str, build: str, digest: str) -> dict:
    """The base delivery receipt as committed: the pinned tree carries only recipe files."""
    receipt = json.loads(git('show', 'HEAD:' + path))
    demand(receipt.get('result') == 'passed', f'{path}: the base delivery did not pass')
    demand(str(receipt.get('build')) == build, f'{path}: base build {receipt.get("build")} is not {build}')
    demand(receipt['ipa']['sha256'] == digest, f'{path}: the delivered IPA is not the pinned base')
    demand(receipt['ipa'].get('bundleVersion') == build, f'{path}: the delivered bundle version is not {build}')
    return receipt


def published_asset(tag: str, asset: str, digest: str, require_digest: bool = False) -> dict:
    """The release asset, checked against the pinned digest when GitHub records one."""
    release = json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPOSITORY}/releases/tags/{tag}']))
    demand(not release['draft'], f'Release {tag} is a draft')
    matches = [a for a in release['assets'] if a['name'] == asset]
    demand(len(matches) == 1, f'Release {tag} has no single asset {asset}')
    published = matches[0]
    demand(published.get('digest') is not None or not require_digest, f'Release asset {asset} has no recorded digest')
    demand(published.get('digest') in (None, 'sha256:' + digest), f'Release asset digest {published.get("digest")} is not the pinned base')
    return dict(release=release, asset=published)


def fetch(tag: str, asset: str, digest: str, destination: Path) -> dict:
    """Downloads the published asset after checking the release and its recorded digest."""
    found = published_asset(tag, asset, digest)
    release, published = found['release'], found['asset']
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['curl', '--fail', '--location', '--retry', '3', '--silent', '--show-error',
                    published['browser_download_url'], '--output', str(destination)], check=True)
    return dict(tag=tag, name=asset, url=published['browser_download_url'], bytes=published['size'],
                digest=published.get('digest'), releasePublishedAt=release['published_at'],
                releaseTarget=release['target_commitish'])


def read_plist(path: Path) -> tuple[dict, plistlib.PlistFormat]:
    data = path.read_bytes()
    form = plistlib.FMT_BINARY if data.startswith(b'bplist00') else plistlib.FMT_XML
    return plistlib.loads(data), form


def stamp(app: Path, base: str, build: str) -> list[str]:
    """Every bundle version equal to the base build becomes this build's."""
    stamped = []
    for path in sorted(app.rglob('Info.plist')):
        if path.is_symlink() or not path.is_file():
            continue
        data, form = read_plist(path)
        if str(data.get('CFBundleVersion')) != base:
            continue
        data['CFBundleVersion'] = build
        path.write_bytes(plistlib.dumps(data, fmt=form))
        stamped.append(str(path.relative_to(app)))
    for path in app.rglob('Info.plist'):
        if path.is_file() and not path.is_symlink():
            demand(str(read_plist(path)[0].get('CFBundleVersion')) != base, f'{path} still carries build {base}')
    return stamped


def extract(ipa: Path, products: Path, base: str, build: str) -> dict:
    """Puts the base application where Xcode leaves the built one."""
    demand(not list(products.glob('*.app')), f'{products} already holds an application')
    listing = subprocess.check_output(['unzip', '-Z1', str(ipa)], text=True).splitlines()
    demand(listing and all(n.startswith('Payload/') for n in listing), 'The base IPA holds files outside Payload/')
    apps = {n.split('/')[1] for n in listing if n.count('/') >= 2 and n.split('/')[1].endswith('.app')}
    demand(apps == {BUNDLE.split('/')[1]}, f'The base IPA holds {sorted(apps)}, not {BUNDLE}')
    products.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=products.parent) as scratch:
        # unzip keeps the recorded permissions and symbolic links.
        subprocess.run(['unzip', '-q', str(ipa), '-d', scratch], check=True)
        source = Path(scratch) / BUNDLE
        demand(source.is_dir() and not source.is_symlink(), 'The base application is missing')
        app = products / APP
        shutil.move(str(source), str(app))
    info, _ = read_plist(app / 'Info.plist')
    demand(str(info.get('CFBundleVersion')) == base, f'The base application is build {info.get("CFBundleVersion")}, not {base}')
    demand(info.get('CFBundleExecutable') == 'Runner', 'The base application executable is not Runner')
    short = pubspec_version()
    demand(info.get('CFBundleShortVersionString') == short, f'The base version {info.get("CFBundleShortVersionString")} is not the pubspec {short}')
    # The embed steps write this build's identity receipts.
    removed = sorted(p.name for p in app.glob(f'*{base}-identity.json'))
    demand(removed, f'The base application has no build {base} identity receipt')
    for name in removed:
        (app / name).unlink()
    stamped = stamp(app, base, build)
    demand('Info.plist' in stamped, 'The application bundle version was not stamped')
    runner = (app / 'Runner').read_bytes()
    marker = re.search(rb'PROJECT:Runner-([0-9]+)', runner)
    return dict(app=str(app.relative_to(ROOT)) if app.is_relative_to(ROOT) else str(app), shortVersion=short,
                stampedBundleVersions=stamped, removedBaseReceipts=removed,
                runnerAppleGenericVersion=marker.group(1).decode() if marker else None,
                files=sum(1 for p in app.rglob('*') if p.is_file()))


def restore_tested_stikjit(app: Path, tested: Path = STIKJIT_TESTED) -> dict:
    """The tested StikJIT binary in place of the published, signed one, as Xcode leaves it.

    The seal step's fingerprint (code and data sections, symbols, dependencies,
    run paths, platform, minimum OS, install name) must be the same for both:
    the published application ships this code, and only its signature differs.
    """
    from delivery_benchmark import payload_fingerprint
    identity = json.loads((tested / 'identity.json').read_text())
    artifact = tested / 'StikJIT.xcframework/ios-arm64/StikJIT.framework/StikJIT'
    demand(artifact.is_file() and sha256(artifact) == identity['binarySha256'],
           'The tested StikJIT artifact is not the one its identity names')
    shipped = app / STIKJIT
    demand(shipped.is_file() and not shipped.is_symlink(), 'The base application has no StikJIT binary')
    published, data = shipped.read_bytes(), artifact.read_bytes()
    fingerprint = payload_fingerprint(data)
    demand(payload_fingerprint(published) == fingerprint,
           'The published StikJIT is not the tested one: a full build is required')
    mode = shipped.stat().st_mode
    shipped.write_bytes(data)
    shipped.chmod(mode)
    return dict(binary=STIKJIT, publishedSha256=hashlib.sha256(published).hexdigest(),
                testedSha256=identity['binarySha256'], payloadFingerprint=fingerprint)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tag', required=True)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--base-build', required=True)
    parser.add_argument('--base-receipt', required=True, help='path of the base delivery receipt in the built commit')
    parser.add_argument('--build-number', default=os.environ.get('BUILD_NUMBER'))
    parser.add_argument('--ipa', type=Path, help='an already downloaded copy of the asset (tests)')
    parser.add_argument('--products', type=Path, default=PRODUCTS)
    parser.add_argument('--report', type=Path, default=ROOT / 'build/delivery/core-swap-base.json')
    parser.add_argument('--check', action='store_true',
                        help='only check the receipt, the product trees and the release digest (checks job)')
    a = parser.parse_args()
    demand(a.build_number and a.build_number.isdigit() and int(a.build_number) > int(a.base_build),
           f'Build {a.build_number} must follow the base {a.base_build}')
    receipt = base_receipt(a.base_receipt, a.base_build, a.sha256)
    trees = product_trees()
    demand(trees == receipt['productTrees'], 'A shipped source changed since the base: a full build is required')
    if a.check:
        found = published_asset(a.tag, a.asset, a.sha256, require_digest=True)['asset']
        demand(found['size'] == receipt['ipa']['bytes'], 'The release asset size is not the delivered base IPA')
        report = dict(schemaVersion=1, build=int(a.build_number), base=dict(build=int(a.base_build), sha256=a.sha256,
                      receipt=a.base_receipt, receiptSource=receipt['source'], asset=found['name'],
                      digest=found['digest'], bytes=found['size']), productTrees=trees, productTreesEqualBase=True)
        out = a.report.with_name('core-swap-check.json')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        return
    if a.ipa:
        ipa, published = a.ipa, None
    else:
        ipa = ROOT / 'build/core-swap' / a.asset
        published = fetch(a.tag, a.asset, a.sha256, ipa)
    demand(sha256(ipa) == a.sha256, 'The downloaded base IPA is not the pinned one')
    result = extract(ipa, a.products, a.base_build, a.build_number)
    result['stikjit'] = restore_tested_stikjit(a.products / APP)
    report = dict(schemaVersion=1, build=int(a.build_number), base=dict(build=int(a.base_build), sha256=a.sha256,
                  bytes=ipa.stat().st_size, receipt=a.base_receipt, receiptSource=receipt['source'],
                  release=published),
                  productTrees=trees, productTreesEqualBase=True, recompiled=False, **result)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
