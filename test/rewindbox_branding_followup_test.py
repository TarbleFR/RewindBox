"""Display branding, unchanged storage identity and README asset integrity."""
import hashlib
import json
from pathlib import Path
import re
import struct
import unittest
ROOT=Path(__file__).resolve().parents[1]
def text(name): return (ROOT/name).read_text(encoding='utf-8')
class RewindBoxFollowup(unittest.TestCase):
    def test_rom_help_uses_fork_name_in_all_twelve_languages(self):
        files=list((ROOT/'lib/l10n').glob('app_locale_*.dart'))
        self.assertEqual(len(files),12)
        for f in files:
            s=f.read_text(encoding='utf-8')
            match=re.search(r'AppLocale\.chooseRomFolderDesc:\s*(.*?)(?=\n\s*AppLocale\.)',s,re.S)
            self.assertIsNotNone(match,f.name)
            self.assertIn('RewindBox',match[1],f.name)
            self.assertNotIn('NeoStation',match[1],f.name)
    def test_wii_motion_permission_has_twelve_branded_translations(self):
        rows=json.loads(text('native/dolphin_motion/strings.json'))
        self.assertEqual(len(rows),12)
        for locale,values in rows.items():
            self.assertIn('RewindBox',values['usage'],locale)
            self.assertNotIn('NeoStation',values['usage'],locale)
    def test_title_fallbacks_are_not_the_upstream_brand(self):
        for name in ('lib/screens/systems_screen/my_systems_section/my_systems_carousel.dart','lib/screens/systems_screen/my_systems_section/my_systems_grid.dart','lib/screens/systems_screen/my_systems_section/my_systems_grid/theme_background.dart'):
            self.assertNotIn('NEOSTATION',text(name),name)
            self.assertIn('RewindBox',text(name),name)
    def test_bios_display_does_not_move_storage(self):
        self.assertIn("return 'RewindBox/",text('lib/services/libretro_bios_check_service.dart'))
        self.assertIn("path.join(support.path, 'NeoStation', 'RPCS3')",text('lib/services/rpcs3_internal_service.dart'))
        self.assertIn("path.join(support.path, 'NeoStation', 'Dolphin')",text('lib/services/dolphin_internal_v2_service.dart'))
    def test_readme_uses_the_verified_maintainer_screenshot(self):
        p=ROOT/'assets/readme/rewindbox-preview.png'
        data=p.read_bytes()
        evidence=json.loads(text('docs/evidence/rewindbox-followup-2026-10-21.json'))
        self.assertEqual(hashlib.sha256(data).hexdigest(),evidence['screenshot']['sha256'])
        self.assertEqual(struct.unpack('>II',data[16:24]),(2504,1153))
        self.assertIn('assets/readme/rewindbox-preview.png',text('README.md'))
        self.assertNotIn('assets/readme/neostation-ios-preview.png',text('README.md'))
    def test_current_provenance_and_download_helpers_use_new_repository(self):
        for name in ('build-utils/collect_build_source_evidence.py','build-utils/embed_legal_bundle.py','build-utils/validate_rpcs3_ipa.py','build-utils/reuse_skin_frontend.py','build-utils/verify_delivery_reuse.py'):
            if not (ROOT/name).exists(): continue
            self.assertIn('TarbleFR/RewindBox',text(name),name)
            self.assertNotIn('TarbleFR/neostation-ios',text(name),name)
    def test_workflow_display_names(self):
        for path in (ROOT/'.github/workflows').glob('*.yml'):
            for line in path.read_text(encoding='utf-8').splitlines():
                if re.match(r'^\s*(?:name|run-name|ARTIFACT_NAME):',line):
                    self.assertNotRegex(line,r'(?i)\bneostation\b',path.name)
if __name__=='__main__': unittest.main(verbosity=2)
