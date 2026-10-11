#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
diag = (ROOT / "lib/services/diagnostics_directory.dart").read_text()
main = (ROOT / "lib/main.dart").read_text()
service = (ROOT / "lib/services/rpcs3_internal_service.dart").read_text()
native = (ROOT / "packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm").read_text()
external = (ROOT / "packages/external_folder_access/ios/Classes/ExternalFolderAccessPlugin.swift").read_text()

def require(value, message):
    if not value:
        raise SystemExit(message)

for token in (
    "DiagnosticsDirectory.migrateLegacyRootFiles()",
    "Rpcs3InternalService.synchronizeFilesWorkspace()",
):
    require(token in main, f"startup housekeeping missing: {token}")

for token in (
    "'Diagnostics'",
    "lower.endsWith('_debug.txt')",
    "lower.startsWith('diagnostic-')",
    "rpcs3-diagnostic.log",
    "rpcs3-milestones.log",
):
    require(token in diag, f"diagnostic migration contract missing: {token}")

for token in (
    "'Import/Game Saves'",
    "'Import/Savestates'",
    "'Export/Game Saves'",
    "'Export/Savestates'",
    "synchronizeFilesWorkspace",
    "README.txt",
    "filesWorkspaceReadme",
    "await filesWorkspaceDirectory();",
):
    require(token in service, f"RPCS3 Files workspace contract missing: {token}")

# Build 442: the startup housekeeping only ensures the folders and README.
# Saves move only on the user's action through Rpcs3SaveExchangeService
# (ZIP export with a share action, staged import with a replace prompt).
for token in ("consumeSource", "_copyTree", "neostation-import-backup"):
    require(token not in service, f"old automatic save copy still present: {token}")
startup = service[service.index("synchronizeFilesWorkspace() async {"):service.index("static String _saves(")]
for token in ("delete(", ".copy(", "rename(", "dataDirectory()"):
    require(token not in startup, f"startup housekeeping still touches saves: {token}")

exchange = (ROOT / "lib/services/rpcs3_save_exchange_service.dart").read_text(encoding="utf-8")
for token in (
    "ZipFileEncoder",
    "ZipDecoder",
    "static const String backupFolderName = 'SaveBackups';",
    "static const String stagingPrefix = '.neostation-save-import-';",
    "Rpcs3RapLicenceService.storageRedirection",
    "Rpcs3RapLicenceService.activeUserId",
):
    require(token in exchange, f"game-save exchange contract missing: {token}")

require('stringByAppendingPathComponent:@"Diagnostics"' in native,
        "native RPCS3 logs still target Documents root")
require('"Diagnostics"' in external and "appendingPathComponent(fileName)" in external,
        "JIT launch diagnostics still target Documents root")

print("PASS: Diagnostics folder and physical RPCS3 Import/Export workspace contracts")
