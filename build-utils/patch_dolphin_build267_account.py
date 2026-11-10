#!/usr/bin/env python3
"""Compatibility entry point: validate the reviewed central-account sources.

The old generator created a second Dolphin login form and Keychain authority.
Keep its build hook harmless and fail if obsolete UI is restored; never rewrite
reviewed sources or inject account labels during a build.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/dolphin_internal_bridge/ios/Classes'


def main():
    menu = (CLASSES / 'DolphinSessionMenu.mm').read_text()
    host = (CLASSES / 'DolphinInternalBridgePlugin.mm').read_text()
    account = (CLASSES / 'DolphinRetroAchievementsAccount.mm').read_text()
    header = (CLASSES / 'DolphinRetroAchievementsAccount.h').read_text()
    for obsolete in ('DOLMenuAchievements', 'raAccount', 'linkAccount', 'unlinkAccount'):
        if obsolete in menu or obsolete in account or obsolete in header:
            raise SystemExit('Legacy Dolphin account UI found; use the reviewed central-session sources')
    for obsolete in ('SecItem', 'NSURLSession', '@interface DolphinRetroAchievementsAccount'):
        if obsolete in account or obsolete in header:
            raise SystemExit('Dolphin must not retain an independent account authority')
    if '[DolphinRetroAchievementsAccount credentials]' in host or 'RBRATakeLaunchConfiguration' not in host:
        raise SystemExit('Dolphin launch must consume the central session snapshot')
    if 'NSData* DOLSerializeMenuRequest(id request)' not in account:
        raise SystemExit('Shared Dolphin menu request validation is missing')
    if 'if (!DOLSerializeMenuRequest(request))' not in menu or 'NSData* data = DOLSerializeMenuRequest(request)' not in host:
        raise SystemExit('Dolphin settings request guards are missing')
    print('Dolphin central account ownership and shared menu validation verified; no files rewritten.')


if __name__ == '__main__':
    main()
