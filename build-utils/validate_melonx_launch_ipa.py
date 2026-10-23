"""Verify the actual signed IPA contains the reviewed launch ABI and policies."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packages/dolphin_internal_bridge/ci'))
from verify_ipa import macho

def entitlements(binary):
    count = struct.unpack_from('<I', binary, 16)[0]; cursor = 32
    for _ in range(count):
        command, size = struct.unpack_from('<II', binary, cursor)
        if command == 0x1d:
            offset, length = struct.unpack_from('<II', binary, cursor + 8)
            blob = binary[offset:offset + length]
            magic, total, entries = struct.unpack_from('>III', blob)
            assert magic == 0xfade0cc0 and total <= len(blob)
            for i in range(entries):
                kind, relative = struct.unpack_from('>II', blob, 12 + i * 8)
                if kind == 5:
                    tag, n = struct.unpack_from('>II', blob, relative)
                    assert tag == 0xfade7171
                    return plistlib.loads(blob[relative + 8:relative + n])
        cursor += size
    return {}

def validate(ipa):
    with zipfile.ZipFile(ipa) as archive:
        assert archive.testzip() is None
        roots = [n[:-len('Info.plist')] for n in archive.namelist() if n.startswith('Payload/') and len(n.split('/')) == 3 and n.endswith('.app/Info.plist')]
        assert len(roots) == 1; root = roots[0]
        info = plistlib.loads(archive.read(root + 'Info.plist')); assert info['CFBundleVersion'] == '514'
        receipt = json.loads(archive.read(root + 'MeloNX-native-identity.json'))
        core = archive.read(root + 'Frameworks/MeloNXCore.framework/MeloNXCore')
        symbols = set(macho(core)['definedSymbols'])
        required = {'_neostation_melonx_diagnostics_abi', '_neostation_melonx_diagnostics', '_neostation_melonx_prepare_jit'}
        assert required <= symbols, required - symbols
        for path in ['native/melonx/EmbeddedLaunchPreflight.cs', 'native/melonx/EmbeddedLaunchDiagnostics.cs',
            'native/melonx/EmbeddedRuntime.cs', 'native/melonx/EmbeddedSession.cs',
            'native/melonx/EmbeddedDarwinSignals.cs', 'native/melonx/EmbeddedBootstrap.cs',
            'build-utils/melonx/adapt_session.py', 'build-utils/melonx/adapt_runtime.py']:
            assert receipt['sourceCoreIdentity']['adaptations'][path] == hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), path
        bridge = archive.read(root + 'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
        for value in [b'launchDiagnostic', b'launchPreflight', b'neostation_melonx_prepare_jit']:
            assert value in bridge, value
        dart = archive.read(root + 'Frameworks/App.framework/App')
        for value in [b'[MeloNX:launch]', b'jitMappingConfirmed', b'firstMetalFramePresented', b'contentPreflight']:
            assert value in dart, value
        declared = entitlements(archive.read(root + info['CFBundleExecutable']))
        for key in ['com.apple.developer.kernel.increased-memory-limit', 'com.apple.developer.kernel.extended-virtual-addressing']:
            assert declared.get(key) is True, key
        assert not any(Path(n).suffix.lower() in {'.nsp', '.xci', '.nro', '.nso'} or Path(n).name.lower() in {'prod.keys', 'title.keys'} for n in archive.namelist())
        return {'result': 'passed', 'build': 514, 'ipaSHA256': hashlib.sha256(ipa.read_bytes()).hexdigest(),
            'newLaunchExports': sorted(required), 'declaredMemoryEntitlements': declared,
            'signedUserInstallationEntitlementsVerified': False, 'physicalDeviceTested': False,
            'privateFrameworks': sorted(receipt['frameworks']), 'personalContentBundled': False}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('ipa', type=Path); parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(); report = validate(args.ipa)
    args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS packaged MeloNX launch ABI, diagnostics, signed declared entitlements and absence of personal content.')
