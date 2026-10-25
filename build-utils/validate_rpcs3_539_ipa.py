#!/usr/bin/env python3
"""Retain the exact successful 536 logger proof while verifying the new IPA payload."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
from rpcs3cell539_delivery import CORE_SOURCE, CORE_RUN, HOST, validate_rpc_core_identity
from delivery_benchmark import payload_fingerprint
from verify_ipa import macho
sys.path.insert(0,str(ROOT/"test"))
from rpcs3_retention536_test import input_hashes as retention_inputs

RECEIPT = 'RPCS3-cell539-identity.json'
CORE = 'Frameworks/libRPCS3Core.dylib'


def inspect(core, images, receipt):
    validate_rpc_core_identity(receipt['coreIdentity'])
    retention=receipt['hostRetentionProof']
    assert retention['passed'] and not retention['physicalDeviceTested']
    assert retention['source']=='5fdc4c4feb729918eb1aaa96ac50bce470dc7e6c'
    assert retention['run']=='40186697206'
    expected=json.loads((ROOT/'docs/evidence/rpcs3-cell536-delivery-ci.json').read_text())['ciValidation']['retention536-tests.json']
    assert retention==expected
    assert retention['inputs']==retention_inputs()
    assert retention['results']['before']['returncode']==-6 and retention['results']['after']['returncode']==0
    assert any(b'RANGELOCKPROF \x00' in data and b'COREPROF_RESILIENCE \x00' in data for data in images.values()), 'Host retention filter is not compiled'

    assert receipt['coreRun'] == CORE_RUN and receipt['coreSource'] == CORE_SOURCE
    assert receipt['productionMinimalSPULinkerEnabled'] is False
    assert receipt['physicalDeviceTested'] is False
    assert receipt['physicalPerformanceMeasured'] is False
    assert payload_fingerprint(core) == receipt['compiledCorePayloadFingerprint']
    image = macho(core)
    assert image['platform'] == 2 and '_rpcs3_ios_set_compiler_budget_api' in image['definedSymbols']
    assert b'REWINDBOX_RPCS3_MEMORY_AUDIT_V1' in core
    for marker in (b'SAVESTATE_MOUNT534', b'COREPROF SHADERCOST534', b'COREPROF SHADERCFG536', b'COREPROF SHADERSTALL538', b'COREPROF FRAMEPROF527', b'partial_fxo_not_resumed=1'):
        assert marker in core, marker
    storage = next(data for path,data in images.items() if path.endswith('neo_swap.framework/neo_swap'))
    assert b'process_private_verified_readback' in storage and b'sourceDeviceSyncSkipped' in storage
    assert b'JITCPU context=game_boot title=' in core, 'Missing compiled GoW3 target diagnostic'
    for marker in (b'RSX_ACQUIRE waiting_after_recovery', b'FREEZE_DUMP snapshot', b'SAVESTATE_RESTORE '):
        assert marker in core, marker
    assert any(b'freeze_snapshot' in data and b'rsx_acquire' in data and b'savestate_restore' in data for data in images.values()), 'Complete freeze and restore milestones are not linked'
    assert any('_NeoSwap_GetCompilerAPI' in macho(data)['definedSymbols'] for data in images.values()), 'Compiler broker is not linked'
    assert any(b'rpcs3_ios_set_compiler_budget_api' in data and b'JITMEM ' in data for data in images.values()), 'Optional Core binder and memory log bridge are not linked'
    for relative, digest in receipt['hostInputSHA256'].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest, relative
    assert set(receipt['hostInputSHA256']) == HOST


def embed(app, core_path, identity_path):
    original = core_path.read_bytes()
    identity = json.loads(identity_path.read_text())
    validate_rpc_core_identity(identity)
    assert identity['sha256'] == hashlib.sha256(original).hexdigest()
    receipt = {'schemaVersion': 1, 'coreSource': CORE_SOURCE, 'coreRun': CORE_RUN,
        'hostRetentionProof': json.loads((ROOT/'build/delivery/retention536-tests.json').read_bytes()),
        'coreIdentity': identity, 'compiledCorePayloadFingerprint': payload_fingerprint(original),
        'hostInputSHA256': {relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() for relative in sorted(HOST)},
        'productionMinimalSPULinkerEnabled': False, 'physicalDeviceTested': False,
        'physicalPerformanceMeasured': False, 'gow3BootAndVmaSourceVerified': True}
    images = {}
    for path in app.rglob('*'):
        if path.is_file():
            data = path.read_bytes()
            if data[:4] == b'\xcf\xfa\xed\xfe':
                images[str(path.relative_to(app))] = data
    inspect((app / CORE).read_bytes(), images, receipt)
    (app / RECEIPT).write_text(json.dumps(receipt, indent=2) + '\n')
    return {'result': 'passed', 'sourceArtifactSHA256': identity['sha256'],
            'compiledCorePayloadFingerprint': receipt['compiledCorePayloadFingerprint']}


def validate(ipa, build):
    with zipfile.ZipFile(ipa) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), 'Duplicate ZIP entry'
        roots = [n.removesuffix('Info.plist') for n in names if n.startswith('Payload/') and len(n.split('/')) == 3 and n.endswith('.app/Info.plist')]
        assert len(roots) == 1
        root = roots[0]
        info = plistlib.loads(archive.read(root + 'Info.plist'))
        assert str(info['CFBundleVersion']) == str(build)
        receipt = json.loads(archive.read(root + RECEIPT))
        images = {}
        for name in names:
            if name.startswith(root + 'Frameworks/') or name == root + info['CFBundleExecutable']:
                if not name.endswith('/'):
                    data = archive.read(name)
                    if data[:4] == b'\xcf\xfa\xed\xfe':
                        images[name.removeprefix(root)] = data
        inspect(archive.read(root + CORE), images, receipt)
    return {'result': 'passed', 'build': build,
        'ipaSHA256': hashlib.sha256(ipa.read_bytes()).hexdigest(),
        'coreSource': CORE_SOURCE, 'coreRun': CORE_RUN,
        'sourceArtifactSHA256': receipt['coreIdentity']['sha256'],
        'compiledCorePayloadFingerprint': receipt['compiledCorePayloadFingerprint'],
        'sharedCompilerBrokerLinked': True, 'optionalCoreBinderLinked': True,
        'productionMinimalSPULinkerEnabled': False, 'physicalDeviceTested': False,
        'physicalPerformanceMeasured': False, 'gow3BootAndVmaSourceVerified': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipa', type=Path, nargs='?')
    parser.add_argument('--embed', type=Path)
    parser.add_argument('--core-binary', type=Path)
    parser.add_argument('--core-identity', type=Path)
    parser.add_argument('--build-number', type=int, default=538)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.embed:
        assert not args.ipa and args.core_binary and args.core_identity
        record = embed(args.embed, args.core_binary, args.core_identity)
    else:
        assert args.ipa
        record = validate(args.ipa, args.build_number)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
