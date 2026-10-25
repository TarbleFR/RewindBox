"""The 3D box catalogue is generated, complete and used consistently."""
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class GameBoxStrings(unittest.TestCase):
    def test_generator_check_passes(self):
        result = subprocess.run(
            [sys.executable, 'tools/game_box/generate_strings.py', '--check'],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_key_used_by_the_app_exists(self):
        catalogue = (ROOT / 'lib/l10n/game_box_locale.dart').read_text(encoding='utf-8')
        defined = set(re.findall(r"static const (\w+) = '", catalogue))
        used = set()
        for path in list((ROOT / 'lib').rglob('*.dart')):
            text = path.read_text(encoding='utf-8')
            used |= set(re.findall(r'GameBoxLocale\.(\w+)\b', text))
        api = {'text', 'format', 'fill', 'forCode', 'forLocale', 'codeFor', 'languageName', 'regionName', 'values', 'locales'}
        self.assertFalse(used - defined - api, sorted(used - defined - api))

    def test_no_user_text_is_hard_coded_in_the_box_screens(self):
        for rel in ('lib/screens/game_box/game_box_inspector.dart', 'lib/screens/game_box/box_back_reader_screen.dart'):
            text = (ROOT / rel).read_text(encoding='utf-8')
            for literal in re.findall(r"Text\('([^']+)'\)", text):
                self.fail(f'{rel}: hard-coded text {literal!r}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
