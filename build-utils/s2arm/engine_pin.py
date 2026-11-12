#!/usr/bin/env python3
"""The S2Arm engine pin (build-utils/s2arm/engine-pin.json): the pinned-engine component `s2arm` of the common recipe.

Three producer artifacts, one pin (schema of standard_delivery.py, `engine_pin_errors`):
  engine   s2arm-engine.yml   artifact s2arm-engine-framework-<head>: S2ArmEngine.framework.zip, NS2Pro.framework.zip,
                              s2arm-engine-identity.json and the licence and notice texts under licenses/
  prepare  s2arm-core.yml     artifact S2ArmPrepare-<head>: S2ArmPrepare.xcframework.zip, sha256.txt, undefined.txt,
                              S2ArmPrepare-identity.json
  sysdata  s2arm-prepare.yml  artifact s2arm-sysdata-macOS-<head>: the system data tree and its SHA256SUMS

  engine_pin.py pin --meta META.json --engine ZIP --prepare ZIP --sysdata ZIP [--out PIN]
        writes the pin from the three downloaded artifacts and the API facts of their runs (see META below)
  engine_pin.py verify ZIP --pin PIN
        the verifier the recipe runs on every artifact (components.s2arm.verifier): the artifact is the pinned one
  engine_pin.py snippet [--pin PIN]
        prints the components.s2arm manifest component that names this pin (a helper, not a manifest)
  engine_pin.py exports ENGINE_ARTIFACT.zip
        prints exportsList (the exact exported symbols of the engine images) for the component
  engine_pin.py install-prepare [--root DIR]
        unzips the verified S2ArmPrepare.xcframework where the engine bridge podspec vendors it, before pod install

META = {producer: {run, attempt, artifact, name, bytes, sha256, headSha, expiresAt}} for engine, prepare, sysdata
(the pin job of s2arm-engine.yml writes it from the API; sha256 is the artifact digest GitHub reports).
Pin fields beyond the common ones: producers.<name>.members {archive member: sha256} (what the artifact holds),
producers.<name>.unpack (archives the recipe unpacks), identity (what other validators read from the identity file:
sourceIdentity.s2arm_commit and the licences record).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import plistlib
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / 'build-utils' / 's2arm' / 'engine-pin.json'
HEX64 = re.compile(r'[0-9a-f]{64}')
FRAMEWORKS = ('S2ArmEngine', 'NS2Pro')
ENGINE_ZIPS = tuple(f'{name}.framework.zip' for name in FRAMEWORKS)
ENGINE_IDENTITY = 's2arm-engine-identity.json'
LICENSES = 'licenses/'
LICENSE_MANIFEST = LICENSES + 'license-sources.json'
PREPARE_ZIP = 'S2ArmPrepare.xcframework.zip'
PREPARE_MEMBERS = (PREPARE_ZIP, 'sha256.txt', 'undefined.txt', 'S2ArmPrepare-identity.json')
PREPARE_XCFRAMEWORK = 'S2ArmPrepare.xcframework'
PREPARE_LIBRARY = 'libS2ArmPrepare.a'
PREPARE_PATCHES = 'build-utils/s2arm/prepare/patches'
BRIDGE_FRAMEWORKS = 'packages/s2arm_engine_bridge/ios/Frameworks'
SYSDATA_SUMS = 'SHA256SUMS'
SYSDATA_SOURCES = 'SOURCES.tsv'
SYSDATA_TOPS = ('systemdata/', 'licenses/')
SYSDATA_TZ_LICENCE = 'licenses/tzdata/LICENSE'
SYSDATA_FONT_LICENCES = 'licenses/fonts/OFL'
BUNDLE_SUFFIXES = ('.app', '.appex', '.framework', '.xcframework', '.bundle', '.dylib')
DIRECT_CHAIN = 'S2ArmDirectChain.txt'
MACHO_MAGICS = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xce',
                b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf', b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'}
PRODUCERS = {
    'engine': ('.github/workflows/s2arm-engine.yml', 'unpack'),
    'prepare': ('.github/workflows/s2arm-core.yml', 'prepare'),
    'sysdata': ('.github/workflows/s2arm-prepare.yml', 'sysdata'),
}
BRANCH = 'work/s2arm-switch2-prototype-20261110'


class PinError(SystemExit):
    pass


def require(condition, message):
    if not condition:
        raise PinError('S2Arm engine pin: ' + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def on_path():
    for part in ('build-utils', 'packages/dolphin_internal_bridge/ci', '.github/diagnostics'):
        if str(ROOT / part) not in sys.path:
            sys.path.insert(0, str(ROOT / part))


def safe_zip(archive, label):
    names = archive.namelist()
    require(len(names) == len(set(names)) and archive.testzip() is None, f'{label}: duplicate or corrupt member')
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        require(entry.filename and not path.is_absolute() and '..' not in path.parts and '\\' not in entry.filename and
                not stat.S_ISLNK(entry.external_attr >> 16), f'{label}: unsafe member {entry.filename}')
    return names


def read_zip(raw, label):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in safe_zip(archive, label) if not name.endswith('/')}


# --- Contents of each artifact -------------------------------------------------------------------------------

def licence_errors(texts, record=None, commit=None):
    on_path()
    import embed_legal_bundle as gate
    errors = gate.s2arm_notice_errors(texts)
    if errors:
        return errors
    manifest = json.loads(texts[gate.S2ARM_NOTICE_MANIFEST])
    if record is not None and not (record.get('sha256') == sha(texts[gate.S2ARM_NOTICE_MANIFEST]) and
                                   record.get('files') == len(texts)):
        errors.append(f'{gate.S2ARM_NOTICE_MANIFEST} or the number of texts is not the recorded one')
    if commit is not None and manifest['s2arm']['commit'] != commit:
        errors.append(f"the texts are of S2Arm {manifest['s2arm']['commit']}, the engine of {commit}")
    return errors


def framework_files(name, raw):
    """One engine framework archive: its files, one Mach-O image (arm64 iOS dylib with install name
    @rpath/<name>.framework/<name>, linking the system and the other engine framework only)."""
    on_path()
    from verify_ipa import macho
    prefix = f'{name}.framework/'
    files = {}
    for member, data in read_zip(raw, f'{name}.framework.zip').items():
        require(member.startswith(prefix), f'{name}.framework.zip member outside {prefix}: {member}')
        relative = member[len(prefix):]
        parts = PurePosixPath(relative).parts
        require(not any(part.endswith(('.framework', '.appex', '.app')) for part in parts[:-1]) and
                not relative.endswith('.dylib'), f'Nested bundle or library in {name}.framework: {relative}')
        files[member] = data
    require(prefix + name in files and prefix + 'Info.plist' in files, f'{name}.framework lacks its executable or Info.plist')
    info = plistlib.loads(files[prefix + 'Info.plist'])
    require(isinstance(info, dict) and info.get('CFBundleExecutable') == name and info.get('CFBundlePackageType') == 'FMWK',
            f'{name}.framework/Info.plist is not this framework')
    images = sorted(path for path, data in files.items() if data[:4] in MACHO_MAGICS)
    require(images == [prefix + name], f'{name}.framework must hold one Mach-O image, its executable: {images}')
    image = macho(files[prefix + name])
    require(image['fileType'] == 6 and image['id'] == f'@rpath/{name}.framework/{name}',
            f'{name} is not a dylib with install name @rpath/{name}.framework/{name}')
    others = {f'@rpath/{other}.framework/{other}' for other in FRAMEWORKS if other != name}
    for dependency in image['dependencies']:
        require(dependency['path'].startswith(('/usr/lib/', '/System/Library/')) or dependency['path'] in others,
                f"{name} links {dependency['path']}: an engine framework links only the system and the other one")
    return files


def sums_listing(raw, label):
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise PinError(f'S2Arm engine pin: {label} is not UTF-8 text') from None
    listing = {}
    for line in text.splitlines():
        digest, separator, path = line.partition('  ')
        require(separator and HEX64.fullmatch(digest) and path and path not in listing,
                f'{label}: malformed or repeated line {line!r}')
        listing[path] = digest
    require(listing and text.endswith('\n'), f'{label} is empty or not newline-terminated')
    return listing


def check_sysdata(files, label='system data'):
    """The tree {path: bytes} (with its SHA256SUMS): exactly the listed files with their digests, only data and licences,
    no executable or bundle, the open font and time zone licence texts beside the data."""
    require(SYSDATA_SUMS in files, f'{label} has no {SYSDATA_SUMS}')
    listed = sums_listing(files[SYSDATA_SUMS], f'{label}/{SYSDATA_SUMS}')
    present = set(files) - {SYSDATA_SUMS}
    missing, extra = sorted(set(listed) - present), sorted(present - set(listed))
    require(not missing and not extra, f'{label} differs from its {SYSDATA_SUMS}: missing {missing[:5]}, not listed {extra[:5]}')
    changed = sorted(path for path, value in listed.items() if sha(files[path]) != value)
    require(not changed, f'{label} files differ from {SYSDATA_SUMS}: {changed[:5]}')
    for path in listed:
        parts = PurePosixPath(path).parts
        require((path == SYSDATA_SOURCES or path.startswith(SYSDATA_TOPS)) and '..' not in parts and '\\' not in path and
                not any(part.startswith('.') or part.endswith(BUNDLE_SUFFIXES) for part in parts),
                f'{label}: unexpected path {path}')
        require(files[path][:4] not in MACHO_MAGICS, f'{label}: Mach-O image {path}')
    folded = {}
    for path in listed:
        folded.setdefault(path.casefold(), []).append(path)
    require(not [paths for paths in folded.values() if len(paths) > 1], f'{label}: paths that differ only by case')
    fonts = [path for path in listed if path.startswith('systemdata/fonts/') and path.endswith('.bfttf')]
    licences = sorted(path for path in listed if path.startswith('licenses/'))
    require(fonts, f'{label} has no shared font (systemdata/fonts/*.bfttf)')
    require(SYSDATA_TZ_LICENCE in licences and any(path.startswith(SYSDATA_FONT_LICENCES) for path in licences),
            f'{label}/licenses lacks the time zone licence or the open font licence texts')
    require(SYSDATA_SOURCES in listed, f'{label} has no {SYSDATA_SOURCES}')
    return dict(files=len(listed), fonts=len(fonts), licences=licences)


def xcframework_library(raw):
    """S2ArmPrepare.xcframework.zip: one static iOS arm64 library and its headers; returns {path: bytes}."""
    prefix = PREPARE_XCFRAMEWORK + '/'
    files = {}
    for member, data in read_zip(raw, PREPARE_ZIP).items():
        require(member.startswith(prefix), f'{PREPARE_ZIP} member outside {prefix}: {member}')
        files[member[len(prefix):]] = data
    require('Info.plist' in files, f'{PREPARE_XCFRAMEWORK} has no Info.plist')
    info = plistlib.loads(files['Info.plist'])
    libraries = info.get('AvailableLibraries') if isinstance(info, dict) else None
    require(isinstance(libraries, list) and info.get('CFBundlePackageType') == 'XFWK' and len(libraries) == 1 and
            isinstance(libraries[0], dict), f'{PREPARE_XCFRAMEWORK} must describe exactly one library')
    entry = libraries[0]
    identifier = entry.get('LibraryIdentifier')
    require(isinstance(identifier, str) and re.fullmatch(r'[A-Za-z0-9_.-]+', identifier) and
            entry.get('LibraryPath') == PREPARE_LIBRARY and entry.get('SupportedPlatform') == 'ios' and
            'SupportedPlatformVariant' not in entry and entry.get('SupportedArchitectures') == ['arm64'],
            f'{PREPARE_XCFRAMEWORK} is not one {PREPARE_LIBRARY} for iOS arm64 devices')
    library = f'{identifier}/{PREPARE_LIBRARY}'
    headers = sorted(path for path in files if path.startswith(identifier + '/Headers/'))
    require(set(files) == {'Info.plist', library, *headers} and all(path.endswith('.h') for path in headers),
            f'{PREPARE_XCFRAMEWORK} holds other files than its Info.plist, {library} and its headers')
    require(files[library][:8] == b'!<arch>\n', f'{library} is not a static library')
    return files, library


def engine_facts(files):
    names = set(files)
    texts = {name for name in names if name.startswith(LICENSES)}
    require(sorted(names - texts) == sorted(ENGINE_ZIPS + (ENGINE_IDENTITY,)) and LICENSE_MANIFEST in texts,
            f'The engine artifact must hold exactly {", ".join(ENGINE_ZIPS)}, {ENGINE_IDENTITY} and {LICENSE_MANIFEST} '
            f'with its texts: {sorted(names)[:12]}')
    inner = {}
    for name in FRAMEWORKS:
        inner.update(framework_files(name, files[f'{name}.framework.zip']))
    identity = json.loads(files[ENGINE_IDENTITY])
    require(isinstance(identity, dict) and {'run', 'attempt', 'head_sha', 's2arm_commit', 'files', 'licenses'} <= set(identity),
            f'Incomplete {ENGINE_IDENTITY}')
    require(identity['files'] == {name: sha(files[name]) for name in ENGINE_ZIPS}, f'{ENGINE_IDENTITY} files differ from the archives')
    record = identity['licenses']
    texts = {name[len(LICENSES):]: files[name] for name in texts}
    errors = licence_errors(texts, record, identity['s2arm_commit'])
    require(not errors, 'the engine licence texts are refused: ' + '; '.join(errors))
    require(DIRECT_CHAIN in {path.split('/', 1)[1] for path in inner}, f'S2ArmEngine.framework has no {DIRECT_CHAIN}')
    return dict(members={name: sha(files[name]) for name in ENGINE_ZIPS}, binaries={path: data for path, data in inner.items()},
                identity=identity, licences=dict(path='Legal/S2Arm', manifest='license-sources.json',
                                                 sha256=record['sha256'], files=record['files']))


def prepare_facts(files):
    require(sorted(files) == sorted(PREPARE_MEMBERS), f'The preparation artifact must hold exactly {", ".join(PREPARE_MEMBERS)}')
    sums = sums_listing(files['sha256.txt'], 'sha256.txt')
    require(set(sums) == {PREPARE_ZIP, PREPARE_LIBRARY} and sums[PREPARE_ZIP] == sha(files[PREPARE_ZIP]),
            'sha256.txt must give the xcframework archive (this one) and the library')
    inner, library = xcframework_library(files[PREPARE_ZIP])
    require(sha(inner[library]) == sums[PREPARE_LIBRARY], f'{library} is not the library sha256.txt measured')
    identity = json.loads(files['S2ArmPrepare-identity.json'])
    require(isinstance(identity, dict) and identity.get('component') == PREPARE_XCFRAMEWORK and
            identity.get('sha256') == sums, 'S2ArmPrepare-identity.json does not describe this archive')
    left = sorted(name for name in files['undefined.txt'].decode('utf-8', errors='replace').split() if name.startswith('_rb_s2arm_'))
    require(not left, f'undefined.txt leaves rb_s2arm_* entry points undefined: {left}')
    # The RewindBox patch series the library's S2Arm rewriter was built with (s2arm-core.yml), name and SHA-256 in order:
    # the pin records it (identity.preparePatches, copied into S2Arm-native-identity.json) beside the engine's own series.
    patches = identity.get('patches', [])
    require(isinstance(patches, list) and all(isinstance(p, dict) and set(p) == {'name', 'sha256'} and
                                              str(p['name']).endswith('.patch') and HEX64.fullmatch(str(p['sha256']))
                                              for p in patches), 'S2ArmPrepare-identity.json patches must be [{name, sha256}]')
    return dict(members={PREPARE_ZIP: sha(files[PREPARE_ZIP])}, identity=identity, patches=patches)


def prepare_patch_series(root=ROOT):
    """build-utils/s2arm/prepare/patches of this checkout, as S2ArmPrepare-identity.json records it."""
    folder = Path(root) / PREPARE_PATCHES
    return [dict(name=path.name, sha256=sha(path.read_bytes())) for path in sorted(folder.glob('*.patch'))]


def sysdata_facts(files):
    check_sysdata(files)
    sources = {}
    for line in files[SYSDATA_SOURCES].decode('utf-8', errors='replace').splitlines()[1:]:
        part, _, value = line.partition('\t')
        sources[part] = value
    return dict(members={SYSDATA_SUMS: sha(files[SYSDATA_SUMS])}, sources=sources)


def classify(files):
    if ENGINE_ZIPS[0] in files:
        return 'engine'
    if PREPARE_ZIP in files:
        return 'prepare'
    if SYSDATA_SUMS in files:
        return 'sysdata'
    raise PinError('S2Arm engine pin: the artifact is none of the engine, preparation or system data artifacts')


FACTS = {'engine': engine_facts, 'prepare': prepare_facts, 'sysdata': sysdata_facts}


def binary_entries(kind, files, facts):
    """The pin's binaries of one artifact: path below dist/s2arm/<subdir>, sha256 and bytes (fingerprint of a Mach-O)."""
    on_path()
    from delivery_benchmark import payload_fingerprint
    if kind == 'engine':
        found = {}
        for path, data in facts['binaries'].items():
            entry = dict(sha256=sha(data), bytes=len(data))
            if data[:4] in MACHO_MAGICS:
                entry['fingerprint'] = payload_fingerprint(data)
            found[path] = entry
        return found
    if kind == 'prepare':
        return {f'prepare/{PREPARE_ZIP}': dict(sha256=sha(files[PREPARE_ZIP]), bytes=len(files[PREPARE_ZIP]))}
    return {f'sysdata/{SYSDATA_SUMS}': dict(sha256=sha(files[SYSDATA_SUMS]), bytes=len(files[SYSDATA_SUMS]))}


