#!/usr/bin/env python3
"""Optional encrypted, authenticated, exact-input pre-embed DerivedData cache.

Every cache failure is a clean-build miss. This helper never builds, embeds,
exports or signs an application. The standard recipe always runs xcodebuild.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
DD = 'build/ios/DolphinDerivedData'
CACHE = '.ci-host-cache'
MAGIC = b'RBHOSTCACHE1\n'
REPO = 'TarbleFR/RewindBox'
REF = 'refs/heads/Claude'
WORKFLOW = REPO + '/.github/workflows/standard-delivery.yml@' + REF
MAX_BYTES = 24 * 1024 ** 3
MAX_FILES = 300000
SOURCE_ROOTS = ('lib', 'packages', 'assets', 'ios',
                'build/native_assets', 'build/stikjit-current')
FILES = ('pubspec.yaml', 'pubspec.lock', '.dart-defines.json', '.flutter-plugins-dependencies',
         '.dart_tool/package_config.json', '.dart_tool/package_graph.json',
         'build-utils/ipa_build_cache.py', 'build-utils/Gemfile.dolphin', 'build-utils/Gemfile.dolphin.lock')
POSTLINK = {'packages/rpcs3_internal_bridge/ios/Frameworks/libRPCS3Core.dylib',
            'packages/melonx_internal_bridge/ios/Frameworks/MeloNXCore.framework/MeloNXCore'}
CORE_INFO = 'packages/melonx_internal_bridge/ios/Frameworks/MeloNXCore.framework/Info.plist'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def require(value, reason='invalid cache'):
    if not value:
        raise ValueError(reason)


def trusted(env):
    return (env.get('GITHUB_REPOSITORY') == REPO and env.get('GITHUB_REF') == REF and
            env.get('GITHUB_EVENT_NAME') == 'push' and env.get('GITHUB_WORKFLOW_REF') == WORKFLOW and
            re.fullmatch('[0-9a-f]{40}', env.get('GITHUB_SHA', '')) is not None and
            env.get('GITHUB_RUN_ID', '').isdecimal() and env.get('GITHUB_RUN_ATTEMPT', '').isdecimal())


def secret(env):
    value = env.get('REWINDBOX_BUILD_CACHE_KEY', '')
    return value.encode() if len(value.encode()) >= 32 and trusted(env) else None


def hkdf(key, salt, info):
    extract = hmac.digest(salt, key, 'sha256')
    return hmac.digest(extract, info + b'\x01', 'sha256')


def outputs(env, **values):
    if env.get('GITHUB_OUTPUT'):
        with open(env['GITHUB_OUTPUT'], 'a') as handle:
            for key, value in values.items():
                handle.write(key + '=' + str(value).lower() + '\n')


def report(root, phase, status, started):
    # Fixed vocabulary only: no paths, tool output, key material or defines.
    path = root / 'build/delivery/host-cache.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        records = json.loads(path.read_bytes())
    except (OSError, ValueError):
        records = {}
    records[phase] = dict(status=status, seconds=round(time.monotonic() - started, 3))
    path.write_bytes(canonical(records) + b'\n')
    print(json.dumps(dict(hostCachePhase=phase, status=status)))


def normalized(name, data, build):
    # Changed raw bytes keep their fresh timestamps, including every version
    # stamp. Only known numeric delivery build fields leave the cache identity.
    if name == 'pubspec.yaml':
        return re.sub(rb'(?m)^(version:\s*\d+\.\d+\.\d+\+)\d+(\s*)$', rb'\g<1><delivery>\2', data)
    if name in ('.flutter-plugins-dependencies', '.dart_tool/package_config.json'):
        value = json.loads(data)
        field = 'date_created' if name == '.flutter-plugins-dependencies' else 'generated'
        if isinstance(value.get(field), str) and re.fullmatch(r'\d{4}-\d\d-\d\d[T ][0-9:.+Z-]+', value[field]):
            value[field] = '<generation-time>'
        return canonical(value)
    if (name.startswith('ios/') and name.endswith('/Info.plist') and len(Path(name).parts) == 3) or name == CORE_INFO:
        value = plistlib.loads(data)
        known = name in ('ios/Runner/Info.plist', CORE_INFO) or 'NSExtension' in value
        if known and str(value.get('CFBundleVersion')) == build and build.isdecimal():
            value['CFBundleVersion'] = '<delivery>'
        return plistlib.dumps(value, sort_keys=True)
    if name == 'ios/Runner.xcodeproj/project.pbxproj' and build.isdecimal():
        return re.sub(rb'(?m)^(\s*CURRENT_PROJECT_VERSION = )' + build.encode() + rb'(;\s*)$',
                      rb'\g<1><delivery>\2', data)
    if name in ('ios/Flutter/Generated.xcconfig', 'ios/Flutter/flutter_export_environment.sh') and build.isdecimal():
        return re.sub(rb'(FLUTTER_BUILD_NUMBER=)' + build.encode() + rb'(?=["\r\n]|$)', rb'\g<1><delivery>', data)
    return data


def source_files(root):
    """Include generated host/Pods and resolved external Dart package sources.

    Only the two reviewed post-link Core binaries are excluded. Linked native
    dependencies and all added headers/files remain inputs. Symlink targets are
    hashed, never restored.
    """
    # Generated projects/Pods must still have no link/embed phase for these
    # two runtime-only binaries. Unknown integration becomes a cache miss.
    for package in ('rpcs3_internal_bridge', 'melonx_internal_bridge'):
        spec = (root / f'packages/{package}/ios/{package}.podspec').read_text()
        require('s.preserve_paths' in spec and not re.search(r's\.vendored_(?:libraries|frameworks)\s*=', spec))
    for path in list((root / 'ios').rglob('project.pbxproj')) + list((root / 'ios/Pods/Target Support Files').rglob('*.sh')):
        data = path.read_bytes()
        require(b'libRPCS3Core.dylib' not in data and b'MeloNXCore.framework' not in data)
    roots = [root / name for name in SOURCE_ROOTS]
    config = json.loads((root / '.dart_tool/package_config.json').read_bytes())
    from urllib.parse import unquote, urlparse
    for package in config['packages']:
        uri = urlparse(package['rootUri'])
        require(uri.scheme in ('', 'file'))
        target = Path(unquote(uri.path))
        if not target.is_absolute():
            target = root / '.dart_tool' / target
        if not target.resolve().is_relative_to(root.resolve()):
            roots.append(target.resolve())
    found = {}
    visited = set()
    def visit(path):
        resolved = path.resolve(strict=True)
        if resolved.is_relative_to(root.resolve()) and str(resolved.relative_to(root.resolve())) in POSTLINK:
            return
        if resolved.is_dir():
            if resolved in visited:
                return
            visited.add(resolved)
            for entry in sorted(path.iterdir()):
                if entry.name not in ('.git', '__pycache__', '.DS_Store'):
                    # Per-delivery manifests and build outputs are not host inputs.
                    if entry == root / 'build-utils/delivery':
                        continue
                    visit(entry)
        else:
            require(resolved.is_file())
            name = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            if resolved.is_relative_to(root.resolve()) and str(resolved.relative_to(root.resolve())) == CORE_INFO:
                name = CORE_INFO
            found[name] = path
    for path in roots:
        if path.exists(): visit(path)
    for name in FILES:
        path = root / name
        if path.exists(): found[name] = path
    require(all((root / name).is_file() for name in ('pubspec.yaml', 'pubspec.lock', '.dart-defines.json',
                                                   'ios/Runner.xcodeproj/project.pbxproj')))
    return found


def compile_command(root):
    text = (root / '.github/workflows/standard-delivery.yml').read_text()
    return text.split('python3 build-utils/delivery_metrics.py xcode_build xcodebuild ', 1)[1].split(
        '2>&1 | tee', 1)[0].strip()


def inputs(root, env):
    environment = json.loads((root / 'build/delivery/environment.json').read_bytes())
    toolchain = {key: environment[key] for key in ('xcode', 'sdk', 'flutter', 'cocoaPods', 'ruby', 'macOS')}
    for key, argv in {'sdkBuild': ['xcrun', '--sdk', 'iphoneos', '--show-sdk-build-version'],
                      'swift': ['xcrun', 'swift', '--version'],
                      'clang': ['xcrun', 'clang', '--version'],
                      'developer': ['xcode-select', '-p']}.items():
        toolchain[key] = subprocess.check_output(argv, stderr=subprocess.DEVNULL, timeout=30).decode().strip()
    records, times = {}, {}
    for name, path in sorted(source_files(root).items()):
        data = path.read_bytes()
        records[name] = sha(normalized(name, data, env.get('BUILD_NUMBER', '')))
        # Mutate metadata only on regular inputs physically inside this checkout.
        if path.is_relative_to(root) and path.resolve().is_relative_to(root) and not path.is_symlink():
            times[name] = dict(sha256=sha(data), mtimeNS=path.stat().st_mtime_ns)
    compiler_env = {key: value for key, value in env.items() if key in (
        'DEVELOPER_DIR', 'SDKROOT', 'ARCHS', 'CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'LDFLAGS',
        'FLUTTER_ROOT', 'DART_VM_OPTIONS', 'DART_DEFINES', 'OTHER_LDFLAGS', 'OTHER_CFLAGS',
        'OTHER_CPLUSPLUSFLAGS', 'SWIFT_ACTIVE_COMPILATION_CONDITIONS')}
    identity = dict(schema=1, checkout=str(root.resolve()), inputs=records, toolchain=toolchain,
                    compileCommand=compile_command(root), compilerEnvironment=compiler_env)
    return dict(identity=identity, times=times)


def key_for(state, key):
    identity_key = hkdf(key, b'RewindBox host cache v1', b'identity')
    return 'ipa-host-v1-' + hmac.new(identity_key, canonical(state['identity']), 'sha256').hexdigest()


def origin(env):
    return {name: env[name] for name in ('GITHUB_REPOSITORY', 'GITHUB_REF', 'GITHUB_EVENT_NAME',
            'GITHUB_WORKFLOW_REF', 'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')}


def crypt(source, destination, key, iv, decrypt=False):
    # Derived per-blob AES key; no secret or subprocess command is logged.
    subprocess.run(['openssl', 'enc', '-aes-256-cbc', '-d' if decrypt else '-e',
                    '-K', key.hex(), '-iv', iv.hex(), '-in', str(source), '-out', str(destination)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)


def mac_file(path, key, initial=b''):
    value = hmac.new(key, initial, hashlib.sha256)
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''): value.update(block)
    return value.digest()


def pack(root, state, key, env):
    folder = root / CACHE
    target = folder / 'state.enc'
    require((root / DD).is_dir() and not (root / DD).is_symlink())
    with tempfile.TemporaryDirectory(dir=folder) as temporary:
        temporary = Path(temporary)
        raw = temporary / 'state.tar.gz'
        total, count = 0, 0
        with tarfile.open(raw, 'w:gz', compresslevel=1) as archive:
            manifest = canonical(dict(schema=1, identitySha256=sha(canonical(state['identity'])), times=state['times']))
            member = tarfile.TarInfo('manifest.json'); member.size = len(manifest); member.mode = 0o600
            import io
            archive.addfile(member, io.BytesIO(manifest))
            # Materialize only in-DerivedData links as regular files/directories.
            # The archive never contains symlinks, hardlinks or special files.
            ancestors = set()
            def add(path, name):
                nonlocal total, count
                resolved = path.resolve(strict=True)
                require(resolved.is_relative_to((root / DD).resolve()))
                require(resolved not in ancestors)
                count += 1
                require(count <= MAX_FILES)
                if resolved.is_dir():
                    ancestors.add(resolved)
                    member = tarfile.TarInfo(name); member.type = tarfile.DIRTYPE; member.mode = 0o700
                    archive.addfile(member)
                    for child in sorted(path.iterdir()): add(child, name + '/' + child.name)
                    ancestors.remove(resolved)
                else:
                    require(resolved.is_file())
                    total += resolved.stat().st_size
                    require(total <= MAX_BYTES)
                    member = tarfile.TarInfo(name); member.size = resolved.stat().st_size
                    member.mtime = resolved.stat().st_mtime; member.mode = 0o600 | (resolved.stat().st_mode & 0o111)
                    with resolved.open('rb') as handle: archive.addfile(member, handle)
            add(root / DD, 'DerivedData')
        require(raw.stat().st_size <= MAX_BYTES)
        salt, iv = os.urandom(32), os.urandom(16)
        enc = hkdf(key, salt, b'encryption'); auth = hkdf(key, salt, b'authentication')
        cipher = temporary / 'cipher'
        crypt(raw, cipher, enc, iv)
        header = canonical(dict(schema=1, key=key_for(state, key), identitySha256=sha(canonical(state['identity'])),
                                origin=origin(env), salt=salt.hex(), iv=iv.hex(), cipherBytes=cipher.stat().st_size))
        prefix = MAGIC + struct.pack('>I', len(header)) + header
        signed = temporary / 'signed'
        with signed.open('wb') as output:
            output.write(prefix)
            with cipher.open('rb') as handle: shutil.copyfileobj(handle, output)
        tag = mac_file(signed, auth)
        with signed.open('ab') as output: output.write(tag)
        signed.chmod(0o600)
        signed.replace(target)


def unpack(root, state, key):
    blob = root / CACHE / 'state.enc'
    require(blob.stat().st_size <= MAX_BYTES + 65536)
    with tempfile.TemporaryDirectory(dir=root / CACHE) as temporary:
        temporary = Path(temporary)
        cipher = temporary / 'cipher'
        with blob.open('rb') as source:
            require(source.read(len(MAGIC)) == MAGIC)
            length = struct.unpack('>I', source.read(4))[0]
            require(0 < length <= 16384)
            header_bytes = source.read(length); header = json.loads(header_bytes)
            require(header['schema'] == 1 and header['key'] == key_for(state, key) and
                    header['identitySha256'] == sha(canonical(state['identity'])) and trusted(header['origin']))
            size = header['cipherBytes']
            require(isinstance(size, int) and 0 < size <= MAX_BYTES and
                    blob.stat().st_size == len(MAGIC) + 4 + length + size + 32)
            salt, iv = bytes.fromhex(header['salt']), bytes.fromhex(header['iv'])
            require(len(salt) == 32 and len(iv) == 16)
            with cipher.open('wb') as output:
                remaining = size
                while remaining:
                    block = source.read(min(1024 * 1024, remaining)); require(bool(block))
                    output.write(block); remaining -= len(block)
            expected = source.read(32)
        prefix = MAGIC + struct.pack('>I', length) + header_bytes
        auth = hkdf(key, salt, b'authentication')
        value = hmac.new(auth, prefix, hashlib.sha256)
        with cipher.open('rb') as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''): value.update(block)
        require(hmac.compare_digest(value.digest(), expected))
        raw = temporary / 'state.tar.gz'
        crypt(cipher, raw, hkdf(key, salt, b'encryption'), iv, decrypt=True)
        stage = temporary / 'stage'; stage.mkdir()
        total, seen, manifest = 0, set(), None
        with tarfile.open(raw, 'r:gz') as archive:
            for member in archive:
                parts = PurePosixPath(member.name)
                require(member.name and not parts.is_absolute() and '..' not in parts.parts and
                        '\\' not in member.name and parts.parts[0] in ('manifest.json', 'DerivedData'), 'archive path')
                require(member.name not in seen, 'archive duplicate')
                require(member.isfile() or member.isdir(), 'archive type')
                require(not (parts.parts[0] == 'manifest.json' and member.name != 'manifest.json'))
                seen.add(member.name); total += member.size
                require(len(seen) <= MAX_FILES + 1 and 0 <= member.size <= MAX_BYTES and total <= MAX_BYTES, 'archive limits')
                destination = stage / member.name
                if member.isdir(): destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, destination.open('xb') as output:
                        shutil.copyfileobj(source, output)
                    destination.chmod(0o600 | (member.mode & 0o111))
                    os.utime(destination, (member.mtime, member.mtime))
            require('manifest.json' in seen and (stage / 'DerivedData').is_dir())
            require((stage / 'manifest.json').stat().st_size <= 64 * 1024 ** 2)
            manifest = json.loads((stage / 'manifest.json').read_bytes())
        require(manifest['schema'] == 1 and manifest['identitySha256'] == sha(canonical(state['identity'])))
        times = []
        for name, record in manifest['times'].items():
            # Membership in current inventory prevents writing unrelated paths.
            if name in state['times'] and state['times'][name]['sha256'] == record['sha256']:
                path = root / name
                require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()) and
                        digest(path) == record['sha256'] and isinstance(record['mtimeNS'], int) and record['mtimeNS'] >= 0)
                times.append((path, record['mtimeNS'], path.stat().st_mtime_ns))
        target = root / DD; backup = temporary / 'previous'
        target.parent.mkdir(parents=True, exist_ok=True)
        require(not target.is_symlink())
        if target.exists(): target.replace(backup)
        try:
            (stage / 'DerivedData').replace(target)
            for path, stamp, previous in times: os.utime(path, ns=(stamp, stamp))
        except Exception:
            if target.exists(): shutil.rmtree(target)
            if backup.exists(): backup.replace(target)
            for path, stamp, previous in times: os.utime(path, ns=(previous, previous))
            raise


def main(operation, root=ROOT, env=None):
    env = os.environ if env is None else env
    started = time.monotonic(); key = secret(env); folder = root / CACHE
    outputs(env, enabled=False, ready=False)
    if not key:
        report(root, operation, 'disabled', started)
        return
    try:
        folder.mkdir(exist_ok=True, mode=0o700)
        state_path = folder / 'current.json'
        if operation == 'prepare':
            state = inputs(root, env)
            state_path.write_bytes(canonical(state)); state_path.chmod(0o600)
            outputs(env, enabled=True, key=key_for(state, key))
            status = 'enabled'
        else:
            state = json.loads(state_path.read_bytes())
            require(state['identity'] == inputs(root, env)['identity'])
            if operation == 'restore':
                unpack(root, state, key); status = 'hit'
            else:
                pack(root, state, key, env); outputs(env, ready=True); status = 'snapshot'
    except Exception:
        # A failed authentication/extraction never supplies build products.
        if operation == 'restore':
            target = root / DD
            if target.is_symlink(): target.unlink()
            elif target.exists(): shutil.rmtree(target)
        if operation == 'snapshot':
            (folder / 'state.enc').unlink(missing_ok=True)
        status = 'miss'
    report(root, operation, status, started)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'restore', 'snapshot'))
    main(parser.parse_args().operation)
