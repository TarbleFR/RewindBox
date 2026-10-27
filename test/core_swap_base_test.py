#!/usr/bin/env python3
"""Core-swap delivery: the base application preparation and the workflow variant.

core_swap_base.extract runs on synthetic IPAs (binary and XML property lists,
build-numbered and other receipts, a Runner with its Apple generic version):
it must stamp exactly the bundles of the base build, remove only the base's
build-numbered receipts, and refuse anything that is not the expected base.
core_swap_base.restore_tested_stikjit runs on synthetic ARM64 images: it must
put back the tested binary when only the signature differs, and refuse a
different code section or an artifact that is not the one its identity names.
make_core_swap_workflow.transform runs on the committed 560 delivery workflow
and on altered copies it must refuse.
"""
import copy
import hashlib
import json
import plistlib
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils'))
import core_swap_base as base  # noqa: E402
import make_core_swap_workflow as variant  # noqa: E402
import yaml  # noqa: E402

SHORT = base.pubspec_version()
APP = 'Payload/NeoStation.app/'


def bundle(version, fmt=plistlib.FMT_BINARY, short=SHORT, executable=None):
    data = {'CFBundleVersion': version, 'CFBundleShortVersionString': short}
    if executable:
        data['CFBundleExecutable'] = executable
    return plistlib.dumps(data, fmt=fmt)


def files(version='559', short=SHORT):
    return {
        APP + 'Info.plist': bundle(version, short=short, executable='Runner'),
        APP + 'Runner': b'\xcf\xfa\xed\xfe' + b'@(#)PROGRAM:Runner  PROJECT:Runner-' + version.encode() + b'\n',
        APP + 'Frameworks/DolphinCore.framework/Info.plist': bundle(version, plistlib.FMT_XML),
        APP + 'Frameworks/mgba_libretro.framework/Info.plist': bundle('1.0'),
        APP + 'PlugIns/RPCS3JITHelper.appex/Info.plist': bundle(version),
        APP + f'RPCS3-cell{version}-identity.json': b'{}',
        APP + f'LiquidGlass-ui{version}-identity.json': b'{}',
        APP + 'MeloNX-delete509-identity.json': b'{"build": ' + version.encode() + b'}',
        APP + 'Frameworks/libRPCS3Core.dylib': b'\xcf\xfa\xed\xfe core',
    }


def ipa(directory, entries):
    stage = Path(directory) / 'stage'
    for name, data in entries.items():
        path = stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if name.endswith(('Runner', '.dylib')):
            path.chmod(0o755)
    out = Path(directory) / 'base.ipa'
    subprocess.run(['zip', '-qry', str(out), '.'], cwd=stage, check=True)
    return out


def refused(entries, message, products_with_app=False):
    with tempfile.TemporaryDirectory() as td:
        products = Path(td) / 'products'
        if products_with_app:
            (products / 'Other.app').mkdir(parents=True)
        try:
            base.extract(ipa(td, entries), products, '559', '560')
        except SystemExit as error:
            assert message in str(error), (message, str(error))
            return
        raise AssertionError('accepted: ' + message)


def test_extract():
    with tempfile.TemporaryDirectory() as td:
        products = Path(td) / 'products'
        result = base.extract(ipa(td, files()), products, '559', '560')
        app = products / 'Runner.app'
        assert result['stampedBundleVersions'] == ['Frameworks/DolphinCore.framework/Info.plist', 'Info.plist',
                                                   'PlugIns/RPCS3JITHelper.appex/Info.plist'], result
        assert result['removedBaseReceipts'] == ['LiquidGlass-ui559-identity.json', 'RPCS3-cell559-identity.json']
        assert result['runnerAppleGenericVersion'] == '559' and result['shortVersion'] == SHORT
        for name in result['stampedBundleVersions']:
            data = (app / name).read_bytes()
            assert plistlib.loads(data)['CFBundleVersion'] == '560', name
        # Each property list keeps its format; other bundles keep their own version.
        assert (app / 'Info.plist').read_bytes().startswith(b'bplist00')
        assert (app / 'Frameworks/DolphinCore.framework/Info.plist').read_bytes().startswith(b'<?xml')
        assert plistlib.loads((app / 'Frameworks/mgba_libretro.framework/Info.plist').read_bytes())['CFBundleVersion'] == '1.0'
        # Receipts of other builds stay for the embed steps to rewrite; executables keep their mode.
        assert (app / 'MeloNX-delete509-identity.json').is_file()
        assert (app / 'Runner').stat().st_mode & 0o777 == 0o755
        assert (app / 'Frameworks/libRPCS3Core.dylib').stat().st_mode & 0o777 == 0o755
        assert result['files'] == len(files()) - 2


def test_refusals():
    entries = files()
    refused(dict(entries, **{'extra.txt': b'x'}), 'outside Payload/')
    refused({k.replace('NeoStation.app', 'Other.app'): v for k, v in entries.items()}, 'not Payload/NeoStation.app')
    refused(files('558'), 'not 559')
    refused(files(short='9.9.9'), 'is not the pubspec')
    refused({k: v for k, v in entries.items() if not k.endswith('559-identity.json')}, 'no build 559 identity receipt')
    refused(dict(entries, **{APP + 'Info.plist': bundle('559', executable='Other')}), 'executable is not Runner')
    refused(entries, 'already holds an application', products_with_app=True)