# --- pin / verify ------------------------------------------------------------------------------------------

def build_pin(meta, archives):
    producers, binaries, zips, identity = {}, {}, {}, {}
    prepare_patches = None
    for name, raw in archives.items():
        files = read_zip(raw, name)
        kind = classify(files)
        require(kind == name, f'the {name} archive is the {kind} artifact')
        facts = FACTS[kind](files)
        described = dict(meta[name])
        require(described['sha256'] == sha(raw) and described['bytes'] == len(raw), f'{name}: the archive is not the one META describes')
        entry = dict(run=described['run'], attempt=described['attempt'], artifact=described['artifact'],
                     name=described['name'], bytes=len(raw), sha256=sha(raw), headSha=described['headSha'],
                     expiresAt=described.get('expiresAt'), members=facts['members'])
        if kind == 'engine':
            entry['unpack'] = list(ENGINE_ZIPS)
            ident = facts['identity']
            require(ident['run'] == entry['run'] and ident['head_sha'] == entry['headSha'],
                    f'{ENGINE_IDENTITY} names another run or commit than its producer')
            identity = dict(sourceIdentity=ident, licenses=facts['licences'])
        elif kind == 'prepare':
            entry['subdir'] = 'prepare'
            prepare_patches = facts['patches']
            require(prepare_patches == prepare_patch_series(),
                    f'the preparation library was built with {prepare_patches}, this checkout has {prepare_patch_series()} '
                    f'in {PREPARE_PATCHES}')
        else:
            entry['subdir'] = 'sysdata'
            entry['sources'] = facts['sources']
        producers[name] = entry
        zips[name] = sha(raw)
        binaries.update(binary_entries(kind, files, facts))
    image = binaries['S2ArmEngine.framework/S2ArmEngine']
    if prepare_patches is not None:
        identity = dict(identity, preparePatches=prepare_patches)
    return dict(status='verified', packagedFingerprint=image['fingerprint'], producers=producers, zips=zips,
                binaries=dict(sorted(binaries.items())), identity=identity)


