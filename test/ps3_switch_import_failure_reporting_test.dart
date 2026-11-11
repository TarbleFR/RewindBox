import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_link_locale.dart';
import 'package:neostation/l10n/melonx_transfer_locale.dart';
import 'package:neostation/l10n/rpcs3_ui_locale.dart';
import 'package:neostation/services/melonx_embedded_library_service.dart';
import 'package:neostation/services/melonx_internal_service.dart';
import 'package:neostation/services/rpcs3_content_import_service.dart';
import 'package:neostation/widgets/library_folder_report_dialog.dart';
import 'package:neostation/widgets/melonx_internal_playlist_actions.dart';
import 'package:neostation/widgets/rpcs3_import_report.dart';

void main() {
  const tags = [
    'en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'id', 'ja', 'ko', 'zh', 'zh_Hant',
  ];
  String en(String key) => Rpcs3UiLocale.textForLocale('en', key);

  group('PS3 import messages', () {
    test('a keys-only selection is refused with a reason per key', () {
      final keys = <String, String>{};
      final games = <String>[];
      final unsupported = Rpcs3ImportMessages.classifySelection(
        ['/a/Game.key', '/a/Other.dkey'],
        keys,
        games,
      );
      expect(unsupported, isEmpty);
      expect(games, isEmpty);
      const picked = ['/a/Game.key', '/a/Other.dkey'];
      final refusals = Rpcs3ImportMessages.keysOnlyRefusals(picked, games, en);
      expect(refusals, hasLength(2));
      expect(refusals.first, startsWith('Game.key — '));
      expect(refusals.first, contains('.iso'));
      // Two key files of the same game are two picked files: two lines.
      expect(
        Rpcs3ImportMessages.keysOnlyRefusals(
          const ['/a/Game.key', '/a/Game.dkey'],
          games,
          en,
        ),
        hasLength(2),
      );
    });

    test('keys with a game file are not refused', () {
      final keys = <String, String>{};
      final games = <String>[];
      final unsupported = Rpcs3ImportMessages.classifySelection(
        ['/a/Game.iso', '/a/Game.key', '/a/readme.txt'],
        keys,
        games,
      );
      expect(unsupported, ['readme.txt']);
      expect(games, ['/a/Game.iso']);
      expect(
        Rpcs3ImportMessages.keysOnlyRefusals(
          const ['/a/Game.iso', '/a/Game.key', '/a/readme.txt'],
          games,
          en,
        ),
        isEmpty,
      );
    });

    test('refusal summary lists five lines then the remainder', () {
      final errors = [for (var i = 1; i <= 8; i++) 'f$i — reason'];
      final lines = Rpcs3ImportMessages.refusalSummary(errors, en).split('\n');
      expect(lines.first, '8 file(s) not imported:');
      expect(lines.sublist(1, 6), errors.take(5));
      expect(lines.last, 'and 3 more');
      expect(lines, hasLength(7));
      final few = Rpcs3ImportMessages.refusalSummary(['a — b'], en).split('\n');
      expect(few, ['1 file(s) not imported:', 'a — b']);
    });

    test('picker and disk-space errors map to sentences', () {
      expect(
        Rpcs3ImportMessages.describeKnownError(
          PlatformException(code: 'PICKER_BUSY'),
          en,
        ),
        en('pickerBusy'),
      );
      expect(
        Rpcs3ImportMessages.describeKnownError(
          PlatformException(code: 'NO_ROOT_VC'),
          en,
        ),
        en('pickerNoRoot'),
      );
      expect(
        Rpcs3ImportMessages.describeKnownError(
          const FileSystemException('x', '/p', OSError('No space', 28)),
          en,
        ),
        en('noSpace'),
      );
      expect(
        Rpcs3ImportMessages.describeKnownError(StateError('other'), en),
        isNull,
      );
    });

    test('a refused folder is told what its own layout lacks', () {
      final root = Directory.systemTemp.createTempSync('ps3-folder-');
      addTearDown(() => root.deleteSync(recursive: true));
      Directory make(String name) => Directory('${root.path}/$name')..createSync(recursive: true);
      void touch(String file) => File('${root.path}/$file')
        ..createSync(recursive: true)
        ..writeAsStringSync('x');

      // Not a game folder at all: the two files of the disc layout.
      final other = make('photos');
      expect(
        Rpcs3ImportMessages.missingInGameFolder(other.path),
        'PS3_GAME/PARAM.SFO, PS3_GAME/USRDIR/EBOOT.BIN',
      );

      // Disc layout without its executable: only the executable.
      make('disc/PS3_GAME/USRDIR');
      touch('disc/PS3_GAME/PARAM.SFO');
      expect(
        Rpcs3ImportMessages.missingInGameFolder('${root.path}/disc'),
        'PS3_GAME/USRDIR/EBOOT.BIN',
      );

      // Flat layout without PARAM.SFO: PS3_GAME is not asked for.
      touch('flat/USRDIR/EBOOT.BIN');
      expect(
        Rpcs3ImportMessages.missingInGameFolder('${root.path}/flat'),
        'PARAM.SFO',
      );

      // An empty PS3_GAME folder: both of its files.
      make('empty/PS3_GAME');
      expect(
        Rpcs3ImportMessages.missingInGameFolder('${root.path}/empty'),
        'PS3_GAME/PARAM.SFO, PS3_GAME/USRDIR/EBOOT.BIN',
      );
    });

    test('a long refusal list is shown whole by the report', () {
      final errors = [for (var i = 1; i <= 8; i++) 'f$i — reason'];
      expect(rpcs3ImportNeedsReport(errors), isTrue);
      expect(rpcs3ImportNeedsReport(errors.take(5).toList()), isFalse);
      final lines = rpcs3ImportReportLines(
        imported: 2,
        errors: errors,
        refreshError: 'refresh failed',
        t: en,
      );
      final texts = [for (final line in lines) line.text];
      expect(texts.first, '2 PS3 game(s) imported.');
      expect(texts[1], '8 file(s) not imported:');
      // Every refused file is named: none is summed up as "and N more".
      expect(texts.sublist(2, 10), errors);
      expect(texts.last, 'refresh failed');
      expect(lines.last.kind, LibraryReportLineKind.problem);
    });

    test('a failed list refresh tells the installation is done and what to do', () {
      for (final tag in tags) {
        final text = Rpcs3UiLocale.textForLocale(tag, 'libraryRefreshFailed');
        expect(text, contains('{error}'), reason: tag);
        expect(text, contains('RewindBox'), reason: tag);
      }
      expect(en('libraryRefreshFailed'), startsWith('Installed'));
    });

    test('new PS3 keys exist, differ from English and keep placeholders', () {
      const keys = {
        'keysOnlySelected': <String>[],
        'folderNotGame': ['{folder}', '{missing}'],
        'libraryRefreshFailed': ['{error}'],
        'refusedHeader': ['{count}'],
        'refusedMore': ['{count}'],
        'pickerBusy': <String>[],
        'pickerNoRoot': <String>[],
        'pickerEmptyPath': <String>[],
        'noSpace': <String>[],
      };
      for (final tag in tags) {
        for (final entry in keys.entries) {
          final text = Rpcs3UiLocale.textForLocale(tag, entry.key);
          expect(text.trim(), isNotEmpty, reason: '$tag ${entry.key}');
          expect(text, isNot(entry.key), reason: '$tag ${entry.key}');
          if (tag != 'en') {
            expect(text, isNot(en(entry.key)), reason: '$tag ${entry.key}');
          }
          for (final placeholder in entry.value) {
            expect(text, contains(placeholder), reason: '$tag ${entry.key}');
          }
        }
      }
    });
  });

  group('Switch import validation', () {
    const ext = {'nsp', 'xci'};

    test('wrong, missing or absent extension names the accepted ones', () {
      expect(
        MelonxEmbeddedLibraryService.validatePicked(
          '/a/game.zip',
          ext,
          exists: true,
          length: 5,
        ),
        'wrongExtension:.nsp, .xci',
      );
      expect(
        MelonxEmbeddedLibraryService.validatePicked(
          '/a/noextension',
          ext,
          exists: true,
          length: 5,
        ),
        startsWith('wrongExtension:'),
      );
    });

    test('missing and empty files have distinct keys', () {
      expect(
        MelonxEmbeddedLibraryService.validatePicked(
          '/a/game.NSP',
          ext,
          exists: false,
          length: 0,
        ),
        'fileUnreadable',
      );
      expect(
        MelonxEmbeddedLibraryService.validatePicked(
          '/a/game.nsp',
          ext,
          exists: true,
          length: 0,
        ),
        'emptyFile',
      );
      expect(
        MelonxEmbeddedLibraryService.validatePicked(
          '/a/game.nsp',
          ext,
          exists: true,
          length: 1,
        ),
        isNull,
      );
    });

    test('copy failures map disk-full and keep other OS text', () {
      expect(
        MelonxEmbeddedLibraryService.copyFailure(
          const FileSystemException('w', '/p', OSError('No space', 28)),
        ).message,
        'insufficientSpace',
      );
      expect(
        MelonxEmbeddedLibraryService.copyFailure(
          const FileSystemException('w', '/p', OSError('Permission denied', 13)),
        ).message,
        'copyFailed:Permission denied',
      );
    });

    test('failure message uses keys and appends unknown technical text', () {
      String t(String key) => MelonxTransferLocale.forLocale(
        const Locale('en'),
        key,
      );
      expect(
        melonxFailureMessage(const FormatException('invalidContent'), t),
        MelonxTransferLocale.values['en']!['invalidContent'],
      );
      expect(
        melonxFailureMessage(
          const FormatException('wrongExtension:.nsp'),
          t,
        ),
        contains('.nsp'),
      );
      // A folder the system picker did not give keeps its own reason.
      const busy = ExternalFolderAccessException('PICKER_BUSY', message: 'busy');
      expect(
        melonxFailureMessage(
          busy,
          t,
          folderFailure: (error) => LibraryLinkLocale.failureFor('en', error),
        ),
        LibraryLinkLocale.textFor('en', 'pickerBusy'),
      );
      expect(
        melonxFailureMessage(busy, t),
        MelonxTransferLocale.values['en']!['folderAccessLost'],
      );
      // A native diagnostic, a system error or an unexpected exception is
      // shown after the generic sentence instead of being dropped.
      final failed = MelonxTransferLocale.values['en']!['failed']!;
      expect(
        melonxFailureMessage(
          MelonxContentException('failed', 'title key missing'),
          t,
        ),
        '$failed title key missing',
      );
      expect(
        melonxFailureMessage(StateError('Missing MeloNX content response'), t),
        '$failed Missing MeloNX content response',
      );
      expect(
        melonxFailureMessage(
          PlatformException(code: 'E', message: 'native text'),
          t,
        ),
        '$failed native text',
      );
      // A known native code keeps its own sentence.
      expect(
        melonxFailureMessage(MelonxContentException('invalidContent', 'x'), t),
        MelonxTransferLocale.values['en']!['invalidContent'],
      );
      // A long technical detail is cut in the notice (app.log has it all).
      final long = melonxFailureMessage(FormatException('x' * 600), t);
      expect(long.length, lessThan(failed.length + melonxFailureDetailLimit + 4));
      expect(long, endsWith('…'));
      // What the add-on report stores, then shows, for a copy that failed.
      expect(
        MelonxEmbeddedLibraryService.refusalCode(
          const FormatException('copyFailed:Is a directory'),
        ),
        'copyFailed:Is a directory',
      );
      expect(
        MelonxEmbeddedLibraryService.refusalCode(StateError('boom')),
        startsWith('failed:'),
      );
      String fr(String key) =>
          MelonxTransferLocale.forLocale(const Locale('fr'), key);
      final shown = melonxFailureMessage(
        const FormatException('copyFailed:Is a directory'),
        fr,
      );
      expect(shown, contains('Is a directory'));
      expect(shown, isNot(contains('The operation failed')));
      final unknown = melonxFailureMessage(
        const FormatException('weird technical text'),
        t,
      );
      expect(unknown, startsWith(MelonxTransferLocale.values['en']!['failed']!));
      expect(unknown, endsWith('weird technical text'));
    });

    test('every language has the new Switch keys', () {
      const keys = [
        'invalidContent',
        'wrongExtension',
        'emptyFile',
        'fileUnreadable',
        'folderAccessLost',
        'copyFailed',
      ];
      final english = MelonxTransferLocale.values['en']!;
      expect(MelonxTransferLocale.values, hasLength(12));
      for (final entry in MelonxTransferLocale.values.entries) {
        for (final key in keys) {
          final text = entry.value[key];
          expect(text, isNotNull, reason: '${entry.key} $key');
          expect(text!.trim(), isNotEmpty, reason: '${entry.key} $key');
          if (entry.key != 'en') {
            expect(text, isNot(english[key]), reason: '${entry.key} $key');
          }
        }
        expect(entry.value['wrongExtension'], contains('{detail}'));
        expect(entry.value['copyFailed'], contains('{detail}'));
      }
    });
  });
}