def image(code, signature):
    """A thin ARM64 dylib: one __TEXT,__text section and a code signature after it."""
    commands = 72 + 80 + 16
    text = 32 + commands
    signed = text + 16 * ((len(code) + 15) // 16)
    header = struct.pack('<IIIIIIII', 0xFEEDFACF, 0x0100000C, 0, 6, 2, commands, 0, 0)
    segment = struct.pack('<II16sQQQQIIII', 0x19, 152, b'__TEXT', 0, signed, 0, signed, 5, 5, 1, 0)
    section = struct.pack('<16s16sQQIIIIIIII', b'__text', b'__TEXT', text, len(code), text, 2, 0, 0, 0, 0, 0, 0)
    signature = struct.pack('<IIII', 0x1D, 16, signed, len(signature))
    return (header + segment + section + signature + code).ljust(signed, b'\0') + signature


def stikjit(directory, published, tested, recorded=None):
    app = Path(directory) / 'Runner.app'
    shipped = app / base.STIKJIT
    shipped.parent.mkdir(parents=True)
    shipped.write_bytes(published)
    shipped.chmod(0o755)
    artifacts = Path(directory) / 'stikjit-current'
    framework = artifacts / 'StikJIT.xcframework/ios-arm64/StikJIT.framework'
    framework.mkdir(parents=True)
    (framework / 'StikJIT').write_bytes(tested)
    (artifacts / 'identity.json').write_text(json.dumps({'binarySha256': recorded or hashlib.sha256(tested).hexdigest()}))
    return app, artifacts


def test_tested_stikjit():
    tested = image(b'\x1f\x20\x03\xd5' * 4, b'linker-signed')
    published = image(b'\x1f\x20\x03\xd5' * 4, b'sealed by the base delivery')
    assert published != tested
    with tempfile.TemporaryDirectory() as td:
        app, artifacts = stikjit(td, published, tested)
        result = base.restore_tested_stikjit(app, artifacts)
        shipped = app / base.STIKJIT
        assert shipped.read_bytes() == tested and shipped.stat().st_mode & 0o777 == 0o755
        assert result['publishedSha256'] == hashlib.sha256(published).hexdigest()
        assert result['testedSha256'] == hashlib.sha256(tested).hexdigest()
    for altered, recorded, message in ((image(b'\x00\x00\x80\xd2' * 4, b'sealed'), None, 'is not the tested one'),
                                       (published, 'f' * 64, 'not the one its identity names')):
        with tempfile.TemporaryDirectory() as td:
            app, artifacts = stikjit(td, altered, tested, recorded)
            try:
                base.restore_tested_stikjit(app, artifacts)
            except SystemExit as error:
                assert message in str(error), (message, str(error))
                assert (app / base.STIKJIT).read_bytes() == altered
                continue
            raise AssertionError('accepted: ' + message)


def test_workflow_variant():
    full = yaml.safe_load((ROOT / '.github/workflows/rpcs3-cell560-delivery.yml').read_text())
    args = ('0.0.10', 'RewindBox-.0.0.10.ipa', 'f' * 64, '559', 'docs/evidence/rpcs3-cell559-delivery.json')
    swap = variant.transform(full, *args)
    names = [s.get('name', '') for s in swap['jobs']['cold']['steps']]
    assert variant.COMPILE not in names and len(names) == len(full['jobs']['cold']['steps'])
    at = names.index(next(n for n in names if n.startswith('Use the published 0.0.10 application')))
    assert [n[:20] for n in names[at + 1:at + 5]] == [p[:20] for p in variant.CORE_STEPS]
    assert names[at + 5] == variant.FIRST_EMBED and names[at + 6] == variant.CORE_EMBED
    checks = [s.get('name', '') for s in swap['jobs']['checks']['steps']]
    pin = variant.pin_index(swap['jobs']['checks']['steps'])
    assert checks[pin + 1].startswith('Require the published 0.0.10 application')
    assert '--check' in swap['jobs']['checks']['steps'][pin + 1]['run']
    assert len(checks) == len(full['jobs']['checks']['steps']) + 1
    # The Core-swap script is a recipe input: changing it runs the delivery again.
    assert swap['on']['push']['paths'] == full['on']['push']['paths'] + [variant.SCRIPT]
    text = yaml.dump(swap, Dumper=variant.Dumper, sort_keys=False, width=120, allow_unicode=True)
    assert yaml.safe_load(text) == swap
    # Altered sources are refused: a missing Core step, Core steps after the compile, no compile.
    for mutate in ('drop core step', 'core after compile', 'no compile'):
        broken = copy.deepcopy(full)
        steps = broken['jobs']['cold']['steps']
        core = variant.core_indices(steps)
        if mutate == 'drop core step':
            del steps[core[1]]
        elif mutate == 'core after compile':
            moved = [steps[i] for i in core]
            for i in reversed(core):
                del steps[i]
            at = next(i for i, s in enumerate(steps) if s.get('name') == variant.COMPILE)
            steps[at + 1:at + 1] = moved
        else:
            steps[:] = [s for s in steps if s.get('name') != variant.COMPILE]
        try:
            variant.transform(broken, *args)
        except (AssertionError, ValueError):
            continue
        raise AssertionError('accepted: ' + mutate)


if __name__ == '__main__':
    test_extract()
    test_refusals()
    test_tested_stikjit()
    test_workflow_variant()
    print('PASS core-swap base preparation (stamping, receipts, 7 refusals), tested StikJIT (2 refusals) '
          'and workflow variant (3 refusals)')
