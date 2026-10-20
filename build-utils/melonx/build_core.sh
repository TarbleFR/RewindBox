#!/usr/bin/env bash
# Build only the pinned managed engine. No firmware, keys or games are fetched.
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE_DIR="${1:?MeloNX source directory required}"
SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"
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
# The MeloNX mirror's f925129209afd55927a0201d82285b8fa4b7ba30
# retains Ryujinx's projects feed. The new Ryulynx feed does not contain
# the exact alpha.129 package (NU1101 in run 39499119399). Keep the package
# version and source mapping; do not substitute an older LibHac API.
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
dotnet publish src/Ryujinx.Library -c Release -r ios-arm64 --self-contained true -p:ExtraDefineConstants=DISABLE_UPDATER -p:NativeLib=Shared
CORE="$SOURCE_DIR/src/Ryujinx.Library/bin/Release/net10.0/ios-arm64/native/Ryujinx.Library.dylib"
test -s "$CORE"
xcrun lipo -verify_arch arm64 "$CORE"
xcrun nm -gU "$CORE" > "$TASK_ROOT/dist/melonx/exports.txt"
otool -L "$CORE" > "$TASK_ROOT/dist/melonx/dependencies.txt"
cp "$CORE" "$TASK_ROOT/dist/melonx/"
cp LICENSE.txt "$TASK_ROOT/dist/melonx/MeloNX-LICENSE.txt"
git archive HEAD | gzip > "$TASK_ROOT/dist/melonx/upstream-source.tar.gz"
python3 - "$TASK_ROOT" "$CORE" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
root, core = map(Path, sys.argv[1:])
pin = json.loads((root / 'build-utils/melonx/source.json').read_text())
exports = (root / 'dist/melonx/exports.txt').read_text()
required = ['initialize', 'main_ryujinx_sdl', 'set_native_window', 'stop_emulation', 'toggle_pause_emulation', 'load_keyset', 'install_firmware', 'installed_firmware_version', 'get_game_info', 'set_gamepad_button_state', 'set_gamepad_stick_axis', 'RegisterCallback']
symbols = {line.split()[-1] for line in exports.splitlines() if line.split()}
assert all('_' + name in symbols for name in required), [name for name in required if '_' + name not in symbols]
receipt = dict(source=pin, host=subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(), size=core.stat().st_size, sha256=hashlib.sha256(core.read_bytes()).hexdigest(), exports=required, status='compiled-not-gameplay-tested')
(root / 'dist/melonx/identity.json').write_text(json.dumps(receipt, indent=2) + '\n')
PY