def verify(archive, pin_path):
    pin = json.loads(Path(pin_path).read_text())
    raw = Path(archive).read_bytes()
    files = read_zip(raw, 'artifact')
    kind = classify(files)
    failures = []
    if pin.get('status') != 'verified':
        failures.append('the pin is not verified')
    entry = (pin.get('producers') or {}).get(kind) or {}
    if sha(raw) != entry.get('sha256') or len(raw) != entry.get('bytes'):
        failures.append(f"the {kind} artifact is not the pinned one ({sha(raw)} against {entry.get('sha256')})")
    try:
        facts = FACTS[kind](files)
    except PinError as error:
        failures.append(str(error))
        facts = None
    if facts:
        if facts['members'] != entry.get('members'):
            failures.append(f"the {kind} artifact members differ from the pin: {facts['members']}")
        for path, expected in binary_entries(kind, files, facts).items():
            if pin.get('binaries', {}).get(path) != expected:
                failures.append(f'{path} is not the pinned file')
        if kind == 'engine':
            ident = facts['identity']
            if ident['run'] != entry.get('run') or ident['head_sha'] != entry.get('headSha'):
                failures.append(f'{ENGINE_IDENTITY} names another run or commit than the pin')
            recorded = {key: value for key, value in (pin.get('identity') or {}).items() if key != 'preparePatches'}
            if recorded != dict(sourceIdentity=ident, licenses=facts['licences']):
                failures.append('the engine identity or licence record differs from the pin')
        if kind == 'prepare' and (pin.get('identity') or {}).get('preparePatches') != facts['patches']:
            failures.append('the preparation patch series differs from the pin (identity.preparePatches)')
        if kind == 'sysdata' and facts['sources'] != entry.get('sources'):
            failures.append('SOURCES.tsv differs from the pin')
    if failures:
        print('S2Arm engine pin: REFUSED\n- ' + '\n- '.join(failures))
        return 1
    print(f"S2Arm engine pin: OK ({kind}, run {entry['run']}, artifact {entry['artifact']}, {len(raw)} bytes)")
    return 0


