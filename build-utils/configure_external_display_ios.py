#!/usr/bin/env python3
"""Declare the external display scene role in the generated iOS host (idempotent).

Adds `UIWindowSceneSessionRoleExternalDisplayNonInteractive` to the scene
manifest of ios/Runner/Info.plist so that UIKit hands an AirPlay or adapter
screen to `NeoExternalDisplaySceneDelegate` (packages/external_display). The
application role written by Flutter's template is never touched, and
`UIApplicationSupportsMultipleScenes` keeps its value unless the
`--multiple-scenes` variant is requested (the variant to try on the device only
if the external scene is never delivered). See docs/external-display-universal.md
section 7.
"""
from __future__ import annotations

import argparse
import os
import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_KEY = 'UIApplicationSceneManifest'
CONFIGURATIONS_KEY = 'UISceneConfigurations'
MULTIPLE_SCENES_KEY = 'UIApplicationSupportsMultipleScenes'
APPLICATION_ROLE = 'UIWindowSceneSessionRoleApplication'
EXTERNAL_ROLE = 'UIWindowSceneSessionRoleExternalDisplayNonInteractive'
CONFIGURATION_NAME = 'neostation-external-display'
DELEGATE_CLASS = 'NeoExternalDisplaySceneDelegate'
MULTIPLE_SCENES_VARIABLE = 'NEOSTATION_EXTERNAL_DISPLAY_MULTIPLE_SCENES'


def external_configuration() -> dict:
    """The single configuration UIKit uses for the external, non-interactive role."""
    return {
        'UISceneClassName': 'UIWindowScene',
        'UISceneConfigurationName': CONFIGURATION_NAME,
        'UISceneDelegateClassName': DELEGATE_CLASS,
    }


def multiple_scenes_requested(flag: bool) -> bool:
    return bool(flag) or os.environ.get(MULTIPLE_SCENES_VARIABLE, '').strip() == '1'


def configure(info_path: Path, multiple_scenes: bool = False) -> list[str]:
    """Add the external role to the Info.plist at `info_path`; return what was done.

    The file is rewritten only when its bytes change, so a second run is a no-op.
    A host without a scene manifest or without the application role is refused:
    inventing a manifest would change the application's own life cycle.
    """
    if not info_path.is_file():
        raise SystemExit(f'Generate the clean Flutter iOS host first: {info_path} is missing')
    original = info_path.read_bytes()
    info = plistlib.loads(original)
    if not isinstance(info, dict):
        raise SystemExit(f'{info_path} is not a dictionary')
    manifest = info.get(MANIFEST_KEY)
    if not isinstance(manifest, dict):
        raise SystemExit(f'{MANIFEST_KEY} missing in {info_path}: the host is not scene based; refusing to add one')
    configurations = manifest.get(CONFIGURATIONS_KEY)
    if not isinstance(configurations, dict):
        raise SystemExit(f'{MANIFEST_KEY}.{CONFIGURATIONS_KEY} missing or invalid in {info_path}')
    application = configurations.get(APPLICATION_ROLE)
    if not isinstance(application, list) or not application:
        raise SystemExit(f'{APPLICATION_ROLE} missing in {info_path}: refusing to configure a host without its application scene')
    existing = configurations.get(EXTERNAL_ROLE)
    if existing is not None and not isinstance(existing, list):
        raise SystemExit(f'Invalid existing {EXTERNAL_ROLE} in {info_path}; refusing to overwrite it')

    actions: list[str] = []
    expected = [external_configuration()]
    if existing is None:
        configurations[EXTERNAL_ROLE] = expected
        actions.append(f'{EXTERNAL_ROLE}: added {CONFIGURATION_NAME} ({DELEGATE_CLASS})')
    elif existing == expected:
        actions.append(f'{EXTERNAL_ROLE}: already {CONFIGURATION_NAME} ({DELEGATE_CLASS}), unchanged')
    else:
        configurations[EXTERNAL_ROLE] = expected
        actions.append(f'{EXTERNAL_ROLE}: replaced {len(existing)} configuration(s) with {CONFIGURATION_NAME} ({DELEGATE_CLASS})')
    actions.append(f'{APPLICATION_ROLE}: untouched ({len(application)} configuration(s))')

    current = manifest.get(MULTIPLE_SCENES_KEY)
    if multiple_scenes:
        if current is True:
            actions.append(f'{MULTIPLE_SCENES_KEY}: already true')
        else:
            manifest[MULTIPLE_SCENES_KEY] = True
            actions.append(f'{MULTIPLE_SCENES_KEY}: set to true (device variant requested)')
    else:
        shown = 'absent' if current is None else str(current).lower()
        actions.append(f'{MULTIPLE_SCENES_KEY}: left unchanged ({shown})')

    rendered = plistlib.dumps(info, fmt=plistlib.FMT_XML, sort_keys=False)
    if rendered != original:
        info_path.write_bytes(rendered)
        actions.append(f'wrote {info_path}')
    else:
        actions.append(f'{info_path} already configured; nothing written')
    return actions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--ios', type=Path, default=ROOT / 'ios',
                        help='generated iOS host directory (default: ios/)')
    parser.add_argument('--multiple-scenes', action='store_true',
                        help=f'set {MULTIPLE_SCENES_KEY} to true (also {MULTIPLE_SCENES_VARIABLE}=1)')
    args = parser.parse_args()
    for action in configure(args.ios / 'Runner' / 'Info.plist', multiple_scenes_requested(args.multiple_scenes)):
        print('external-display: ' + action)
    print('External display scene role configured; application scene, emulators and Flutter host untouched.')


if __name__ == '__main__':
    main()
