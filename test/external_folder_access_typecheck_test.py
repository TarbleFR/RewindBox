#!/usr/bin/env python3
"""Type-check the folder access plugin against the iPhone SDK and Flutter.

The plugin holds the folder picker and the saved folder accesses of every import that reads a folder outside the
application. Nothing else compiles it before the application build of a delivery; this check gives the verdict on a
macOS runner in a few seconds. It proves that the Swift is accepted by the compiler, not how a picker behaves.
"""
import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sources = sorted((root / 'packages/external_folder_access/ios/Classes').glob('*.swift'))
assert len(sources) >= 3, sources
sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
flutter = Path(os.environ['FLUTTER_ROOT']) / 'bin/cache/artifacts/engine/ios/Flutter.xcframework/ios-arm64'
assert (flutter / 'Flutter.framework/Flutter').is_file(), flutter
# The deployment target of the podspec (s.platform = :ios, '14.0').
podspec = (root / 'packages/external_folder_access/ios/external_folder_access.podspec').read_text()
assert "s.platform = :ios, '14.0'" in podspec, 'the type-check target follows the podspec: update both'
subprocess.run(['xcrun', 'swiftc', '-typecheck', '-swift-version', '5', '-sdk', sdk,
                '-target', 'arm64-apple-ios14.0', '-F', str(flutter),
                '-module-name', 'external_folder_access', *map(str, sources)], check=True)
print('PASS: external_folder_access type-checks against the iPhone SDK: ' + ', '.join(p.name for p in sources))
