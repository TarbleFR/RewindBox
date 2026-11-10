#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
main = (ROOT / "lib/main.dart").read_text(encoding="utf-8")
manager = (ROOT / "lib/screens/rpcs3_manager_screen.dart").read_text(encoding="utf-8")
playlist = (ROOT / "lib/widgets/rpcs3_internal_playlist_actions.dart").read_text(encoding="utf-8")
service = (ROOT / "lib/services/rpcs3_internal_service.dart").read_text(encoding="utf-8")
header = (ROOT / "lib/widgets/header.dart").read_text(encoding="utf-8")
rpcs3_locale = (ROOT / "lib/l10n/rpcs3_ui_locale.dart").read_text(encoding="utf-8")

def require(value, message):
    if not value:
        raise SystemExit(message)

blocking = main[main.index("void main() async {"):main.index("await AudioPolicyService().initialize();")]
require("synchronizeFilesWorkspace()" not in blocking,
        "RPCS3 Files workspace still blocks NeoStation cold startup")
require("migrateLegacyRootFiles()" not in blocking,
        "diagnostic migration still blocks NeoStation cold startup")
require("_prepareIosFilesWorkspaceAfterStartup" in main and
        "addPostFrameCallback" in main and
        "Duration(milliseconds: 750)" in main,
        "Files maintenance is not deferred until after the real app frame")

require("await synchronizeFilesWorkspace();" in service,
        "RPCS3 Files workspace folders are not ensured before explicit Core startup")
require("static bool get jitPrepared => _jitPrepared;" in service,
        "authoritative JIT prepared state is not exposed")

require("diagnostics['jitEnabled'] == true" in manager and
        "jit['debugged'] == true" in manager,
        "RPCS3 manager does not use the native CS_DEBUGGED UI state")
require("jit['requiresCoreHandshake'] != true" not in manager,
        "RPCS3 manager still gates the UI indicator on the Core handshake")
require("_t('jitCoreReady')" in manager and
        "_t('jitCoreOnDemand')" in manager,
        "RPCS3 manager active-state localization keys are missing")
for locale in ("en","fr","de","es","it","pt","ru","id","ja","ko","zh","zh_Hant"):
    require("'" + locale + "':" in rpcs3_locale,
            "RPCS3 UI locale table missing " + locale)
require("'jitCoreReady':" in rpcs3_locale and
        "'jitCoreOnDemand':" in rpcs3_locale,
        "RPCS3 UI active-state translations are missing")

require("value: 'saves'" not in playlist,
        "playlist popup still exposes Export save data")
require("value: 'restoreSaves'" not in playlist,
        "playlist popup still exposes Import save data")

# The maintainer retired the header JIT dot (25 October 2026): the main
# header no longer shows or polls the JIT state; the native CS_DEBUGGED
# probe stays available to the RPCS3 screens.
require("header-jit-active-dot" not in header and
        "jitEnabledForUi" not in header and
        "Color(0xFF22C55E)" not in header,
        "main header still draws or polls the retired JIT dot")
require("status['debugged'] == true" in service and
        "static Future<bool> jitEnabledForUi()" in service,
        "UI JIT state is not backed by the native CS_DEBUGGED result")

print("PASS: startup non-blocking, popup clean, JIT status backed by CS_DEBUGGED, header JIT dot retired")