def exports_list(archive):
    """exportsList of the engine images in an engine artifact: {image path: [exported symbols]} (dyld export trie)."""
    on_path()
    sys.path.insert(0, str(ROOT / '.github' / 'diagnostics'))
    import standard_delivery as sd
    files = read_zip(Path(archive).read_bytes(), 'artifact')
    require(classify(files) == 'engine', 'exports reads the engine artifact')
    facts = engine_facts(files)
    return {f'Frameworks/{path}': sd.engine_exports(data) for path, data in facts['binaries'].items()
            if data[:4] in MACHO_MAGICS}


def snippet(pin_path):
    """components.s2arm for the next common draft (a helper: the manifest is the main session's to write). Add
    `exportsList` from `engine_pin.py exports <engine artifact>` if the delivery should pin the exported symbols."""
    subdirs = {'engine': None, 'prepare': 'prepare', 'sysdata': 'sysdata'}
    return {'s2arm': {
        'mode': 'pinned-engine', 'pin': 'build-utils/s2arm/engine-pin.json', 'verifier': 'build-utils/s2arm/engine_pin.py',
        'identityFile': 'S2Arm-native-identity.json',
        'frameworks': ['Frameworks/S2ArmEngine.framework', 'Frameworks/NS2Pro.framework'],
        'image': 'Frameworks/S2ArmEngine.framework/S2ArmEngine', 'sideImages': [],
        'extensions': ['S2ArmJITHelper.appex'], 'legalFolders': ['Legal/S2Arm'],
        'checks': ['build-utils/s2arm/check_app.py'],
        'producers': {name: dict({'workflow': PRODUCERS[name][0], 'branch': BRANCH},
                                 **({'subdir': subdirs[name]} if subdirs[name] else {})) for name in PRODUCERS},
        'podLibraries': ['s2arm_engine_bridge'],
        'appResources': [{'path': 'S2ArmSystemData/SHA256SUMS', 'binary': f'sysdata/{SYSDATA_SUMS}'}],
        'pinSha256': hashlib.sha256(Path(pin_path).read_bytes()).hexdigest(),
    }}


