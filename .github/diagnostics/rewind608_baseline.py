"""Build608: exact delivered607 plus an explicitly frozen RA session delta.

The scope is written by the integrator before committing, never by CI. It binds
every changed tracked byte and file mode to the delivered source. It does not
turn the previous private IPA metadata into a new download verification.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD = 608
BASE = '68552e27770b114ecc9a347600816132794b4fae'
CONFIG = 'build-utils/rewind608-source-scope.json'
DECLARATIONS = 'docs/evidence/retro-achievements-session-declarations-2026-11-01.json'
INVENTORY = 'build-utils/rewind608-native-inventory.json'
PUBLIC_KEY = 'build-utils/delivery-608-recipient.pem'
PRODUCTS = ('lib', 'native', 'packages', 'assets', 'pubspec.yaml', 'pubspec.lock')
PRESERVED = ('native', 'assets', 'packages/rpcs3_internal_bridge',
             'packages/melonx_internal_bridge', 'packages/melonx_jit_helper',
             'packages/neo_swap', 'build-utils/rpcs3', 'build-utils/melonx',
             '.github/diagnostics/rpcs3runtime607_core.py',
             '.github/diagnostics/rewind607_delivery.py',
             '.github/diagnostics/rewind606_engine.py',
             '.github/diagnostics/rewind606_baseline.py')
BASELINE = dict(build=607, source=BASE, run=41246903346, job=124672229557,
                attempt=1, ipaBytes=189741645,
                ipaSHA256='817a196dd6452c1b6fc876b07f2337d09ade5a148751888c136d0e12dd90d2d4')
DECLARATION_PATHS = (
    'pubspec.yaml',
    'packages/armsx2_internal_bridge/ios/armsx2_internal_bridge.podspec',
    'packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec',
    'packages/libretro_internal_bridge/ios/libretro_internal_bridge.podspec',
    'packages/retro_achievements_session/pubspec.yaml',
    'packages/retro_achievements_session/ios/retro_achievements_session.podspec',
)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, timeout=120).strip()


def safe_path(name):
    path = Path(name)
    require(bool(name) and not path.is_absolute() and '..' not in path.parts and
            '\\' not in name and ':' not in name, 'Unsafe source path: ' + name)
    return ROOT / path


def original(path):
    entry = git('ls-tree', BASE, '--', path)
    if not entry:
        return None, None
    mode, kind, _ = entry.partition('\t')[0].split()
    require(kind == 'blob', 'Expected a baseline file: ' + path)
    raw = subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT, timeout=120)
    return raw, mode


def current(path):
    target = safe_path(path)
    if not target.exists():
        return None, None
    require(target.is_file() and not target.is_symlink(), 'Non-regular delivery input: ' + path)
    return target.read_bytes(), '100755' if target.stat().st_mode & stat.S_IXUSR else '100644'


def change_record(path):
    before, before_mode = original(path)
    after, after_mode = current(path)
    return dict(before=sha(before) if before is not None else None,
                after=sha(after) if after is not None else None,
                modeBefore=before_mode, modeAfter=after_mode)


def changed_paths(include_untracked=False):
    paths = set(git('diff', '--no-renames', '--name-only', BASE, '--').splitlines())
    if include_untracked:
        paths.update(git('ls-files', '--others', '--exclude-standard').splitlines())
    paths.discard(CONFIG)
    return sorted(paths)


def is_product(path):
    return any(path == root or path.startswith(root + '/') for root in PRODUCTS)


def freeze():
    """Explicit local integration operation; CI must never call this."""
    require(not os.environ.get('CI') and not os.environ.get('GITHUB_ACTIONS'),
            'The reviewed scope may not be generated in CI')
    require(git('branch', '--show-current') == 'Claude', 'Freeze only the Claude checkout')
    for path in PRESERVED:
        require(not git('diff', '--name-only', BASE, '--', path),
                'Retained607 component changed: ' + path)
    prior_path = 'docs/evidence/achievement-translation-declarations-2026-10-31.json'
    prior_raw = safe_path(prior_path).read_bytes()
    prior = json.loads(prior_raw)
    locked = safe_path('pubspec.lock').read_bytes()
    require(sha(locked) == prior['pubspec_lock_sha256'],
            'This scoped local-plugin review does not authorize a different package lock')
    declarations = {}
    for path in DECLARATION_PATHS:
        change = change_record(path)
        require(change['after'] is not None and change['before'] != change['after'],
                'Expected a changed session dependency declaration: ' + path)
        declarations[path] = {key: change[key] for key in ('before', 'after')}
    followup = dict(schema=1, review_date='2026-11-01',
        scope='Central RetroAchievements session: local workspace plugin and its three native consumers only. No hosted package or engine source selection changes.',
        baseline_inventory=prior_path, baseline_inventory_sha256=sha(prior_raw),
        pubspec_lock_sha256=sha(locked), declarations=declarations,
        dependency_changes=dict(local_plugin='retro_achievements_session',
            host_license='LICENSE.md (repository GPL-3.0); podspec declares GPL-3.0',
            external_packages_added=[], existing_sdk_dependency='Flutter',
            system_frameworks=['Foundation', 'Security'],
            native_consumers=['armsx2_internal_bridge', 'dolphin_internal_bridge', 'libretro_internal_bridge']),
        complete_corresponding_source_attested=False)
    safe_path(DECLARATIONS).parent.mkdir(parents=True, exist_ok=True)
    safe_path(DECLARATIONS).write_text(json.dumps(followup, indent=2) + '\n')
    paths = changed_paths(include_untracked=True)
    require(all(p.startswith(('.github/', 'build-utils/', 'test/', 'tools/', 'docs/', 'lib/', 'packages/')) or
                p in ('pubspec.yaml', 'pubspec.lock', 'AGENTS.md') for p in paths),
            'Unexpected source scope; inspect before freezing')
    source = {p: change_record(p) for p in paths}
    require(source and any(p.startswith('packages/retro_achievements_session/') for p in source),
            'The central session plugin is absent from the reviewed source delta')
    value = dict(schema=1, build=BUILD, baseline=dict(BASELINE, tree=git('rev-parse', BASE + '^{tree}')),
        sourceDelta=source, productDelta={p: v for p, v in source.items() if is_product(p)},
        declarationsSHA256=sha(safe_path(DECLARATIONS).read_bytes()),
        nativeInventorySHA256=sha(safe_path(INVENTORY).read_bytes()),
        publicKeySHA256=sha(safe_path(PUBLIC_KEY).read_bytes()),
        scopeGeneratedInCI=False, physicalDeviceTested=False)
    safe_path(CONFIG).write_text(json.dumps(value, indent=2) + '\n')
    return dict(result='frozen-for-review', sourcePaths=len(source),
                productPaths=len(value['productDelta']), path=CONFIG)


def pins():
    value = json.loads(safe_path(CONFIG).read_bytes())
    require(value['schema'] == 1 and value['build'] == BUILD and value['scopeGeneratedInCI'] is False,
            'Missing reviewed608 source scope')
    require(value['baseline'] == dict(BASELINE, tree=git('rev-parse', BASE + '^{tree}')),
            'Wrong delivered607 product baseline')
    require(value['sourceDelta'] and value['productDelta'], 'Empty reviewed608 delta')
    return value


def source_contract():
    value = pins()
    require(os.environ.get('BUILD_NUMBER', '608') == '608' and
            os.environ.get('GITHUB_REF_NAME', 'Claude') == 'Claude', 'Wrong delivery branch/build')
    require(git('rev-parse', 'HEAD') == os.environ.get('GITHUB_SHA', git('rev-parse', 'HEAD')),
            'Checkout differs from triggering source')
    require(not git('diff', '--name-only') and git('write-tree') == git('rev-parse', 'HEAD^{tree}'),
            'Tracked checkout changed after commit')
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    require(set(changed_paths()) == set(value['sourceDelta']), 'Unreviewed source addition/deletion')
    for path, record in value['sourceDelta'].items():
        require(change_record(path) == record, 'Reviewed source bytes or file mode changed: ' + path)
    require(value['productDelta'] == {p: r for p, r in value['sourceDelta'].items() if is_product(p)},
            'Product delta does not cover the exact source changes')
    for path in PRESERVED:
        require(not git('diff', '--name-only', BASE, 'HEAD', '--', path),
                'Retained607 component changed: ' + path)
    for path, key in ((DECLARATIONS, 'declarationsSHA256'), (INVENTORY, 'nativeInventorySHA256'),
                      (PUBLIC_KEY, 'publicKeySHA256')):
        require(sha(safe_path(path).read_bytes()) == value[key], 'Delivery review input changed: ' + path)
    require(safe_path(PUBLIC_KEY).read_text().startswith('-----BEGIN PUBLIC KEY-----'),
            'Delivery608 needs the recipient public key')
    require(json.loads(safe_path('build-utils/armsx2/source.json').read_bytes())['abi_version'] == 9,
            'Build608 requires the ARMSX2 launch-policy ABI9')
    sys.path[:0] = [str(ROOT / 'build-utils'), str(ROOT / 'build-utils/melonx')]
    from helper_initialization import verify as verify_helper
    from collect_build_source_evidence import repository_inputs
    verify_helper()
    repository_inputs(ROOT)
    return dict(result='passed', build=BUILD, source=git('rev-parse', 'HEAD'),
        tree=git('rev-parse', 'HEAD^{tree}'), baseline=value['baseline'],
        productDelta=value['productDelta'], reviewedSourceScopeSHA256=sha(safe_path(CONFIG).read_bytes()),
        productTrees={p: git('rev-parse', 'HEAD:' + p) for p in PRODUCTS},
        rebuiltForDelivery=['Dolphin', 'ARMSX2', 'Flutter application'],
        retainedFrom607=['RPCS3 ABI30', 'MeloNX', 'libretro core binaries'],
        physicalDeviceTested=False)


def verify():
    sys.path.insert(0, str(ROOT / 'build-utils'))
    from delivery_contract_memo import reuse
    return reuse('608-source', source_contract)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['freeze', 'verify'])
    args = parser.parse_args()
    print(json.dumps(globals()[args.operation](), indent=2))
