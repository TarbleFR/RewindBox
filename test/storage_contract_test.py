#!/usr/bin/env python3
"""Storage source contract, test J (docs/storage-audit-cleanup.md § 4 and § 6).

Light maintenance: the picker's copies under tmp/ are discarded only right
after an import verified their length, the engine logs are bounded only at
their documented points, and FilePicker.clearTemporaryFiles(), which empties
the whole of tmp/, is never called again. The behaviour itself is tested by
test/storage_picker_copies_test.dart and test/storage_log_rotation_test.dart;
this file pins where the helpers are called, in which order, and that
nothing runs at startup. Method bodies are found by parsing the Dart sources
(comments and string literals blanked, braces matched), not by line numbers.

The screen and locale checks of test J (phase 5d) follow, then the imports
in progress (review of phase 5d): every import that follows a Files pick
runs inside StorageImportActivity.run, so the cleanup refuses itself while
the picker's copies are still being read.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'lib'
HELPER = 'lib/services/storage/storage_picker_copies.dart'
DISCARD = 'StoragePickerCopies.discardAfterVerifiedImport('
KEEP_NEWEST = 'StorageLogRotation.keepNewest('
ROTATE = 'StorageLogRotation.rotateAtSize('


def mask(source: str) -> str:
    """[source] with its comments and string literals (interpolations
    included) replaced by spaces: same length and line breaks, so an index
    in the result is an index in the source."""
    out = list(source)
    n = len(source)

    def blank(start: int, end: int) -> None:
        for k in range(start, end):
            if out[k] != '\n':
                out[k] = ' '

    def block_comment(i: int) -> int:
        start, depth = i, 0
        while i < n:
            if source.startswith('/*', i):
                depth += 1
                i += 2
            elif source.startswith('*/', i):
                depth -= 1
                i += 2
                if depth == 0:
                    break
            else:
                i += 1
        blank(start, i)
        return i

    def string(i: int) -> int:
        start, raw = i, False
        if source[i] in 'rR':
            raw = True
            i += 1
        quote = source[i]
        delimiter = quote * 3 if source.startswith(quote * 3, i) else quote
        i += len(delimiter)
        while i < n:
            if not raw and source[i] == '\\':
                i += 2
            elif source.startswith(delimiter, i):
                i += len(delimiter)
                break
            elif not raw and source.startswith('${', i):
                i = code(i + 2, inside_interpolation=True) + 1
            elif len(delimiter) == 1 and source[i] == '\n':
                break
            else:
                i += 1
        blank(start, i)
        return i

    def code(i: int, inside_interpolation: bool = False) -> int:
        depth = 0
        while i < n:
            c = source[i]
            if source.startswith('//', i):
                end = source.find('\n', i)
                end = n if end < 0 else end
                blank(i, end)
                i = end
            elif source.startswith('/*', i):
                i = block_comment(i)
            elif c in '\'"' or (
                c in 'rR' and i + 1 < n and source[i + 1] in '\'"'
                and (i == 0 or not (source[i - 1].isalnum() or source[i - 1] in '_$'))
            ):
                i = string(i)
            elif c == '{':
                depth += 1
                i += 1
            elif c == '}':
                if inside_interpolation and depth == 0:
                    return i
                depth -= 1
                i += 1
            else:
                i += 1
        return i

    code(0)
    return ''.join(out)


def matching(masked: str, at: int, opening: str, closing: str) -> int:
    """Index just after the [closing] that matches the [opening] at [at]."""
    assert masked[at] == opening, (at, masked[at:at + 40])
    depth = 0
    for k in range(at, len(masked)):
        if masked[k] == opening:
            depth += 1
        elif masked[k] == closing:
            depth -= 1
            if depth == 0:
                return k + 1
    raise AssertionError('unbalanced ' + opening + closing)


class Source:
    def __init__(self, relative: str) -> None:
        self.relative = relative
        self.text = (ROOT / relative).read_text(encoding='utf-8')
        self.masked = mask(self.text)

    def line(self, index: int) -> int:
        return self.text.count('\n', 0, index) + 1

    def body(self, signature: str) -> tuple:
        """(start, end) of the body of the only declaration starting with
        [signature] (which ends with its opening parenthesis)."""
        at = self.masked.find(signature)
        assert at >= 0, self.relative + ': ' + signature
        assert self.masked.find(signature, at + 1) < 0, self.relative + ': twice ' + signature
        i = matching(self.masked, at + len(signature) - 1, '(', ')')
        i += re.match(r'\s*(?:async\*?|sync\*)?\s*', self.masked[i:]).end()
        if self.masked[i] == '{':
            return i, matching(self.masked, i, '{', '}')
        assert self.masked.startswith('=>', i), self.relative + ': ' + signature
        depth = 0
        for k in range(i + 2, len(self.masked)):
            c = self.masked[k]
            if c in '([{':
                depth += 1
            elif c in ')]}':
                depth -= 1
            elif c == ';' and depth == 0:
                return i, k + 1
        raise AssertionError('no end for ' + signature)


class Span:
    """A method body, searched in the masked text unless [original]."""

    def __init__(self, source: Source, signature: str) -> None:
        self.source = source
        self.signature = signature
        self.start, self.end = source.body(signature)

    def find(self, token: str, original: bool = False, after: int = None) -> int:
        text = self.source.text if original else self.source.masked
        at = text.find(token, self.start if after is None else after, self.end)
        assert at >= 0, f'{self.source.relative}: {self.signature} lacks {token!r}'
        return at

    def count(self, token: str) -> int:
        return self.source.masked.count(token, self.start, self.end)

    def block_end(self, opener: str) -> int:
        """End of the block that [opener] (ending with '{') opens."""
        at = self.find(opener)
        return matching(self.source.masked, at + len(opener) - 1, '{', '}')

    def call(self, at: int) -> str:
        """Source text of the call starting at [at], up to its ')'."""
        open_at = self.source.masked.index('(', at)
        return self.source.text[at:matching(self.source.masked, open_at, '(', ')')]


def dart_files():
    return sorted(LIB.rglob('*.dart'))


# Each verified-import call site: the verification it follows, the line that
# records the verified length, and the loop it waits for (a pick list).
LOOP_SITES = (
    ('lib/services/libretro_internal_service.dart',
     'static Future<LibretroImportResult> importGames(',
     'if (length == 0 || length != sourceLength) {',
     'verifiedCopies[source] = length;',
     'for (final file in selection.files) {',
     # A cue sheet reads its tracks from the picker's folder first.
     ('_copyReferencedTracks(File(source), destination);',)),
    ('lib/services/dolphin_internal_v2_service.dart',
     'static Future<DolphinImportResult> importGames(',
     'if (sourceLength <= 0 || sourceLength != outputLength) {',
     'verifiedCopies[sourcePath] = outputLength;',
     'for (final picked in selection.files) {',
     ()),
    ('lib/services/armsx2_internal_service.dart',
     'static Future<Armsx2ImportResult> _copySelection(',
     'if (sourceLength <= 0 || sourceLength != outputLength) {',
     'verifiedCopies[sourcePath] = outputLength;',
     'for (final picked in files) {',
     ()),
    # The Dolphin import the menu really uses (dolphin_internal_playlist_actions).
    ('lib/services/dolphin_smart_import_service.dart',
     'static Future<DolphinSmartImportResult> importGames(',
     'if (sourceLength <= 0 || sourceLength != outputLength) {',
     'verifiedCopies[sourcePath] = outputLength;',
     'for (final picked in selection.files) {',
     ()),
)

# Every allowed caller of the helpers outside lib/services/storage/:
# file -> method signatures (§ 4). Extending this list is a contract change.
ALLOWED_CALLERS = {
    'lib/services/libretro_internal_service.dart': (
        'static Future<LibretroImportResult> importGames(',),
    'lib/services/dolphin_internal_v2_service.dart': (
        'static Future<DolphinImportResult> importGames(',
        'static Future<String> _sessionLogPath(',),
    'lib/services/armsx2_internal_service.dart': (
        'static Future<Armsx2ImportResult> _copySelection(',),
    'lib/services/rpcs3_internal_service.dart': (
        'static Future<bool> importFirmware(',),
    'lib/services/rpcs3_save_exchange_service.dart': (
        'Future<Rpcs3SaveImportReport?> importGuarded(',),
    'lib/services/dolphin_smart_import_service.dart': (
        'static Future<DolphinSmartImportResult> importGames(',),
    # Embedded MeloNX (Builds 553-558): a game and an update/DLC file, each
    # discarded after its verified copy, inside importGame/importAddon.
    'lib/services/melonx_embedded_library_service.dart': (
        'static Future<bool> importGame(',
        'static Future<String?> _importAddonFile(',),
}


class NeverClearTheWholeTemporaryDirectory(unittest.TestCase):
    def test_no_clear_temporary_files_call_in_lib(self) -> None:
        checked = 0
        for path in dart_files():
            source = Source(str(path.relative_to(ROOT)))
            checked += 1
            at = source.masked.find('clearTemporaryFiles(')
            self.assertLess(at, 0, f'{source.relative}:{source.line(at)} calls clearTemporaryFiles()')
        self.assertGreater(checked, 100, 'lib/ is read')

    def test_the_rpcs3_save_import_flag_is_gone(self) -> None:
        exchange = Source('lib/services/rpcs3_save_exchange_service.dart')
        self.assertNotIn('cleanPickerCopies', exchange.masked)


class RetiredPortsServices(unittest.TestCase):
    # KartPad (19 October 2026), then Dusklight and the Ports playlist
    # (docs/ports-removal-2026-10-20.md) were removed: their import, launch
    # and log call sites left with them, and no other file took their place.
    def test_the_ports_services_are_gone(self) -> None:
        for relative in ('lib/services/dusklight_internal_service.dart',
                         'lib/services/kartpad_internal_service.dart',
                         'lib/services/ports_game_identity.dart'):
            self.assertFalse((ROOT / relative).exists(), relative)
        for path in dart_files():
            masked = Source(str(path.relative_to(ROOT))).masked
            for token in ('DusklightInternalService', 'KartPadInternalService'):
                self.assertNotIn(token, masked, str(path))


class NothingAtStartup(unittest.TestCase):
    def test_main_never_reaches_the_helpers_or_their_call_sites(self) -> None:
        main = Source('lib/main.dart')
        for token in ('StoragePickerCopies', 'StorageLogRotation', 'storage_picker_copies'):
            self.assertNotIn(token, main.text, token)
        for token in ('importGames(', 'importGame(', 'importBios(', 'importFirmware(', 'importGuarded(',
                      'DolphinInternalV2Service.launch('):
            self.assertNotIn(token, main.masked, token)

    def test_the_helpers_are_called_only_at_the_documented_points(self) -> None:
        for path in dart_files():
            relative = str(path.relative_to(ROOT))
            if relative.startswith('lib/services/storage/'):
                continue
            source = Source(relative)
            spans = [Span(source, signature) for signature in ALLOWED_CALLERS.get(relative, ())]
            for token in ('StoragePickerCopies.', 'StorageLogRotation.'):
                at = source.masked.find(token)
                while at >= 0:
                    self.assertTrue(
                        any(span.start <= at < span.end for span in spans),
                        f'{relative}:{source.line(at)} calls {token} outside the call sites of '
                        'docs/storage-audit-cleanup.md § 4 (ALLOWED_CALLERS)')
                    at = source.masked.find(token, at + 1)

    def test_each_call_site_calls_the_helper_once(self) -> None:
        expected = {
            'lib/services/libretro_internal_service.dart': (1, 0, 0),
            'lib/services/dolphin_internal_v2_service.dart': (1, 1, 1),
            'lib/services/armsx2_internal_service.dart': (1, 0, 0),
            'lib/services/rpcs3_internal_service.dart': (1, 0, 0),
            'lib/services/rpcs3_save_exchange_service.dart': (1, 0, 0),
            'lib/services/dolphin_smart_import_service.dart': (1, 0, 0),
        }
        for relative, counts in expected.items():
            masked = Source(relative).masked
            self.assertEqual((masked.count(DISCARD), masked.count(KEEP_NEWEST), masked.count(ROTATE)),
                             counts, relative)


class PickerCopiesAfterAVerifiedImport(unittest.TestCase):
    def test_loops_record_the_verified_length_and_discard_after_the_loop(self) -> None:
        for relative, signature, verification, record, loop, before_record in LOOP_SITES:
            with self.subTest(site=relative):
                span = Span(Source(relative), signature)
                check = span.find(verification)
                check_end = span.block_end(verification)
                recorded = span.find(record)
                loop_end = span.block_end(loop)
                discard = span.find(DISCARD)
                self.assertLess(check_end, recorded, 'the length is recorded once verified')
                for token in before_record:
                    self.assertLess(span.find(token, after=check), recorded, token)
                self.assertLess(recorded, loop_end, 'recorded inside the pick loop')
                self.assertGreater(discard, loop_end,
                                   'discarded once every pick is handled (a later pick may read the folder)')
                self.assertEqual(span.count(DISCARD), 1)
                call = span.call(discard)
                self.assertIn('copy.key', call)
                self.assertIn('expectedLength: copy.value', call)
                self.assertEqual(span.count('verifiedCopies['), 1, 'one recording line')

    def test_armsx2_games_and_bios_share_the_verified_copy(self) -> None:
        source = Source('lib/services/armsx2_internal_service.dart')
        for signature in ('static Future<Armsx2ImportResult> importGames(',
                          'static Future<Armsx2ImportResult> importBios('):
            span = Span(source, signature)
            self.assertGreater(span.count('_copySelection('), 0, signature)
            self.assertEqual(span.count('StoragePickerCopies'), 0, signature)

    def test_rpcs3_firmware_discards_once_staged_before_the_core(self) -> None:
        span = Span(Source('lib/services/rpcs3_internal_service.dart'), 'static Future<bool> importFirmware(')
        staged = span.find('stagedPath = await _stageFirmware(sourcePath);')
        discard = span.find(DISCARD)
        core = span.find('await ensureManagementInitialized();')
        cleanup = span.find('} finally {')
        self.assertLess(staged, discard)
        self.assertLess(discard, core)
        self.assertLess(core, cleanup)
        call = span.call(discard)
        self.assertIn('sourcePath', call)
        self.assertIn('expectedLength: (await File(stagedPath).stat()).size', call)

    def test_rpcs3_game_import_is_unchanged(self) -> None:
        # pkg/iso/zip are installed by the Core from the picked path itself.
        span = Span(Source('lib/services/rpcs3_internal_service.dart'),
                    'static Future<Rpcs3ImportResult> importGames(')
        self.assertEqual(span.count('StoragePickerCopies'), 0)

    def test_rpcs3_save_import_discards_only_the_picked_zip_in_its_finally(self) -> None:
        source = Source('lib/services/rpcs3_save_exchange_service.dart')
        span = Span(source, 'Future<Rpcs3SaveImportReport?> importGuarded(')
        zip_case = span.find('case Rpcs3SaveImportSourceKind.zipFile:')
        folder_case = span.find('case Rpcs3SaveImportSourceKind.folder:')
        readable = span.find('if (path == null || !await File(path).exists()) {', after=zip_case)
        readable_end = matching(source.masked, source.masked.index('{', readable), '{', '}')
        recorded = span.find('pickerCopy = (path: path, length: (await File(path).stat()).size);')
        self.assertEqual(span.count('pickerCopy ='), 1)
        self.assertLess(readable_end, recorded)
        self.assertLess(recorded, folder_case, 'only the ZIP source is a picker copy')
        # The finally of the try that wraps the guarded import (the guard's
        # own body has an inner try/finally for the folder scopes).
        guard = span.find('return await guard(')
        outer_try = source.masked.rfind('try {', span.start, guard)
        try_end = matching(source.masked, outer_try + len('try '), '{', '}')
        self.assertLess(guard, try_end)
        follows = re.match(r'\s*finally\s*\{', source.masked[try_end:])
        self.assertIsNotNone(follows, 'the guarded import is followed by a finally')
        cleanup = try_end + follows.end() - 1
        cleanup_end = matching(source.masked, cleanup, '{', '}')
        discard = span.find(DISCARD)
        self.assertLess(cleanup, discard)
        self.assertLess(discard, cleanup_end, 'inside the finally that follows the guarded import')
        self.assertIn('expectedLength: copy.length', span.call(discard))
        self.assertEqual(span.count(DISCARD), 1)


class LogsBoundedAtTheirPoints(unittest.TestCase):
    def test_dolphin_session_logs_and_persistent_log(self) -> None:
        source = Source('lib/services/dolphin_internal_v2_service.dart')
        span = Span(source, 'static Future<String> _sessionLogPath(')
        keep = span.find(KEEP_NEWEST)
        rotate = span.find(ROTATE)
        named = span.find('return path.join(')
        self.assertIn('name: _sessionLogName, keep: 10', span.call(keep))
        self.assertIn("'dolphin-persistent.jsonl'", span.call(rotate))
        self.assertLess(keep, named)
        self.assertLess(rotate, named)

        declaration = re.search(r"static final RegExp _sessionLogName = RegExp\(\s*r'([^']*)'", source.text)
        self.assertIsNotNone(declaration)
        pattern = re.compile(declaration.group(1))
        for name in ('dolphin-2026-10-12T10-14-00.123456Z.jsonl', 'dolphin-x.jsonl'):
            self.assertTrue(pattern.search(name), name)
        for name in ('dolphin-persistent.jsonl', 'dolphin-persistent.jsonl.old', 'notes.jsonl',
                     'dolphin-2026.jsonl.old'):
            self.assertFalse(pattern.search(name), name)

        # Only _launch names a session log, once the native side reported no
        # running session: never ensureLayout, the scanner or startup.
        launch = Span(source, 'static Future<DolphinLaunchReport> _launch(')
        at = source.masked.find('_sessionLogPath()')
        calls = 0
        while at >= 0:
            if not span.start - len('static Future<String> _sessionLogPath(') <= at < span.end:
                self.assertTrue(launch.start <= at < launch.end, f'_sessionLogPath() at line {source.line(at)}')
                calls += 1
            at = source.masked.find('_sessionLogPath()', at + 1)
        self.assertGreater(calls, 0)
        session = Span(source, 'static Future<DolphinLaunchReport> _launchSession(')
        self.assertLess(session.find("invokeMethod<bool>('isRunning')", original=True),
                        session.find('await _launch('))
        self.assertEqual(source.masked.count('await _launch('), 1)

class HelperNeverFollowsLinks(unittest.TestCase):
    def test_listings_do_not_follow_links_and_nothing_is_deleted_recursively(self) -> None:
        helper = Source(HELPER)
        lists = [m.start() for m in re.finditer(r'\.list\(', helper.masked)]
        self.assertGreaterEqual(len(lists), 2)
        for at in lists:
            self.assertIn('followLinks: false', helper.masked[at:helper.masked.index(')', at)], helper.line(at))
        for token in ('recursive: true', 'followLinks: true', 'clearTemporaryFiles', 'deleteSync'):
            self.assertNotIn(token, helper.masked, token)
        for token in ('resolveSymbolicLinks()', 'path.isWithin(root, resolved)', 'FileSystemEntityType.file',
                      "endsWith('-Inbox')"):
            self.assertIn(token, helper.text, token)

    def test_the_root_is_the_container_tmp_not_path_providers_temporary_directory(self) -> None:
        # path_provider_foundation's getTemporaryPath() is NSCachesDirectory
        # (Library/Caches on iOS); the picker copies into NSTemporaryDirectory(),
        # the container's tmp beside Documents.
        helper = Source(HELPER)
        self.assertNotIn('getTemporaryDirectory', helper.masked)
        self.assertRegex(helper.masked,
                         r'static Future<Directory> Function\(\) temporaryDirectory =\s*_containerTemporaryDirectory;')
        span = Span(helper, 'static Future<Directory> _containerTemporaryDirectory(')
        self.assertIn('await getApplicationDocumentsDirectory()', helper.masked[span.start:span.end])
        self.assertIn("path.join(path.dirname(documents.path), 'tmp')", helper.text[span.start:span.end])
        self.assertIn('static bool _isIOS() => Platform.isIOS;', helper.masked)
        self.assertRegex(helper.masked, r'static bool Function\(\) pickedPathsAreCopies = _isIOS;')


# ---------------------------------------------------------------------------
# Phase 5d: screen and locale checks of test J (docs/storage-audit-cleanup.md
# § 6, row J, and § 3.10). No "Library/Sources" string in lib/screens/storage/
# nor in lib/l10n/storage_locale.dart (INV-15 stays aggregated under
# « Bibliothèque », § 1); the pages never empty tmp/ nor delete by themselves;
# nothing reaches them from lib/main.dart; every StorageLocale key they use
# exists. `python3 test/storage_contract_test.py` remains the single Python
# gate of the storage lane (§ 5). The behaviour itself is tested by
# test/storage_audit_screen_test.dart and test/storage_tools_row_test.dart.
# ---------------------------------------------------------------------------
PAGES = 'lib/screens/storage'
LOCALE = 'lib/l10n/storage_locale.dart'
TOOLS = 'lib/screens/settings_screen/new_settings_options/tools_settings_content.dart'
PREVIEW = PAGES + '/storage_cleanup_preview_screen.dart'
AUDIT = PAGES + '/storage_audit_screen.dart'
# StorageLocale members that are its API, not catalog keys.
LOCALE_API = {'values', 'codeFor', 'forLocale', 'text', 'format', 'fill', 'categoryKeys',
              'containerKeys', 'levelKeys', 'levelHelpKeys', 'refusalKeys'}


def page_sources():
    files = sorted((ROOT / PAGES).glob('*.dart'))
    return [Source(str(path.relative_to(ROOT))) for path in files]


def catalog():
    """(constants, keys of each language block) of storage_locale.dart."""
    source = Source(LOCALE)
    constants = dict(re.findall(r"static const (\w+) = '(\w+)';", source.text))
    start = source.masked.find('static const Map<String, Map<String, String>> values = {')
    assert start >= 0
    values_end = matching(source.masked, source.masked.index('{', start), '{', '}')
    languages = {}
    for match in re.finditer(r"'(\w+)': \{", source.text[start:values_end]):
        at = start + match.end() - 1
        block = source.masked[at:matching(source.masked, at, '{', '}')]
        languages[match.group(1)] = set(re.findall(r'^\s+(\w+):', block, re.M))
    return constants, languages


class StorageScreensAndLocaleContract(unittest.TestCase):
    def test_the_pages_exist(self) -> None:
        names = {Path(source.relative).name for source in page_sources()}
        self.assertLessEqual({'storage_audit_screen.dart', 'storage_cleanup_preview_screen.dart'}, names)

    def test_the_hidden_library_folder_is_never_named(self) -> None:
        # § 1: comments included, in the pages and in the catalog.
        for source in page_sources() + [Source(LOCALE)]:
            with self.subTest(file=source.relative):
                self.assertNotIn('Sources', source.text)
                self.assertIsNone(re.search(r'library\s*[/\\]+\s*sources', source.text, re.I))
        # Nor reached through its service or its own catalog.
        for source in page_sources():
            for token in ('LibrarySourceFiles', 'library_source_files', 'LibrarySourcesLocale',
                          'library_sources_locale'):
                self.assertNotIn(token, source.text, source.relative + ': ' + token)

    def test_the_pages_never_empty_tmp_nor_delete_by_themselves(self) -> None:
        for source in page_sources():
            with self.subTest(file=source.relative):
                for token in ('clearTemporaryFiles', 'FilePicker', '.delete(', 'deleteSync', 'recursive: true',
                              'resetDatabase', 'UserDataLocationService', '.rawDelete(', 'rawQuery(',
                              'transaction('):
                    self.assertNotIn(token, source.masked, token)
                # SQL lives in string literals, blanked in the masked text.
                self.assertIsNone(re.search(r'\b(?:DELETE|DROP|UPDATE|INSERT|VACUUM)\b', source.text), 'SQL')
                for package in ('dart:io', 'package:file_picker/'):
                    self.assertIsNone(re.search(r"^import\s+'" + re.escape(package), source.text, re.M), package)
        # Only the preview runs a plan, once, after its confirmation dialog,
        # the page's controller layer paused around the dialog: the only
        # `.execute(` of the pages (no database statement either).
        self.assertEqual(sum(source.masked.count('.execute(') for source in page_sources()), 1)
        self.assertNotIn('.execute(', Source(AUDIT).masked)
        preview = Source(PREVIEW)
        self.assertEqual(preview.masked.count('.execute('), 1)
        confirm = Span(preview, 'Future<void> _confirmAndDelete(')
        pause = confirm.find('pausePageNavigation();')
        dialog = confirm.find('showDialog<bool>(')
        resume = confirm.find('resumePageNavigation();')
        refused = confirm.find('if (!confirmed || !mounted) return;')
        run = confirm.find('await _execute(selection);')
        self.assertLess(pause, dialog)
        self.assertLess(dialog, resume)
        self.assertLess(resume, refused)
        self.assertLess(refused, run)
        Span(preview, 'Future<void> _execute(').find('widget.deletionManager.execute(')
        # `_execute(`: its definition and exactly one call, the one after the
        # dialog (review of phase 5d).
        self.assertEqual(preview.masked.count('_execute('), 2)
        self.assertEqual(preview.masked.count('await _execute(selection);'), 1)
        self.assertEqual(confirm.count('_execute('), 1)
        # The selection the deletion receives is the boxes' own.
        self.assertLess(confirm.find('final selection = _selection.selected;'), dialog)
        # Contract replaced by the review of phase 5d: the selection used to
        # start as the plan's preselection whatever the level
        # (`{...widget.plan.preselectedPaths}`); it now starts empty at level
        # 3, whichever of the page or the plan says level 3, and as the plan's
        # preselection at levels 1 and 2 only.
        self.assertNotIn('late final Set<String> _selection = {...widget.plan.preselectedPaths};', preview.masked)
        initial = Span(preview, 'static Set<String> initialSelection(')
        body = preview.masked[initial.start:initial.end]
        self.assertRegex(body, r'level == StorageCleanupLevel\.confirmed \|\|\s+plan\.level == StorageCleanupLevel\.confirmed\s+\? <String>\{\}\s+: \{\.\.\.plan\.preselectedPaths\}')
        self.assertEqual(preview.masked.count('preselectedPaths'), 1, 'only initialSelection reads the preselection')
        self.assertRegex(preview.masked, r'_PreviewSelection _selection = _PreviewSelection\(\s*widget\.plan,\s*'
                                         r'StorageCleanupPreviewScreen\.initialSelection\(widget\.plan, widget\.level\),\s*\);')
        # Lazy lists only (review of phase 5d): the page scrolls a
        # CustomScrollView of slivers; the only SingleChildScrollView left is
        # the confirmation dialog's.
        self.assertIn('child: CustomScrollView(', preview.masked)
        self.assertEqual(preview.masked.count('SingleChildScrollView('), 1)
        self.assertGreater(preview.masked.index('SingleChildScrollView('),
                           preview.masked.index('class _ConfirmDeletionDialogState'))
        self.assertGreaterEqual(preview.masked.count('SliverList.builder('), 3)

    def test_nothing_reaches_the_pages_from_main_or_at_startup(self) -> None:
        main = Source('lib/main.dart')
        for token in ('StorageAuditScreen', 'StorageCleanupPreviewScreen', 'screens/storage/', 'services/storage/',
                      'StorageScanner', 'StorageCleanupPlanner', 'StorageDeletionManager', 'StorageOrphanDetector',
                      'StorageMaintenanceRepository', 'storage_maintenance_repository', 'StorageReport',
                      'StorageLocale', 'storage_locale', 'StorageImportActivity', 'storage_import_activity'):
            self.assertNotIn(token, main.text, token)
        # The storage Tools row (the fourth on iOS) is the only way in.
        for path in dart_files():
            relative = str(path.relative_to(ROOT))
            if relative.startswith(PAGES + '/') or relative == TOOLS:
                continue
            masked = Source(relative).masked
            for token in ('StorageAuditScreen(', 'StorageCleanupPreviewScreen('):
                self.assertNotIn(token, masked, relative + ': ' + token)
        tools = Source(TOOLS)
        self.assertEqual(tools.masked.count('StorageAuditScreen('), 1)
        self.assertIn('bool get _showStorageAudit => defaultTargetPlatform == TargetPlatform.iOS;', tools.masked)
        # Fifth row: the Cheats & Enhancements catalogue (docs/ENHANCEMENTS.md).
        self.assertIn('int getItemCount() => _showBiosChecker ? 5 : 2;', tools.masked)
        select = Span(tools, 'void selectItem(')
        self.assertLess(select.find('if (index == 3 && _showStorageAudit) {'), select.find('_openStorageAudit();'))

    def test_every_key_the_pages_use_exists_in_the_twelve_languages(self) -> None:
        constants, languages = catalog()
        for name, value in constants.items():
            self.assertEqual(name, value)
        self.assertEqual(len(languages), 12)
        for language, keys in languages.items():
            self.assertEqual(keys, set(constants), language)
        used = set()
        literal = re.compile(r"\bStorageLocale\.(?:text|format|forLocale)\(\s*[^,()]+,\s*'(\w+)'")
        for source in page_sources() + [Source(TOOLS)]:
            for match in re.finditer(r'\bStorageLocale\.(\w+)', source.masked):
                if match.group(1) in LOCALE_API:
                    continue
                self.assertIn(match.group(1), constants, f'{source.relative}:{source.line(match.start())}')
                used.add(match.group(1))
            for match in literal.finditer(source.text):
                self.assertIn(match.group(1), constants, f'{source.relative}:{source.line(match.start())}')
                used.add(match.group(1))
        self.assertGreaterEqual(len(used), 70, 'the pages name their texts from StorageLocale')
        self.assertLessEqual({'toolTitle', 'toolSubtitle'}, used, 'the Tools row texts')
        # The root labels the pages show come from the registry.
        labels = set(re.findall(r"labelKey: '(\w+)'", Source('lib/services/storage/storage_roots.dart').text))
        self.assertTrue(labels)
        self.assertLessEqual(labels, set(constants))

    def test_sizes_are_formatted_by_the_shared_helper_only(self) -> None:
        # Decimal units as the Files app shows them, never translated.
        sources = page_sources()
        self.assertEqual(sum(source.masked.count('formatBytes(') for source in sources), 1)
        for source in sources:
            for unit in re.finditer(r"'[^'\n]*\b(?:KB|MB|GB|TB|Ko|Mo|Go|To)\b[^'\n]*'", source.text):
                self.fail(f'{source.relative}:{source.line(unit.start())} spells a size unit')


# ---------------------------------------------------------------------------
# Imports in progress (review of phase 5d, docs/storage-audit-cleanup.md
# § 3.7). Every import that follows a Files pick runs inside
# StorageImportActivity.run, from the pick to the end of its processing: the
# session guard reports it (`importActive`), the planner then refuses the
# whole plan and the deletion manager stops. The behaviour is tested by
# test/storage_import_activity_test.dart, the planner, deletion manager and
# screen tests; this section pins where the imports are wrapped and that no
# pick escapes the list.
# ---------------------------------------------------------------------------
ACTIVITY = 'lib/services/storage/storage_import_activity.dart'
PLANNER = 'lib/services/storage/storage_cleanup_planner.dart'
MANAGER = 'lib/services/storage/storage_deletion_manager.dart'
WRAP = 'StorageImportActivity.run('
# `part of` files import through their library.
LIBRARY_OF = {'lib/widgets/system_emulator_settings_dialog/tabs.dart': 'lib/widgets/system_emulator_settings_dialog.dart'}

# file -> signatures whose whole body is `=> StorageImportActivity.run(...)`.
# Extending or shrinking this list is a contract change.
IMPORT_SITES = {
    'lib/services/libretro_internal_service.dart': (
        'static Future<LibretroImportResult> importGames(',
        'static Future<LibretroRetroArchCopy?> copyRetroArchData(',),
    'lib/services/libretro_skin_service.dart': (
        'Future<LibretroSkinImportResult?> pickAndImport(',),
    'lib/services/dolphin_internal_v2_service.dart': (
        'static Future<DolphinImportResult> importGames(',),
    'lib/services/dolphin_smart_import_service.dart': (
        'static Future<DolphinSmartImportResult> importGames(',),
    'lib/services/armsx2_internal_service.dart': (
        'static Future<Armsx2ImportResult> importGames(',
        'static Future<Armsx2ImportResult> importBios(',),
    'lib/services/rpcs3_internal_service.dart': (
        'static Future<bool> importFirmware(',
        'static Future<Rpcs3ImportResult> importGames(',
        'static Future<bool> importExtractedGameFolder(',),
    'lib/services/rpcs3_content_import_service.dart': (
        'static Future<Rpcs3ImportResult> importGames(',
        'static Future<bool> importExtractedGameFolder(',),
    # Build 554: the RPCS3 installation of a library-folder PS3 disc, started
    # from its launch (no pick: the file is already in the library folder).
    'lib/services/rpcs3_library_file_service.dart': (
        'static Future<Rpcs3LibraryFileOutcome> install(',),
    'lib/services/rpcs3_save_exchange_service.dart': (
        'Future<Rpcs3SaveImportReport?> importGuarded(',),
    'lib/services/rpcs3_rap_licence_service.dart': (
        'static Future<Rpcs3RapImportReport?> importFromFiles(',),
    'lib/services/pairing_file_service.dart': (
        'static Future<PairingFileImportResult?> importFromPicker(',),
    'lib/services/home_music_service.dart': (
        'Future<bool> _pickAndStoreMusic(',),
    'lib/services/library_local_library_service.dart': (
        'Future<List<LibraryImportOutcome>?> pickAndImport(',),
    'lib/screens/libretro/libretro_3ds_system_screen.dart': (
        'Future<void> _import(',),
    'lib/screens/libretro/libretro_library_actions.dart': (
        'Future<LibretroLibraryMoveOutcome?> moveLibraryIntoNeoStation(',),
    'lib/screens/settings_screen/new_settings_options/themes_settings_content.dart': (
        'Future<void> _pickCustomBackground(',),
    'lib/screens/game_screen/game_settings_dialog/game_settings_scrapping_tab.dart': (
        'Future<void> _replaceImage(',),
    'lib/widgets/system_emulator_settings_dialog/tabs.dart': (
        'Future<void> _pickAndSaveImage(',
        'Future<void> _pickAndSaveLogoImage(',),
    # Embedded MeloNX: game, firmware, keys, update/DLC and the standalone
    # app's data transfer, each wholly inside StorageImportActivity.run.
    'lib/services/melonx_embedded_library_service.dart': (
        'static Future<bool> importGame(',
        'static Future<bool> importFirmware(',
        'static Future<MelonxKeysReport> importKeys(',
        'static Future<MelonxAddonReport> importAddon(',),
    'lib/widgets/melonx_transfer_dialog.dart': (
        'Future<bool> showMelonxTransfer(',),
}

# Dolphin's system files (IPL, Wii keys, system folders): every body given
# to `_withSystemImport(` runs inside the wrapper, which holds the run.
SYSTEM_WRAPPER = ('lib/services/dolphin_internal_v2_service.dart',
                  'static Future<T> _withSystemImport<T>(', '_withSystemImport(')

# Pick helpers reached only from a wrapped import of their own file: helper
# -> (how it is called, the wrapped import calling it).
PICK_HELPERS = {
    'lib/screens/libretro/libretro_3ds_system_screen.dart': {
        'Future<List<String>?> _pickFiles(': ('_pickFiles()', 'Future<void> _import('),
        'Future<String?> _pickFolder(': ('_pickFolder()', 'Future<void> _import('),
    },
    'lib/services/melonx_embedded_library_service.dart': {
        'static Future<File?> pick(': ('await pick(', ('static Future<bool> importGame(',
                                                     'static Future<bool> importFirmware(')),
    },
    # The default `_picker` of the service.
    'lib/services/library_local_library_service.dart': {
        'Future<LibraryPickedFiles?> libraryPickBookFiles(': (
            '_picker()', 'Future<List<LibraryImportOutcome>?> pickAndImport('),
    },
}

PICKS = ('FilePicker.pickFiles(', 'FilePicker.getDirectoryPath(', 'FilePicker.saveFile(',
         'ExternalFolderAccess.pickAndActivateFolder(', 'ExternalFolderAccess.pickAndBookmarkFolder(')

# Picks that start no import into the container, by file and count: folder
# links (bookmarked and scanned where they are, nothing copied under tmp/),
# desktop executables (a path saved in the settings) and the Library's
# catalogue file (read at once, in the library lane, which this lane does not
# edit; its copy waits the picker's hour like any other).
NOT_IMPORTS = {
    'lib/providers/sqlite_config_provider/scanning.dart': {'FilePicker.getDirectoryPath(': 1},
    'lib/screens/settings_screen/new_settings_options/directories_settings_content.dart': {
        'FilePicker.getDirectoryPath(': 3, 'ExternalFolderAccess.pickAndBookmarkFolder(': 1},
    'lib/widgets/setup_wizard.dart': {
        'FilePicker.getDirectoryPath(': 2, 'ExternalFolderAccess.pickAndActivateFolder(': 1},
    'lib/widgets/system_emulator_settings_dialog.dart': {'FilePicker.pickFiles(': 2},
    'lib/screens/library_screen/library_sources_view.dart': {'FilePicker.pickFiles(': 1},
}


class Range:
    def __init__(self, start: int, end: int) -> None:
        self.start, self.end = start, end


class ImportsInProgress(unittest.TestCase):
    def test_the_activity_is_a_counter_released_in_a_finally(self) -> None:
        source = Source(ACTIVITY)
        run = Span(source, 'static Future<T> run<T>(')
        increment = run.find('_running++;')
        body = run.find('return await body();')
        decrement = run.find('_running--;')
        self.assertLess(increment, run.find('try {'))
        self.assertLess(run.find('try {'), body)
        self.assertLess(body, run.find('} finally {'))
        self.assertLess(run.find('} finally {'), decrement)
        self.assertIn('static bool get active => _running > 0;', source.masked)
        for package in ('dart:io', 'package:file_picker/'):
            self.assertNotIn(package, source.text)

    def test_the_guard_reads_it_and_refuses_the_whole_plan(self) -> None:
        planner = Source(PLANNER)
        self.assertIn('static bool _importRunning() => StorageImportActivity.active;', planner.masked)
        self.assertIn('_importActive = importActive ?? _importRunning', planner.masked)
        # Contract replaced by the review of the storage services (12 October
        # 2026): a library scan in progress also refuses the whole plan and
        # stops a deletion, under its own reason. The getter used to read
        # `launchActive || importActive`, the plan to test
        # `session.wholeCleanupRefused` and the deletion to set `_stopped`
        # from it; the plan and the deletion now read the reason, null only
        # when no game, import or library scan runs. The scan probe the
        # screens do not give fails closed (counted as a scan).
        self.assertRegex(planner.masked,
                         r'bool get wholeCleanupRefused =>\s+launchActive \|\| importActive \|\| libraryScanActive;')
        self.assertRegex(planner.masked,
                         r'StorageRefusalReason\? get wholeCleanupReason => launchActive \|\| importActive\s+'
                         r'\? StorageRefusalReason\.sessionActive\s+: libraryScanActive\s+'
                         r'\? StorageRefusalReason\.libraryScanActive\s+: null;')
        self.assertIn('_libraryScanActive = libraryScanActive ?? _libraryScanUnknown', planner.masked)
        self.assertRegex(planner.masked, r'static bool _libraryScanUnknown\(\) =>\s+throw StateError\(')
        plan = Span(planner, 'Future<StorageCleanupPlan> plan(')
        self.assertLess(plan.find('final refused = session.wholeCleanupReason;'), plan.find('if (refused != null) {'))
        self.assertLess(plan.find('if (refused != null) {'), plan.find('_PlanBuilder('))
        manager = Source(MANAGER)
        check = Span(manager, 'Future<void> _checkSession(')
        self.assertLess(check.find('final reason = _state.wholeCleanupReason;'),
                        check.find('if (reason != null && !_stopped) {'))
        self.assertLess(check.find('if (reason != null && !_stopped) {'), check.find('_stopped = true;'))
        # Read by the guard only; reset by the tests only. Contract extended
        # (6ddf9d7c, embedded MeloNX): the Switch playlist also reads it, to
        # skip its library discovery while an import runs; it never writes it.
        melonx_reader = 'lib/widgets/melonx_internal_playlist_actions.dart'
        discover = Span(Source(melonx_reader), 'Future<void> _discover(')
        self.assertEqual(Source(melonx_reader).masked.count('StorageImportActivity.active'), 1)
        self.assertEqual(discover.count('StorageImportActivity.active'), 1)
        self.assertLess(discover.find('StorageImportActivity.active'), discover.find('return;'))
        for path in dart_files():
            relative = str(path.relative_to(ROOT))
            masked = Source(relative).masked
            if relative not in (ACTIVITY, PLANNER, melonx_reader):
                self.assertNotIn('StorageImportActivity.active', masked, relative)
            if relative != ACTIVITY:
                self.assertNotIn('StorageImportActivity.reset(', masked, relative)

    def test_every_listed_import_runs_inside_the_activity(self) -> None:
        for relative, signatures in IMPORT_SITES.items():
            source = Source(relative)
            library = Source(LIBRARY_OF.get(relative, relative))
            self.assertIsNotNone(
                re.search(r"(?m)^import '(?:[^']*services/|(?:\.\./)*)storage/storage_import_activity\.dart';$",
                          library.text),
                relative)
            for signature in signatures:
                with self.subTest(site=relative + ': ' + signature):
                    span = Span(source, signature)
                    self.assertRegex(source.masked[span.start:span.end], r'^=>\s*StorageImportActivity\.run\(')
                    self.assertEqual(span.count(WRAP), 1)
        relative, signature, call = SYSTEM_WRAPPER
        source = Source(relative)
        wrapper = Span(source, signature)
        self.assertLess(wrapper.find('throw const DolphinSystemFilesException('),
                        wrapper.find('return await StorageImportActivity.run(action);'))

    def test_no_pick_escapes_the_list(self) -> None:
        covered = {}
        for relative, signatures in IMPORT_SITES.items():
            source = Source(relative)
            covered.setdefault(relative, []).extend(Span(source, s) for s in signatures)
        relative, signature, call = SYSTEM_WRAPPER
        source = Source(relative)
        wrapped = 0
        for match in re.finditer(r'=>\s*' + re.escape(call), source.masked):
            # The declaration owning this `=> _withSystemImport(` body.
            start = source.masked.rfind('static Future<', 0, match.start())
            end = matching(source.masked, match.end() - 1, '(', ')')
            covered[relative].append(Range(start, end))
            wrapped += 1
        # IPL, Wii system files, system folder.
        self.assertEqual(wrapped, 3)
        for relative, helpers in PICK_HELPERS.items():
            source = Source(relative)
            importer = None
            for helper, (call, owners) in helpers.items():
                span = Span(source, helper)
                owners = (owners,) if isinstance(owners, str) else owners
                importers = [Span(source, owner) for owner in owners]
                name = call[:-1]
                declaration = source.masked.find(helper) + helper.index(name) if name in helper else -1
                calls = [m.start() for m in re.finditer(re.escape(call), source.masked) if m.start() != declaration]
                self.assertTrue(calls, helper)
                for at in calls:
                    if span.start <= at < span.end:
                        continue
                    self.assertTrue(any(importer.start <= at < importer.end for importer in importers),
                                    f'{relative}: {call} outside {owners}')
                covered.setdefault(relative, []).append(span)
        # The MeloNX pick helper is public: its only other caller is the
        # wrapped standalone-data transfer.
        transfer = Source('lib/widgets/melonx_transfer_dialog.dart')
        transfer_import = Span(transfer, 'Future<bool> showMelonxTransfer(')
        outside = [m.start() for m in re.finditer(re.escape('MelonxEmbeddedLibraryService.pick('), transfer.masked)]
        self.assertTrue(outside)
        for at in outside:
            self.assertTrue(transfer_import.start <= at < transfer_import.end, 'MeloNX pick outside its transfer')
        for path in dart_files():
            relative = str(path.relative_to(ROOT))
            if relative not in ('lib/services/melonx_embedded_library_service.dart',
                                'lib/widgets/melonx_transfer_dialog.dart'):
                self.assertNotIn('MelonxEmbeddedLibraryService.pick(', Source(relative).masked, relative)
        # The book picker is reached through `_picker` only.
        library = Source('lib/services/library_local_library_service.dart')
        self.assertIn('_picker = picker ?? libraryPickBookFiles,', library.masked)
        self.assertEqual(sum(Source(str(path.relative_to(ROOT))).masked.count('libraryPickBookFiles')
                             for path in dart_files()), 2)
        unlisted = {}
        for path in dart_files():
            relative = str(path.relative_to(ROOT))
            if relative.startswith('lib/services/storage/'):
                continue
            source = Source(relative)
            for token in PICKS:
                for match in re.finditer(re.escape(token), source.masked):
                    at = match.start()
                    if any(span.start <= at < span.end for span in covered.get(relative, ())):
                        continue
                    unlisted.setdefault(relative, {}).setdefault(token, 0)
                    unlisted[relative][token] += 1
        self.maxDiff = None
        self.assertEqual(unlisted, NOT_IMPORTS)


if __name__ == '__main__':
    unittest.main(verbosity=2)
