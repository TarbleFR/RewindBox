"""Protect the requested library rollback and unchanged native engines."""
import hashlib
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'docs/retroarch-baseline-manifest.json').read_text())
# Maintainer-requested RPCS3 NeoSwap adaptation, reviewed at 364b4d1a on
# 11 October 2026. Keep the historical manifest intact; pin the two changed
# host allocators explicitly. The 11 October follow-up adds published backing
# accounting (Backend.cpp/.h) and truthful 12-locale donation labels only. IPC,
# extensions and other native engines retain every historical fingerprint.
# The delivery lane runs the changed native and translation tests.
NEOSWAP_MELONX_REVIEWED = {
    'native/neoswap-donation/Pool.cpp': '4bf08a2242fe53b1ed482731748697d750d879214b85b894d31a28f84a54b577',
    'native/neoswap-relay/Backend.cpp': '6907b636cd87a7b7c6889d80bc33115a4725b58dedac29ab8e254302ecfcda47',
    'native/neoswap-relay/Backend.h': '1ada97c35b7db91f285989a68e4584e0aa200bf42d49ab1d6ca43ca845b03d68',
    'native/neoswap/localizations.json': '9aed2f02173e1d1618133392a82fbfced8c56720d8ef6dd083d43bef44380b67',
}
# Build441, explicitly requested RPCS3/NeoSwap prepared guest backing, reviewed
# at 351b738c8d4d5fbe2c7498d4438776baecdba613. Only these two host-backend
# fingerprints supersede Build439: bounded prepared acquisition/return,
# first-map publication and deferred scrub are exercised by relay_backend_test.
# Keep the older review and every other library/native fingerprint intact.
NEOSWAP_PREPARED_441_REVIEWED = {
    'native/neoswap-relay/Backend.cpp': '376c9f268ebd4d2454393b56aa1a0ef090b9ee5a039cddaca085219e2bbb1a21',
    'native/neoswap-relay/Backend.h': '231dc8b69b60ab26242cdcc9723a449b0872d198211097ab7fe248c18acc3c69',
}
# Build444, explicitly requested RPCS3/LLVM/NeoSwap cycle (11 October 2026,
# "corrige les limitations démontrées"), reviewed at 7ec94a8c316526dcf99c4ca6bdd699a528b7d0ae:
# the same two host-backend files gain the optional direct guest admission
# (NeoSwapDirectRelayAPI try_create under the budget allowance), burst
# restocking of one size class and the rate-limited maintenance wake-up, all
# exercised by relay_backend_test. They supersede the Build441 fingerprints;
# every other library/native fingerprint stays intact.
NEOSWAP_DIRECT_444_REVIEWED = {
    'native/neoswap-relay/Backend.cpp': 'e8bf456bc25f52d429ffc7d690153e0670ac1ae49644a3b6206456b66603e181',
    'native/neoswap-relay/Backend.h': '230e5572307f01c6ba47c11f9e6e47fcfcd1a5fd43f0d9e450d6e4304a1fff35',
}

# KartPad removal, maintainer decision of 19 October 2026: KartPad is no longer
# part of NeoStation (players build it themselves as a separate app). The two
# library files lose exactly the KartPad scan root, reconstructed below before
# the 419 fingerprint check; the retired KartPad host sources must be absent.
KARTPAD_REMOVAL_EDITS = {
    'lib/providers/sqlite_config_provider.dart': [
        (b"import '../services/dusklight_internal_service.dart';\n/* DOLPHIN_ISOLATION_END: provider_import */\n",
         b"import '../services/dusklight_internal_service.dart';\nimport '../services/kartpad_internal_service.dart';\n/* DOLPHIN_ISOLATION_END: provider_import */\n"),
    ],
    'lib/providers/sqlite_config_provider/scanning.dart': [
        (b"    await DusklightInternalService.ensureLayout();\n    if (_availableSystems.isEmpty) await _loadAvailableSystems();\n",
         b"    await DusklightInternalService.ensureLayout();\n    await KartPadInternalService.ensureLayout();\n    if (_availableSystems.isEmpty) await _loadAvailableSystems();\n"),
        (b"""            (await DusklightInternalService.rootDirectory()).path;
        nativeScanRoots = <String>[dusklightRoot];
""",
         b"""            (await DusklightInternalService.rootDirectory()).path;
        final kartPadRoot = (await KartPadInternalService.rootDirectory()).path;
        nativeScanRoots = <String>[dusklightRoot, kartPadRoot];
"""),
        (b"""            'ports': (await DusklightInternalService.gamesDirectory()).path,
          },
        };
""",
         b"""            'ports': (await DusklightInternalService.gamesDirectory()).path,
          },
          kartPadRoot: <String, String>{
            'ports': (await KartPadInternalService.gamesDirectory()).path,
          },
        };
"""),
    ],
}
RETIRED_KARTPAD_NATIVE = 'native/kartpad/'


