#!/usr/bin/env python3
"""Source contract of the 3D books and manga chantier (Build 447).

docs/library-books-3d-plan.md § 5: the page-curl shader is declared and only
loaded behind LibraryPageCurlProgram.load (painter fallback otherwise); the
chantier adds no dependency; the three readers react to memory pressure and
to Reduce Motion (iOS reports it only as AccessibilityFeatures.reduceMotion);
the right stick click is wired; the readers' texts come from the twelve-locale
catalog; nothing mentions the Library/Sources folder; the delivery runs this
contract and every library_* Dart test, and the gate declares the inputs.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READER_DIR = ROOT / 'lib/screens/library_screen/reader'
PDF_READER = ROOT / 'lib/screens/library_screen/library_pdf_reader_screen.dart'
PAGE_READER = READER_DIR / 'library_page_reader_screen.dart'
BOOK_READER = READER_DIR / 'library_book_reader_screen.dart'
CURL = READER_DIR / 'library_page_curl.dart'
GAMEPAD = READER_DIR / 'library_reader_gamepad.dart'
WIDGETS = ('lib/widgets/library_book_cover.dart', 'lib/widgets/library_book_volume.dart',
           'lib/widgets/library_book_open_transition.dart')
DELIVERY = ROOT / '.github/workflows/retroarch-delivery.yml'
# pubspec.lock of the Build 446 source (8ceeb055): this cycle adds no package.
LOCK_SHA256 = '6ceb0c3787c1c35c844950338e99e408ff548dbc4aacfff0270c5b1ddd285a8e'


def read(path: Path | str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def class_block(text: str, name: str) -> str:
    start = text.index('class ' + name)
    open_at = text.index('{', start)
    depth = 0
    for index in range(open_at, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError('unbalanced class ' + name)


def book_sources() -> list[Path]:
    files = sorted(READER_DIR.glob('*.dart')) + [PDF_READER]
    files += [ROOT / path for path in WIDGETS]
    files.append(ROOT / 'lib/screens/library_screen/library_reader_launcher.dart')
    return files


class BooksContract(unittest.TestCase):
    def test_shader_is_declared_and_loaded_only_behind_the_program(self) -> None:
        pubspec = read('pubspec.yaml')
        shaders = pubspec.split('\n  shaders:\n', 1)[1]
        self.assertIn('    - assets/shaders/page_curl.frag\n', shaders)
        self.assertTrue((ROOT / 'assets/shaders/page_curl.frag').is_file())
        curl = CURL.read_text(encoding='utf-8')
        program = class_block(curl, 'LibraryPageCurlProgram')
        self.assertIn("static const String asset = 'assets/shaders/page_curl.frag';", program)
        self.assertIn('static Future<LibraryPageCurlProgram?> load() => _loading ??= _attempt();', program)
        # The asset is only named by the program; nothing else loads it.
        for path in sorted((ROOT / 'lib').rglob('*.dart')):
            text = path.read_text(encoding='utf-8')
            if path == CURL:
                outside = text.replace(program, '')
                self.assertNotIn('fromAsset', outside, 'only LibraryPageCurlProgram loads the shader')
                continue
            self.assertNotIn('page_curl.frag', text, str(path.relative_to(ROOT)))
            if path.is_relative_to(READER_DIR) or path == PDF_READER:
                self.assertNotIn('fromAsset', text, str(path.relative_to(ROOT)))

    def test_no_dependency_is_added(self) -> None:
        self.assertEqual(hashlib.sha256((ROOT / 'pubspec.lock').read_bytes()).hexdigest(), LOCK_SHA256)

    def test_the_three_readers_handle_memory_pressure_and_reduce_motion(self) -> None:
        helper = read('lib/widgets/library_reduce_motion.dart')
        self.assertIn('bool libraryReduceMotion(BuildContext context)', helper)
        # iOS reports Reduce Motion only through this flag (never disableAnimations).
        self.assertIn('accessibilityFeatures.reduceMotion', helper)
        self.assertIn('MediaQuery.maybeDisableAnimationsOf(context)', helper)
        for path in (PAGE_READER, BOOK_READER, PDF_READER):
            text = path.read_text(encoding='utf-8')
            name = str(path.relative_to(ROOT))
            self.assertIn('void didHaveMemoryPressure()', text, name)
            self.assertIn('void didChangeAccessibilityFeatures()', text, name)
            self.assertIn('libraryReduceMotion(', text, name)
            # Reading only disableAnimations would ignore iOS's Reduce Motion.
            self.assertNotIn('MediaQuery.disableAnimationsOf', text, name)
        cover = read('lib/widgets/library_book_cover.dart')
        self.assertIn('libraryReduceMotion(', cover)
        transition = read('lib/widgets/library_book_open_transition.dart')
        self.assertIn('features.reduceMotion', transition)

    def test_right_stick_click_is_wired(self) -> None:
        gamepad = GAMEPAD.read_text(encoding='utf-8')
        self.assertIn('final VoidCallback? rightStickClick;', gamepad)
        self.assertIn('onRightStickClick: () => b().rightStickClick?.call(),', gamepad)
        pdf = PDF_READER.read_text(encoding='utf-8')
        self.assertIn('rightStickClick: _mode == LibraryPdfMode.scroll ? _fitPage : null,', pdf)

    def test_reader_texts_come_from_the_catalog(self) -> None:
        literal = re.compile(r"""(?:\bText\(\s*|\b(?:tooltip|semanticsLabel|hintText|labelText|message):\s*)(['"])(?=[^'"$]*[A-Za-z])""")
        for path in book_sources():
            text = path.read_text(encoding='utf-8')
            for match in literal.finditer(text):
                line = text.count('\n', 0, match.start()) + 1
                self.fail(f'{path.relative_to(ROOT)}:{line}: user-visible literal, use LibraryReaderLocale')

    def test_nothing_points_to_the_library_sources_folder(self) -> None:
        for path in book_sources():
            text = path.read_text(encoding='utf-8')
            name = str(path.relative_to(ROOT))
            self.assertNotIn('Library/Sources', text, name)
            self.assertNotIn('LibrarySourceFiles', text, name)
            self.assertNotIn('library_source_files', text, name)

    def test_delivery_runs_the_books_checks_and_the_gate_declares_them(self) -> None:
        delivery = DELIVERY.read_text(encoding='utf-8')
        self.assertTrue('        flutter test test/library_*_test.dart\n' in delivery,
                        'the checks job runs every library_* Dart test')
        self.assertTrue('        python3 test/library_reader_orientation_contract_test.py\n'
                        '        python3 test/library_books_3d_contract_test.py\n' in delivery,
                        'the checks job runs this contract after the orientation contract')
        spec = importlib.util.spec_from_file_location('reuse', ROOT / 'build-utils/verify_delivery_reuse.py')
        reuse = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reuse)
        delta = reuse.BUILD447_BOOKS_DELTA
        self.assertTrue(delta <= reuse.DELTA)
        for path in ('assets/shaders/page_curl.frag', 'pubspec.yaml', 'test/library_books_3d_contract_test.py',
                     'lib/screens/library_screen/reader/library_page_curl.dart',
                     'lib/screens/library_screen/library_pdf_reader_screen.dart',
                     'lib/widgets/library_book_volume.dart', 'lib/widgets/library_book_open_transition.dart'):
            self.assertIn(path, delta)
        for relative in BOOK_TESTS_OF_THIS_CYCLE:
            self.assertTrue((ROOT / relative).is_file(), relative)
            self.assertIn(relative, delta)
        # No stale entry: every declared test exists.
        for relative in sorted(path for path in delta if path.startswith('test/')):
            self.assertTrue((ROOT / relative).is_file(), relative)


# The test files this chantier adds (docs/library-books-3d-plan.md § 5).
BOOK_TESTS_OF_THIS_CYCLE = (
    'test/library_reading_store_bookmarks_test.dart',
    'test/library_book_volume_test.dart',
    'test/library_book_open_transition_test.dart',
    'test/library_page_textures_test.dart',
    'test/library_page_curl_test.dart',
    'test/library_reader_page_precedence_test.dart',
    'test/library_reader_page_turns_test.dart',
    'test/library_reader_page_spreads_test.dart',
    'test/library_reader_pdf_modes_test.dart',
    'test/library_reflow_paginator_test.dart',
    'test/library_reader_book_pages_test.dart',
    'test/library_reader_toolbar_test.dart',
    'test/library_reader_bookmarks_test.dart',
    'test/library_reader_settings_sections_test.dart',
    'test/library_reader_accessibility_test.dart',
    'test/library_books_3d_contract_test.py',
)


if __name__ == '__main__':
    unittest.main()
