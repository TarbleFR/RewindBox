#!/usr/bin/env python3
"""Small contract fixtures; no engine compilation, network call or IPA claim."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT


def helper_source(path):
    found = REPOSITORY / path
    return found.read_text() if found.is_file() else subprocess.check_output(
        ['git', 'show', 'HEAD:' + path], cwd=REPOSITORY, text=True)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Execute only the existing pure Mach-O and fingerprint helpers, avoiding the
# unrelated validators and the delivery module's import-time directory writes.
verify = types.ModuleType('verify_ipa')
verify.__dict__.update(struct=struct, ARM64=0x0100000C,
                       LOAD_DYLIB={0xC, 0x80000018, 0x8000001F, 0x20, 0x80000023})
tree = ast.parse(helper_source('packages/dolphin_internal_bridge/ci/verify_ipa.py'))
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in ['demand', 'macho']:
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<existing-macho>', 'exec'), verify.__dict__)
sys.modules['verify_ipa'] = verify
benchmark = types.ModuleType('delivery_benchmark')
benchmark.__dict__.update(ROOT=ROOT, struct=struct, json=json, sys=sys,
                          sha=lambda data: hashlib.sha256(data).hexdigest())
tree = ast.parse(helper_source('build-utils/delivery_benchmark.py'))
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'payload_fingerprint')
exec(compile(ast.Module(body=[node], type_ignores=[]), '<existing-fingerprint>', 'exec'), benchmark.__dict__)
sys.modules['delivery_benchmark'] = benchmark
engine = load('rewind588_engine', ROOT / '.github/diagnostics/rewind588_engine.py')
validator = load('validate_melonx_engine588_ipa', ROOT / 'build-utils/validate_melonx_engine588_ipa.py')
passed = 0


def reject(fn):
    global passed
    try:
        fn()
    except (AssertionError, KeyError, ValueError):
        passed += 1
    else:
        raise AssertionError('negative fixture was accepted')


def image(install_name, platform=2, exports=None, signature=b'A' * 16):
    exports = engine.SYMBOLS if exports is None else exports
    strings, symbols = b'\0', bytearray()
    for name in exports:
        symbols += struct.pack('<IBBHQ', len(strings), 0x0F, 1, 0, 0)
        strings += name.encode() + b'\0'
    section = struct.pack('<16s16sQQIIIIIIII', b'__text', b'__TEXT', 0, 16, 512, 2, 0, 0, 0, 0, 0, 0)
    segment = struct.pack('<II16sQQQQiiII', 0x19, 152, b'__TEXT', 0, 16, 512, 16, 5, 5, 1, 0) + section
    identity = struct.pack('<IIIIII', 0xD, 128, 24, 0, 0, 0) + install_name.encode().ljust(104, b'\0')
    version = struct.pack('<IIIIII', 0x32, 24, platform, 18 << 16, 26 << 16, 0)
    table = struct.pack('<IIIIII', 0x2, 24, 528, len(exports), 528 + len(symbols), len(strings))
    sig = struct.pack('<IIII', 0x1D, 16, 528 + len(symbols) + len(strings), len(signature))
    commands = segment + identity + version + table + sig
    header = struct.pack('<IiiIIIII', 0xFEEDFACF, 0x0100000C, 0, 6, 5, len(commands), 0, 0)
    return (header + commands).ljust(512, b'\0') + bytes(range(16)) + symbols + strings + signature


assert len(engine.INPUT_SHA256) == 57 and len(engine.EXPORTS) == 47 and len(engine.MARKERS) == 12
proof = json.loads(helper_source(engine.APPLE_PROOF))
assert hashlib.sha256(helper_source(engine.APPLE_PROOF).encode()).hexdigest() == engine.APPLE_PROOF_SHA256
assert (proof['host'], proof['run'], proof['artifact'], proof['artifactSha256']) == (
    engine.MELONX_SOURCE, engine.MELONX_RUN, engine.MELONX_ARTIFACT[0], engine.MELONX_ARTIFACT[1])
assert proof['iphoneSha256'] == engine.BINARY_SHA256['ios-arm64']
assert proof['simulatorSha256'] == engine.BINARY_SHA256['iossimulator-arm64']
passed += 1

# Fixed complete expected adaptation map, including same-count substitutions.
real_sha = engine.sha
engine.sha = lambda path: engine.INPUT_SHA256[path]
engine.check_inputs(dict(engine.INPUT_SHA256))
passed += 1
for change in ['omit', 'add', 'replace', 'digest']:
    inputs = dict(engine.INPUT_SHA256)
    key = next(iter(inputs))
    if change == 'omit':
        inputs.pop(key)
    elif change == 'add':
        inputs['extra.cs'] = '0' * 64
    elif change == 'replace':
        inputs['extra.cs'] = inputs.pop(key)
    else:
        inputs[key] = '0' * 64
    reject(lambda: engine.check_inputs(inputs))
engine.sha = lambda path: '0' * 64
reject(lambda: engine.check_inputs(dict(engine.INPUT_SHA256)))
engine.sha = real_sha

original = image('@rpath/Ryujinx.Library.dylib')
signed = image(engine.PACKAGED_ID, signature=b'B' * 16)
assert engine.normalized_payload_fingerprint(original) == engine.normalized_payload_fingerprint(signed)
assert benchmark.payload_fingerprint(original) != benchmark.payload_fingerprint(signed)
engine.check_image(original, 'ios-arm64')
passed += 1
reject(lambda: engine.check_image(image(engine.PACKAGED_ID, platform=7), 'ios-arm64'))
reject(lambda: engine.check_image(image(engine.PACKAGED_ID, exports=engine.SYMBOLS[:-1]), 'ios-arm64'))
changed = bytearray(signed)
changed[512] ^= 1
assert engine.normalized_payload_fingerprint(changed) != engine.normalized_payload_fingerprint(original)
passed += 1

with tempfile.TemporaryDirectory(prefix='melonx588-contract-') as temp:
    engine.ROOT = Path(temp)
    engine.NEW = engine.ROOT / 'dist/melonx'
    directory = engine.NEW / 'ios-arm64'
    directory.mkdir(parents=True)
    (directory / 'Ryujinx.Library.dylib').write_bytes(original)
    engine.BINARY_SHA256 = dict(engine.BINARY_SHA256, **{'ios-arm64': hashlib.sha256(original).hexdigest()})
    pin = {'revision': 'fixture-only'}
    (engine.ROOT / 'build-utils/melonx').mkdir(parents=True)
    (engine.ROOT / 'build-utils/melonx/source.json').write_text(json.dumps(pin))
    identity = dict(host=engine.MELONX_SOURCE, runtimeIdentifier='ios-arm64', source=pin,
                    sha256=engine.BINARY_SHA256['ios-arm64'], exports=engine.EXPORTS,
                    adaptations=dict(engine.INPUT_SHA256), embeddedSessionDeviceVerified=False)
    (directory / 'identity.json').write_text(json.dumps(identity))
    engine.sha = lambda path: engine.INPUT_SHA256[path]
    engine.engine_identity()
    passed += 1
    for key, value in [('host', 'wrong'), ('runtimeIdentifier', 'iossimulator-arm64'),
                       ('source', {}), ('sha256', '0' * 64), ('exports', engine.EXPORTS[:-1])]:
        wrong = dict(identity, **{key: value})
        (directory / 'identity.json').write_text(json.dumps(wrong))
        reject(engine.engine_identity)
    (directory / 'identity.json').write_text(json.dumps(identity))
    root = 'Payload/NeoStation.app/'
    def packaged(data, name='packaged.zip'):
        path = engine.ROOT / name
        native = dict(sourceCoreIdentity=identity,
                      compiledPayloadFingerprints={'MeloNXCore': benchmark.payload_fingerprint(data)})
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr(root + 'MeloNX-native-identity.json', json.dumps(native))
            archive.writestr(root + 'Frameworks/MeloNXCore.framework/MeloNXCore', data)
        return path
    with zipfile.ZipFile(packaged(signed)) as archive:
        assert validator.engine_ipa(archive, root)['originalPayloadMatched'] is True
        passed += 1
    # The counterfeit packaging receipt follows the altered binary. It must
    # still fail against the original fixed sections, not pass by self-check.
    with zipfile.ZipFile(packaged(changed, 'altered.zip')) as archive:
        reject(lambda: validator.engine_ipa(archive, root))
    with zipfile.ZipFile(packaged(original, 'wrong-id.zip')) as archive:
        reject(lambda: validator.engine_ipa(archive, root))

state = dict(head_sha=engine.MELONX_SOURCE, path=engine.MELONX_WORKFLOW, status='completed', conclusion='success')
jobs = dict(total_count=1, jobs=[dict(conclusion='success', steps=[dict(name=name, conclusion='success') for name in engine.ENGINE_STEPS])])
artifact = dict(id=engine.MELONX_ARTIFACT_ID, name=engine.MELONX_ARTIFACT_NAME,
                size_in_bytes=engine.MELONX_ARTIFACT_BYTES, expired=False,
                workflow_run=dict(id=engine.MELONX_RUN, head_sha=engine.MELONX_SOURCE))
def api(endpoint):
    if '/jobs?' in endpoint:
        return jobs
    return artifact if endpoint.startswith('actions/artifacts/') else state
engine.api = api
engine.engine_run()
passed += 1
state['head_sha'] = 'wrong'
reject(engine.engine_run)
state['head_sha'] = engine.MELONX_SOURCE
state['conclusion'] = 'failure'
reject(engine.engine_run)
state['conclusion'] = 'success'
artifact['expired'] = True
reject(engine.engine_run)
artifact['expired'] = False
jobs['jobs'][0]['steps'].pop()
reject(engine.engine_run)
print(json.dumps(dict(result='passed', contractFixtures=passed,
                     engineCompiled=False, artifactDownloaded=False, physicalDeviceTested=False,
                     inputs={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in
                             ['.github/diagnostics/rewind588_engine.py',
                              'build-utils/validate_melonx_engine588_ipa.py',
                              'test/melonx_engine588_test.py']})))
