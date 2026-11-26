"""Playlist labels from the components authenticated by the current delivery."""
import json
from pathlib import Path
import re
import subprocess


def _repository_name(source):
    return source['repository'].rstrip('/').rsplit('/', 1)[-1].removesuffix('.git')


def _melonx_release(root, revision):
    # The framework plist has the packaging version. Read the release settings
    # from the same upstream Git object as the native producer, if available.
    checkout = root / '.native-sources/MeloNX'
    if not checkout.is_dir():
        return None
    project = 'src/MeloNX/MeloNX.xcodeproj/project.pbxproj'
    result = subprocess.run(['git', '-C', str(checkout), 'show', f'{revision}:{project}'],
                            capture_output=True, text=True)
    if result.returncode:
        return None
    for settings in re.findall(r'buildSettings\s*=\s*\{([^{}]*)\};\s*name\s*=\s*Release;', result.stdout):
        if re.search(r'\bINFOPLIST_FILE\s*=\s*"?MeloNX/Info\.plist"?;', settings):
            version = re.search(r'\bMARKETING_VERSION\s*=\s*"?(\d+(?:\.\d+)+)"?;', settings)
            if version:
                return version[1]
    return None


def native_engines(app: Path, manifest: dict, identity: dict, root: Path) -> dict:
    components = identity['components']
    specs = manifest['components']
    armsx2 = components['armsx2']['identity']
    dolphin = components['dolphin']['identity']
    rpcs3 = json.loads((root / specs['rpcs3']['pin']).read_bytes())
    melonx = json.loads((app / 'MeloNX-native-identity.json').read_bytes())['sourceCoreIdentity']

    # RewindBox sometimes updates its port without changing upstream. Keep the
    # original engine producer's revision even when the application is rebuilt.
    melonx_release = _melonx_release(root, melonx['source']['revision'])
    dolphin_name = _repository_name(dolphin)
    engines = {
        'armsx2': {
            'name': _repository_name(armsx2),
            'version': f"{armsx2['release'].removeprefix('iOSv')} · git {armsx2['host_commit'][:8]}",
        },
        'dolphin': {
            'name': 'DolphiniOS' if dolphin_name == 'dolphin-ios' else dolphin_name,
            'version': f"git {dolphin['source_revision'][:8]} · RewindBox {dolphin['host_commit'][:8]}",
        },
        'rpcs3': {
            'name': rpcs3['component'].upper(),
            'version': f"Build {rpcs3['build']} · git {components['rpcs3']['coreSource'][:8]}",
        },
        'melonx': {
            'name': f"RSwitch ({_repository_name(melonx['source'])})",
            'version': (melonx_release or f"git {melonx['source']['revision'][:8]}")
                       + f" · RewindBox {melonx['host'][:8]}",
        },
    }

    if 'xenia' in components:
        pin = json.loads((root / specs['xenia']['pin']).read_bytes())
        source = json.loads((root / 'build-utils/xenia/source.json').read_bytes())
        name = _repository_name(source)
        # The upstream IPA attestation recorded by the producer names a release
        # and its commit. Use its label only for the binary pinned to that commit.
        attestation = re.match(
            rf'{re.escape(name)} (\d+(?:\.\d+)+) \(\d+\) IPA attestation commitShort=([0-9a-f]{{7,40}})\b',
            source.get('revision_evidence', ''),
        )
        version = f"git {pin['source'][:8]}"
        if attestation and source['revision'] == pin['source'] and pin['source'].startswith(attestation[2]):
            version = attestation[1]
        engines['xenia'] = {
            'name': name,
            'version': f"{version} · SHA-256 {pin['binaries']['ios-arm64']['sha256'][:8]}",
        }
    if 's2arm' in components:
        spec = specs['s2arm']
        receipt = json.loads((app / spec['identityFile']).read_bytes())
        engine = receipt['sourceIdentity']
        notice = receipt['licenses']
        provenance = json.loads((app / notice['path'] / notice['manifest']).read_bytes())
        engines['s2arm'] = {
            'name': provenance['engine'],
            'version': f"git {engine['s2arm_commit'][:8]} · RewindBox {engine['head_sha'][:8]}",
        }
    return engines
