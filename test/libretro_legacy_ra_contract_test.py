#!/usr/bin/env python3
"""Static regression contracts for retirement of engine-local RA account paths.

These source checks complement native tests; they do not claim to exercise
Keychain migration, authentication, awards, or UIKit. The shared session
plugin owns legacy migration. libretro must neither reuse nor erase it.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / "packages/libretro_internal_bridge/ios/Classes"


class LegacyLibretroAccountContract(unittest.TestCase):
    def test_client_has_no_engine_local_storage_or_authentication(self):
        client = (CLASSES / "LibretroAchievements.m").read_text()
        public = (CLASSES / "LibretroAchievements.h").read_text()
        for retired in ("NSUserDefaults", "SecItem", "StoredLogin", "StoreLogin",
                        "ClearLogin", "libretro.achievements.enabled", ".libretro.retroachievements",
                        "rc_client_begin_login_with_password"):
            self.assertNotIn(retired, client, retired)
        self.assertNotRegex(public, r"(?m)^[-+]\s*\([^\n]+\)\s*(?:setEnabled|enabled|hasStoredLogin|loginWithUsername|logout)\b")
        self.assertIn('rc_client_begin_login_with_token', client)

    def test_ticket_consumed_only_at_native_launch_boundary(self):
        sources = {path.name: path.read_text() for path in CLASSES.glob("*.m")}
        consumers = [name for name, body in sources.items()
                     if re.search(r"\bRBRATakeLaunchConfiguration\s*\(", body)]
        self.assertEqual(consumers, ["LibretroInternalBridgePlugin.m"])
        self.assertEqual(sources[consumers[0]].count("RBRATakeLaunchConfiguration("), 1)
        self.assertNotIn("RBRATakeLaunchConfiguration(", sources["LibretroSession.m"])
        self.assertNotIn("RBRATakeLaunchConfiguration(", sources["LibretroAchievements.m"])

    def test_native_menu_cannot_restore_independent_account_controls(self):
        session = (CLASSES / "LibretroSession.m").read_text()
        plugin = (CLASSES / "LibretroInternalBridgePlugin.m").read_text()
        for retired in ("achievementsPage", "achievementsLogin", "achievementsLogout",
                        "achievementsEnabled", "achievementsPassword"):
            self.assertNotIn(retired, session)
            self.assertNotIn(retired, plugin)
        for path in (CLASSES / "LibretroInputMap.m", CLASSES / "LibretroFrontendMenu.m"):
            body = path.read_text()
            self.assertNotRegex(body, r"achievements(?:Login|Logout|Enabled|Password)")

    def test_libretro_does_not_delete_legacy_credentials(self):
        # Legacy key names are intentionally absent from this adapter. Their
        # presence in the shared migration is reviewed/tested in that plugin.
        for path in CLASSES.glob("*.[hm]"):
            body = path.read_text()
            self.assertNotIn("libretro.achievements.enabled", body, str(path))
            self.assertNotIn(".libretro.retroachievements", body, str(path))
        client = (CLASSES / "LibretroAchievements.m").read_text()
        self.assertNotIn("SecItemDelete", client)
        self.assertNotIn("removeObjectForKey", client)


if __name__ == "__main__":
    unittest.main()
