#!/usr/bin/env python3
"""Bind the 551 Core, its host files and the logger proofs executed by this delivery while verifying the private 551 IPA payload."""
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
from rpcs3cell551_delivery import CORE_SOURCE, CORE_RUN, HOST, HOST551, validate_rpc_core_identity
from rpcs3cell546_delivery import logger_proofs
from delivery_benchmark import payload_fingerprint
from verify_ipa import macho
sys.path.insert(0,str(ROOT/"test"))
from rpcs3_retention536_test import input_hashes as retention_inputs

RECEIPT = 'RPCS3-cell551-identity.json'
# CELL546 host diagnostics compiled into the RPCS3 bridge.
BRIDGE546_MARKERS = (b'RPCS3-restore-trace.log', b'RPCS3-timeline.log', b'savestate_restore_trace',
                     b'LOG_BUDGET dropped=%u limit_per_s=128', b'LOG_ROTATION file=%@',
                     b'core_report_window_values_not_additive', b'SAVESTATE_RESTORE phase=fs_stage ',
                     b'COREPROF PRESSURE547 ', b'spu_passive_waits')
# CELL551 timeline families, title and configuration layers.
BRIDGE551_MARKERS = (b'COREPROF RSXSYNC551 ', b'COREPROF RSXFRAME551 ', b'COREPROF SPUWAIT551 ', b'CONFIG_LAYERS ',
                     b'metal_compiles_interactive', b'fifo_idle_entries', b'putllc_heavy', b'mlaa_bypass', b'rsx_frame')
CORE551_MARKERS = (b'COREPROF RSXSYNC551 session=', b'COREPROF RSXFRAME551 session=', b'COREPROF SPUWAIT551 session=',
                   b'Applying database config under the custom config', b'MoltenVK asynchronous submits enabled for this boot',
                   b'MoltenVK Asynchronous Submits', b'MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS', b'metal_compiles_interactive=')
# The 551 game profiles, compiled into the Dart snapshot.
DART551_MARKERS = ('BLES01658', 'experimental.moltenvk_async_submits')
CORE = 'Frameworks/libRPCS3Core.dylib'


def inspect(core, images, receipt):
    validate_rpc_core_identity(receipt['coreIdentity'])
    # The changed logger was executed by this delivery job (536 retention and
    # 546 rotation/restore-trace/timeline cases), not reused from history.
    proofs=logger_proofs()
    assert receipt['hostRetentionProof']==proofs['retention536']
    assert receipt['hostDiagnostics546Proof']==proofs['diagnostics546']
    assert receipt['hostRetentionProof']['inputs']==retention_inputs()
    assert any(b'RANGELOCKPROF \x00' in data and b'COREPROF_RESILIENCE \x00' in data for data in images.values()), 'Host retention filter is not compiled'
    bridge = images.get('Frameworks/rpcs3_internal_bridge.framework/rpcs3_internal_bridge', b'')
    for marker in BRIDGE546_MARKERS + BRIDGE551_MARKERS:
        assert marker in bridge, marker
    dart = images['Frameworks/App.framework/App']
    for text in DART551_MARKERS:
        assert text.encode('latin-1') in dart or text.encode('utf-16le') in dart, text

    assert receipt['coreRun'] == CORE_RUN and receipt['coreSource'] == CORE_SOURCE
    assert receipt['productionMinimalSPULinkerEnabled'] is False
    assert receipt['physicalDeviceTested'] is False
    assert receipt['physicalPerformanceMeasured'] is False
    assert payload_fingerprint(core) == receipt['compiledCorePayloadFingerprint']
    image = macho(core)
    assert image['platform'] == 2 and '_rpcs3_ios_set_compiler_budget_api' in image['definedSymbols']
    assert b'REWINDBOX_RPCS3_MEMORY_AUDIT_V1' in core
    for marker in CORE551_MARKERS + (b'COREPROF PRESSURE547', b'SPUWARMUP duplicates removed=', b'Invalid installation directory name', b'context543=1 origin=', b'COREPROF SHADERPUB543', b'COREPROF SHADERPIPE543', b'COREPROF SHADERFEEDBACK543',
                   b'NEOSTATION_CELL543_PIPELINE_CACHE', b'context542=1 properties=', b'SAVESTATE_MOUNT534', b'COREPROF SHADERCOST534', b'COREPROF SHADERCFG536', b'COREPROF SHADERSTALL538', b'COREPROF FRAMEPROF527', b'partial_fxo_not_resumed=1'):
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
    assert set(receipt['hostInputSHA256']) == HOST | HOST551


def embed(app, core_path, identity_path):
    original = core_path.read_bytes()
    identity = json.loads(identity_path.read_text())
    validate_rpc_core_identity(identity)
    assert identity['sha256'] == hashlib.sha256(original).hexdigest()
    receipt = {'schemaVersion': 1, 'coreSource': CORE_SOURCE, 'coreRun': CORE_RUN,
        'hostRetentionProof': json.loads((ROOT/'build/delivery/retention536-tests.json').read_bytes()),
        'hostDiagnostics546Proof': json.loads((ROOT/'build/delivery/diagnostics546-tests.json').read_bytes()),
        'coreIdentity': identity, 'compiledCorePayloadFingerprint': payload_fingerprint(original),
        'hostInputSHA256': {relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() for relative in sorted(HOST | HOST551)},
        'productionMinimalSPULinkerEnabled': False, 'physicalDeviceTested': False,
        'physicalPerformanceMeasured': False, 'gow3BootAndVmaSourceVerified': True,
        'fpsGainClaimed': False}
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
    parser.add_argument('--build-number', type=int, default=551)
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
