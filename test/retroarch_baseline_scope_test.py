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
                if name == 'lib/main.dart':
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
        for name, expected in MANIFEST['native_sha256'].items():
            with self.subTest(path=name):
                reviewed = NEOSWAP_PREPARED_441_REVIEWED.get(name, NEOSWAP_MELONX_REVIEWED.get(name, expected))
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), reviewed)

    def test_retired_repairs_are_outside_executable_app_sources(self):
        for name in ('embedded_library_recovery.dart', 'retroarch_folder_recovery.dart', 'retroarch_library_importer.dart'):
            self.assertFalse((ROOT / 'lib/services' / name).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