# Removal of Dusklight and the Ports playlist, maintainer decision of 20 October
# 2026 (docs/ports-removal-2026-10-20.md): six library files lose exactly the
# Ports import, scan roots, forced playlist, scraping identity and SQL name
# cases, and sqlite_service.dart gains two marked RETIRED_PORTS blocks (the
# checked database copy made before the former system is pruned). Each edit is
# reconstructed below (current, original, occurrences) before the Build 423 and
# KartPad reconstructions; the retired Dusklight host sources must be absent.
PORTS_REMOVAL_EDITS = {
    'lib/providers/sqlite_config_provider.dart': [
        (b"""import '../services/armsx2_internal_service.dart';
/* DOLPHIN_ISOLATION_END: provider_import */
""",
         b"""import '../services/armsx2_internal_service.dart';
import '../services/dusklight_internal_service.dart';
/* DOLPHIN_ISOLATION_END: provider_import */
""", 1),
    ],
    'lib/providers/sqlite_config_provider/scanning.dart': [
        (b"""      await Armsx2InternalService.ensureLayout();
    }
""",
         b"""      await Armsx2InternalService.ensureLayout();
      await DusklightInternalService.ensureLayout();
    }
""", 1),
        (b"        for (final folderName in const <String>['ps2']) {\n",
         b"        for (final folderName in const <String>['ps2', 'ports']) {\n", 1),
        (b"            ? ['gc', 'wii', 'ps2']\n",
         b"            ? ['gc', 'wii', 'ps2', 'ports']\n", 1),
        (b"""        final isEmbeddedIosLibrary =
            Platform.isIOS &&
            const <String>{'ps2'}.contains(
              system.folderName.toLowerCase(),
            );
""",
         b"""        final isEmbeddedIosLibrary =
            Platform.isIOS &&
            const <String>{'ps2', 'ports'}.contains(
              system.folderName.toLowerCase(),
            );
""", 1),
        (b'  /// Performs an isolated scan for a specific system.\n',
         b"""  /// Refreshes NeoStation's Files-visible native Ports libraries.
  Future<void> refreshPortsInternalLibrary() async {
    if (!Platform.isIOS) {
      throw StateError('Embedded Ports refresh is available on iOS only.');
    }
    await DusklightInternalService.ensureLayout();
    if (_availableSystems.isEmpty) await _loadAvailableSystems();
    final system = _availableSystems.firstWhere(
      (candidate) => candidate.folderName == 'ports',
    );
    await SystemRepository.addDetectedSystem(system.id!, system.folderName);
    if (!_detectedSystems.any((candidate) => candidate.id == system.id)) {
      _detectedSystems = [..._detectedSystems, system];
    }
    await _scanSystemRoms(system);
    await _refreshDetectedSystemsFromDatabase();
    _sortDetectedSystems();
    _notify();
  }

  /// Compatibility alias while the former single-port API is retired.
  Future<void> refreshDusklightInternalLibrary() =>
      refreshPortsInternalLibrary();

  /// Performs an isolated scan for a specific system.
""", 1),
        (b"""      final isArmsx2InternalSystem =
          Platform.isIOS && system.folderName.toLowerCase() == 'ps2';
      final isNativeInternalSystem =
          isDolphinInternalSystem ||
          isArmsx2InternalSystem;
""",
         b"""      final isArmsx2InternalSystem =
          Platform.isIOS && system.folderName.toLowerCase() == 'ps2';
      final isPortsInternalSystem =
          Platform.isIOS && system.folderName.toLowerCase() == 'ports';
      final isNativeInternalSystem =
          isDolphinInternalSystem ||
          isArmsx2InternalSystem ||
          isPortsInternalSystem;
""", 1),
        (b"""          (await Armsx2InternalService.gamesDirectory()).path,
        ];
      } else {
""",
         b"""          (await Armsx2InternalService.gamesDirectory()).path,
        ];
      } else if (isPortsInternalSystem) {
        final dusklightRoot =
            (await DusklightInternalService.rootDirectory()).path;
        nativeScanRoots = <String>[dusklightRoot];
        effectiveRootFoldersMap = <String, Map<String, String>>{
          dusklightRoot: <String, String>{
            'ports': (await DusklightInternalService.gamesDirectory()).path,
          },
        };
      } else {
""", 1),
        (b"""                  const <String>{'ps2'}.contains(
                    updatedSystem.folderName.toLowerCase(),
                  )));
""",
         b"""                  const <String>{'ps2', 'ports'}.contains(
                    updatedSystem.folderName.toLowerCase(),
                  )));
""", 1),
    ],
    'lib/data/datasources/sqlite_database_service.dart': [
        (b"""import '../../utils/vita_title_extractor.dart';

""",
         b"""import '../../utils/vita_title_extractor.dart';
import '../../services/ports_game_identity.dart';

""", 1),
        (b"    if (systemId == 'switch' || systemId == 'nintendo-switch') return true;\n",
         b"""    if (systemId == 'ports') return true;
    if (systemId == 'switch' || systemId == 'nintendo-switch') return true;
""", 1),
        (b"""        String? titleName;

        if (isSwitch && !entry.path.startsWith('content://')) {
""",
         b"""        String? titleName;

        if (systemFolderName == 'ports') {
          final identity = await PortGameIdentity.read(entry.path);
          if (identity != null) {
            titleId = identity.discId;
            titleName = identity.displayTitle;
          }
        }

        if (isSwitch && !entry.path.startsWith('content://')) {
""", 1),
    ],
    'lib/data/datasources/sqlite_service.dart': [
        (b"CASE WHEN s.folder_name = 'android' OR",
         b"CASE WHEN s.folder_name IN ('android', 'ports') OR", 4),
    ],
    'lib/repositories/scraper_repository.dart': [
        (b"""        AND (s.screenscraper_id IS NOT NULL AND s.screenscraper_id != 0)
      ORDER BY s.real_name
""",
         b"""        AND ((s.screenscraper_id IS NOT NULL AND s.screenscraper_id != 0)
             OR s.folder_name = 'ports')
      ORDER BY s.real_name
""", 1),
        (b"""        WHERE (asys.screenscraper_id IS NOT NULL AND asys.screenscraper_id > 0)
        AND ussc.enabled = 1
""",
         b"""        WHERE ((asys.screenscraper_id IS NOT NULL AND asys.screenscraper_id > 0)
               OR asys.folder_name = 'ports')
        AND ussc.enabled = 1
""", 1),
        (b'      WHERE asys.screenscraper_id IS NULL\n',
         b"      WHERE asys.screenscraper_id IS NULL AND asys.folder_name != 'ports'\n", 1),
        (b'WHERE screenscraper_id IS NOT NULL AND screenscraper_id > 0",\n',
         b'WHERE (screenscraper_id IS NOT NULL AND screenscraper_id > 0) OR folder_name = \'ports\'",\n', 1),
    ],
    'lib/repositories/system_repository.dart': [
        (b"      for (final folderName in const <String>['ps2', 'ps3']) {\n",
         b"      for (final folderName in const <String>['ps2', 'ps3', 'ports']) {\n", 1),
    ],
}
RETIRED_PORTS_BLOCK = re.compile(
    rb'(?m)^[ \t]*// RETIRED_PORTS_BEGIN: (\w+)\n.*?^[ \t]*// RETIRED_PORTS_END: \1\n', re.S)
