#!/usr/bin/env bash
# Build only the pinned managed engine. No firmware, keys or games are fetched.
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE_DIR="${1:?MeloNX source directory required}"
SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"
LIBHAC_DIR="$(cd "${2:?LibHac source directory required}" && pwd)"
python3 - "$TASK_ROOT" "$SOURCE_DIR" <<'PY'
import json, subprocess, sys
from pathlib import Path
root, source = map(Path, sys.argv[1:])
pin = json.loads((root / 'build-utils/melonx/source.json').read_text())
actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
assert actual == pin['revision'], (actual, pin['revision'])
assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
# Pin SDK resolution as well as the installation. Upstream's latestFeature
# otherwise silently chooses the runner's preinstalled 10.0.401 SDK.
global_json = json.loads((source / 'global.json').read_text())
assert global_json['sdk']['version'] == pin['dotnet']
assert global_json['sdk']['rollForward'] == 'latestFeature'
global_json['sdk']['rollForward'] = 'disable'
(source / 'global.json').write_text(json.dumps(global_json, indent=2) + '\n')
# Retain the official declared feed. Both its current namespace and the
# migrated projects namespace lack alpha.129; the former host is unreachable.
# Exact unsuccessful probes are recorded in the integration audit. Do not
# substitute an older LibHac API or an unverified binary.
nuget = source / 'nuget.config'
config = nuget.read_text(encoding='utf-8-sig')
old_feed = 'https://starforgejo.dev/api/packages/Ryulynx/nuget/index.json'
assert config.count(old_feed) == 1
nuget.write_text(config.replace(old_feed, pin['libHacFeed']), encoding='utf-8')
PY
mkdir -p "$TASK_ROOT/dist/melonx"
cd "$SOURCE_DIR"
dotnet --info
test "$(dotnet --version)" = '10.0.100'
dotnet workload install mobile-librarybuilder --skip-manifest-update
python3 "$TASK_ROOT/build-utils/melonx/build_libhac.py" "$SOURCE_DIR" "$LIBHAC_DIR"
python3 "$TASK_ROOT/build-utils/melonx/prepare_embedded.py" "$SOURCE_DIR"
python3 - <<'PY_PUBLISH'
import subprocess
# Library-builder selects its NativeAOT runtime in publishing mode. A separate
# restore followed by --no-restore omits that runtime even with SelfContained.
# Let publish perform its own matching restore, as the upstream build does.
# The missing LibHac feed is now local; retain a bound on the whole operation.
subprocess.run(['dotnet', 'publish', 'src/Ryujinx.Library', '-c', 'Release', '-r', 'ios-arm64', '--self-contained', 'true', '-p:ExtraDefineConstants=DISABLE_UPDATER', '-p:NativeLib=Shared'], check=True, timeout=1800)
PY_PUBLISH
CORE="$SOURCE_DIR/src/Ryujinx.Library/bin/Release/net10.0/ios-arm64/native/Ryujinx.Library.dylib"
test -s "$CORE"
# Retain the successfully compiled binary even if a subsequent audit fails.
cp "$CORE" "$TASK_ROOT/dist/melonx/"
xcrun lipo "$CORE" -verify_arch arm64
xcrun nm -gU "$CORE" > "$TASK_ROOT/dist/melonx/exports.txt"
otool -L "$CORE" > "$TASK_ROOT/dist/melonx/dependencies.txt"
xcrun vtool -show-build "$CORE" > "$TASK_ROOT/dist/melonx/platform.txt"
cp LICENSE.txt "$TASK_ROOT/dist/melonx/MeloNX-LICENSE.txt"
git archive HEAD | gzip > "$TASK_ROOT/dist/melonx/upstream-source.tar.gz"
python3 - "$TASK_ROOT" "$CORE" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
root, core = map(Path, sys.argv[1:])
pin = json.loads((root / 'build-utils/melonx/source.json').read_text())
exports = (root / 'dist/melonx/exports.txt').read_text()
platform = (root / 'dist/melonx/platform.txt').read_text()
assert 'platform IOS\n' in platform and 'platform IOSSIMULATOR' not in platform, platform
required = ['initialize', 'main_ryujinx_sdl', 'set_native_window', 'stop_emulation', 'toggle_pause_emulation', 'load_keyset', 'install_firmware', 'installed_firmware_version', 'get_game_info', 'set_gamepad_button_state', 'set_gamepad_stick_axis', 'RegisterCallback', 'neostation_melonx_bootstrap_abi', 'neostation_melonx_initialize']
symbols = {line.split()[-1] for line in exports.splitlines() if line.split()}
assert all('_' + name in symbols for name in required), [name for name in required if '_' + name not in symbols]
receipt = dict(source=pin, host=subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(), size=core.stat().st_size, sha256=hashlib.sha256(core.read_bytes()).hexdigest(), exports=required, status='compiled-not-gameplay-tested')
receipt['adaptations'] = json.loads((root / 'dist/melonx/embedded-inputs.json').read_text())
receipt['libHac'] = json.loads((root / 'dist/melonx/libhac-identity.json').read_text())
receipt['embeddedSessionImplemented'] = False
(root / 'dist/melonx/identity.json').write_text(json.dumps(receipt, indent=2) + '\n')
PY