def install_prepare(root):
    """Unzip the pinned xcframework (dist/s2arm/prepare) where the bridge podspec vendors it."""
    root = Path(root)
    raw = (root / 'dist/s2arm/prepare' / PREPARE_ZIP).read_bytes()
    pin = json.loads((root / 'build-utils/s2arm/engine-pin.json').read_text())
    require(pin['binaries'][f'prepare/{PREPARE_ZIP}']['sha256'] == sha(raw), f'{PREPARE_ZIP} is not the pinned one')
    target = root / BRIDGE_FRAMEWORKS
    require(not target.exists() or not any(target.iterdir()), f'{BRIDGE_FRAMEWORKS} is not empty')
    files = read_zip(raw, PREPARE_ZIP)
    xcframework_library(raw)
    for member, data in files.items():
        path = target / member
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(f'S2Arm engine pin: {PREPARE_XCFRAMEWORK} installed in {BRIDGE_FRAMEWORKS} ({len(files)} files)')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('pin')
    p.add_argument('--meta', required=True)
    for name in PRODUCERS:
        p.add_argument('--' + name, required=True)
    p.add_argument('--out', default=str(PIN))
    v = sub.add_parser('verify')
    v.add_argument('artifact')
    v.add_argument('--pin', default=str(PIN))
    s = sub.add_parser('snippet')
    s.add_argument('--pin', default=str(PIN))
    e = sub.add_parser('exports')
    e.add_argument('artifact')
    i = sub.add_parser('install-prepare')
    i.add_argument('--root', default=str(ROOT))
    arguments = parser.parse_args(argv)
    if arguments.command == 'verify':
        return verify(arguments.artifact, arguments.pin)
    if arguments.command == 'snippet':
        print(json.dumps(snippet(arguments.pin), indent=2))
        return 0
    if arguments.command == 'exports':
        print(json.dumps(exports_list(arguments.artifact), indent=2))
        return 0
    if arguments.command == 'install-prepare':
        return install_prepare(arguments.root)
    meta = json.loads(Path(arguments.meta).read_text())
    pin = build_pin(meta, {name: Path(getattr(arguments, name)).read_bytes() for name in PRODUCERS})
    Path(arguments.out).write_text(json.dumps(pin, indent=2) + '\n')
    print(json.dumps(pin, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