RETIRED_DUSKLIGHT_NATIVE = 'native/dusklight/'


class RetroArchBaselineScope(unittest.TestCase):
    def test_library_is_the_recorded_build419_reference(self):
        for name, expected in MANIFEST['library_sha256'].items():
            with self.subTest(path=name):
                data = (ROOT / name).read_bytes()
                if name == 'lib/services/ios_rom_library_root_resolver.dart':
                    # Reviewed linkage-only exception: Files returns a literal
                    # filesystem path, including spaces. Reconstruct exactly the
                    # single Build419 expression; all other bytes stay locked.
                    literal = b'final rootPath = path.normalize(linkedRoot);'
                    self.assertEqual(data.count(literal), 1)
                    data = data.replace(literal, b'final rootPath = path.normalize(linkedRoot.trim());', 1)
                if name in PORTS_REMOVAL_EDITS:
                    # Dusklight and Ports removal, at the maintainer's request
                    # (20 October 2026): the marked database-copy blocks and
                    # the Ports lines are reconstructed first.
                    data, blocks = RETIRED_PORTS_BLOCK.subn(b'', data)
                    self.assertEqual(blocks, 2 if name.endswith('/sqlite_service.dart') else 0)
                    for current, original, occurrences in PORTS_REMOVAL_EDITS[name]:
                        self.assertEqual(data.count(current), occurrences)
                        data = data.replace(current, original)
                if name == 'lib/providers/sqlite_config_provider/scanning.dart':
                    # Build423: the user's seven saved roots exposed the silent
                    # five-folder cap. Only registration changes; scan logic is
                    # still byte-identical to 419/422. Reconstruct those exact
                    # reviewed edits before checking the historical fingerprint.
                    edits = [
                        (b'    if (_config.romFolders.contains(folderPath)) return;\n',
                         b'    if (_config.romFolders.contains(folderPath)) return;\n    if (_config.romFolders.length >= 5) return;\n'),
                        (b'      final updatedConfig = _config.copyWith(\n', b'      _config = _config.copyWith(\n'),
                        (b'      await SqliteConfigService.saveConfig(updatedConfig);\n      _config = updatedConfig;\n',
                         b'      await SqliteConfigService.saveConfig(_config);\n'),
                    ]
                    for current, original in edits:
                        self.assertEqual(data.count(current), 1)
                        data = data.replace(current, original, 1)
                if name in KARTPAD_REMOVAL_EDITS:
                    # KartPad removal, at the maintainer's request (19 October
                    # 2026): only the Ports › KartPad scan root and its import
                    # are gone; every other byte stays 419.
                    for current, original in KARTPAD_REMOVAL_EDITS[name]:
                        self.assertEqual(data.count(current), 1)
                        data = data.replace(current, original, 1)
                if name == 'lib/main.dart':
                    # Maintainer-requested external MeloNX retirement, 20 October 2026.
                    for current, original in [(b'    // External MeloNX synchronisation is retired. Existing cached metadata is\n    // left untouched; Nintendo Switch games must be imported for the embedded\n    // engine. RetroArch retains its own callback.\n    ExternalFolderAccess.setIncomingUrlListener((uri) async {\n      await RetroArchLibraryService.handleIncomingUri(uri);\n    });', b'    // RetroArch and MeloNX still receive their exported libraries through the\n    // neostation:// callback scheme. ARMSX2 library discovery is filesystem-only\n    // and therefore has no callback handler here.\n    ExternalFolderAccess.setIncomingUrlListener((uri) async {\n      if (await RetroArchLibraryService.handleIncomingUri(uri)) return;\n      await MelonxLibraryService.handleIncomingUri(uri);\n    });'), (b"import 'package:neostation/services/armsx2_internal_service.dart';\n", b"import 'package:neostation/services/armsx2_internal_service.dart';\nimport 'package:neostation/services/melonx_library_service.dart';\n"), (b'    await RetroArchLibraryService.loadCachedLibrary();\n', b'    await RetroArchLibraryService.loadCachedLibrary();\n    await MelonxLibraryService.loadCachedLibrary();\n')]:
                        self.assertEqual(data.count(current), 1)
                        data = data.replace(current, original, 1)
                    # Build433, at the maintainer's request (10 October 2026):
                    # saved library folders are found again at startup after
                    # iOS moved an app container. Exactly these three marked
                    # blocks are removed; every other byte stays 419.
                    data, count = re.subn(
                        rb'(?m)^[ \t]*// LIBRARY_RELOCATION_BEGIN: (\w+)\n.*?^[ \t]*// LIBRARY_RELOCATION_END: \1\n',
                        b'', data, flags=re.S)
                    self.assertEqual(count, 3)
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected)

    def test_native_sources_keep_their_existing_identity(self):
        self.assertLessEqual(NEOSWAP_MELONX_REVIEWED.keys(), MANIFEST['native_sha256'].keys())
        self.assertEqual(set(NEOSWAP_PREPARED_441_REVIEWED), {
            'native/neoswap-relay/Backend.cpp', 'native/neoswap-relay/Backend.h',
        })
        self.assertLessEqual(NEOSWAP_PREPARED_441_REVIEWED.keys(), MANIFEST['native_sha256'].keys())
        self.assertEqual(set(NEOSWAP_DIRECT_444_REVIEWED), set(NEOSWAP_PREPARED_441_REVIEWED))
        for name, expected in MANIFEST['native_sha256'].items():
            with self.subTest(path=name):
                if name.startswith((RETIRED_KARTPAD_NATIVE, RETIRED_DUSKLIGHT_NATIVE)):
                    # Retired with KartPad and Dusklight: the old host sources
                    # must not come back.
                    self.assertFalse((ROOT / name).exists())
                    continue
                reviewed = NEOSWAP_DIRECT_444_REVIEWED.get(name, NEOSWAP_PREPARED_441_REVIEWED.get(name, NEOSWAP_MELONX_REVIEWED.get(name, expected)))
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), reviewed)

    def test_retired_repairs_are_outside_executable_app_sources(self):
        for name in ('embedded_library_recovery.dart', 'retroarch_folder_recovery.dart', 'retroarch_library_importer.dart'):
            self.assertFalse((ROOT / 'lib/services' / name).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
