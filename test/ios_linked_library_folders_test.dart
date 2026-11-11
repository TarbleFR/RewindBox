import 'dart:io';
import 'dart:ui' show Locale;

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_database_service.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/l10n/library_link_locale.dart';
import 'package:neostation/services/ios_library_root_relocation.dart';
import 'package:neostation/services/ios_linked_library_folders.dart';
import 'package:sqlite3/sqlite3.dart';

/// Library folders outside the application on iOS (11 November 2026): a
/// tester's linked folder was no longer given back after an update; nothing
/// said so, its games were dropped by the next scan and picking a folder
/// again "did nothing". These tests hold the rules that replace that.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const appGroup = '/private/var/mobile/Containers/Shared/AppGroup/D64BBD85-0CBC-452D-9492-336D580EFECC';
  const linked = '$appGroup/File Provider Storage/Roms';
  const oldOwn = '/var/mobile/Containers/Data/Application/B59D6A89-908A-4531-8034-FC8908E7BD6E';
  const newOwn = '/var/mobile/Containers/Data/Application/6AA78A94-8BA7-4733-BFC3-66B22495B12A';

  Future<bool> Function(String) existing(Set<String> folders) => (folder) async => folders.contains(folder);

  group('a folder that does not open keeps its games', () {
    test('only folders outside the app\'s own container are kept waiting', () async {
      final unreachable = await SqliteDatabaseService.unreachableLibraryRoots(
        <String>['$newOwn/Documents/roms', '$newOwn/Documents/gone', linked, 'content://tree/abc', ''],
        ownContainer: '/private$newOwn',
        exists: existing({'$newOwn/Documents/roms'}),
      );
      expect(unreachable, <String>[linked],
          reason: 'a missing folder of the own container was deleted; a linked folder only lost its access');
    });

    test('without a known own container every missing plain folder is kept', () async {
      final unreachable = await SqliteDatabaseService.unreachableLibraryRoots(
        <String>['$newOwn/Documents/gone', linked],
        exists: existing(<String>{}),
      );
      expect(unreachable, <String>['$newOwn/Documents/gone', linked]);
    });

    test('a folder that throws while it is probed counts as not open', () async {
      final unreachable = await SqliteDatabaseService.unreachableLibraryRoots(
        <String>[linked],
        exists: (_) async => throw const FileSystemException('denied'),
      );
      expect(unreachable, <String>[linked]);
    });

    test('a game row is under a folder only below its separator', () {
      expect(SqliteDatabaseService.isUnderLibraryRoot('$linked/gc/Melee.rvz', <String>[linked]), isTrue);
      expect(SqliteDatabaseService.isUnderLibraryRoot('$linked/Zelda.sfc', <String>['$linked/']), isTrue);
      expect(SqliteDatabaseService.isUnderLibraryRoot('${linked}Other/gc/Melee.rvz', <String>[linked]), isFalse);
      expect(SqliteDatabaseService.isUnderLibraryRoot(linked, <String>[linked]), isFalse);
      expect(SqliteDatabaseService.isUnderLibraryRoot('$linked/gc/Melee.rvz', const <String>[]), isFalse);
    });
  });

  group('the games follow a folder that iOS moved', () {
    test('a moved folder is paired with its new path; a dropped duplicate moves nowhere', () {
      final before = <String>['$oldOwn/Documents/roms', '$oldOwn/Documents/MeloNX/roms', linked];
      final after = <String>['$newOwn/Documents/roms', '$newOwn/Documents/MeloNX/roms', linked];
      expect(IosLibraryRootRelocation.moves(before, after), <({String from, String to})>[
        (from: '$oldOwn/Documents/roms', to: '$newOwn/Documents/roms'),
        (from: '$oldOwn/Documents/MeloNX/roms', to: '$newOwn/Documents/MeloNX/roms'),
      ]);
      expect(
        IosLibraryRootRelocation.moves(<String>['$oldOwn/Documents/roms', '$newOwn/Documents/roms'], <String>['$newOwn/Documents/roms']),
        isEmpty,
        reason: 'the new path was already registered: the old rows are not moved onto it',
      );
    });

    test('rows keep their play time and favourite at the new path; a row already there is not overwritten', () {
      final db = sqlite3.openInMemory();
      addTearDown(db.dispose);
      db.execute('CREATE TABLE user_roms (rom_path TEXT NOT NULL COLLATE NOCASE, play_time INTEGER, is_favorite INTEGER, UNIQUE(rom_path))');
      final insert = db.prepare('INSERT INTO user_roms (rom_path, play_time, is_favorite) VALUES (?, ?, ?)');
      insert.execute(<Object?>['$oldOwn/Documents/roms/snes/Zelda.sfc', 3600, 1]);
      insert.execute(<Object?>['$oldOwn/Documents/roms/gba/Métroïd 🚀.gba', 120, 0]);
      insert.execute(<Object?>['$oldOwn/Documents/roms/snes/Mario.smc', 50, 0]);
      insert.execute(<Object?>['$newOwn/Documents/roms/snes/Mario.smc', 7, 1]);
      insert.execute(<Object?>['$oldOwn/Documents/romsOther/snes/Other.sfc', 9, 0]);
      insert.execute(<Object?>['$linked/gc/Melee.rvz', 10, 1]);
      insert.dispose();

      final statement = SqliteService.romPathRelocation('$oldOwn/Documents/roms', '$newOwn/Documents/roms');
      db.execute(statement.sql, statement.arguments);
      expect(db.updatedRows, 2);

      final rows = <String, List<Object?>>{
        for (final row in db.select('SELECT rom_path, play_time, is_favorite FROM user_roms'))
          row['rom_path'] as String: <Object?>[row['play_time'], row['is_favorite']],
      };
      expect(rows['$newOwn/Documents/roms/snes/Zelda.sfc'], <Object?>[3600, 1]);
      expect(rows['$newOwn/Documents/roms/gba/Métroïd 🚀.gba'], <Object?>[120, 0]);
      expect(rows['$newOwn/Documents/roms/snes/Mario.smc'], <Object?>[7, 1], reason: 'the row already at the new path wins');
      expect(rows['$oldOwn/Documents/roms/snes/Mario.smc'], <Object?>[50, 0], reason: 'left for the scan to drop, as before');
      expect(rows['$oldOwn/Documents/romsOther/snes/Other.sfc'], <Object?>[9, 0], reason: 'another folder with the same prefix');
      expect(rows['$linked/gc/Melee.rvz'], <Object?>[10, 1]);
      expect(rows, hasLength(6));
    });

    test('a folder name with a character outside the basic plane is measured in characters', () {
      final db = sqlite3.openInMemory();
      addTearDown(db.dispose);
      db.execute('CREATE TABLE user_roms (rom_path TEXT NOT NULL COLLATE NOCASE, UNIQUE(rom_path))');
      db.execute('INSERT INTO user_roms (rom_path) VALUES (?)', <Object?>['$oldOwn/Documents/🎮 roms/snes/Zelda.sfc']);
      final statement = SqliteService.romPathRelocation('$oldOwn/Documents/🎮 roms', '$newOwn/Documents/🎮 roms');
      db.execute(statement.sql, statement.arguments);
      expect(db.select('SELECT rom_path FROM user_roms').single['rom_path'], '$newOwn/Documents/🎮 roms/snes/Zelda.sfc');
    });
  });

  group('one saved access per added folder', () {
    test('the list survives a damaged value and keeps one entry per slot', () {
      expect(IosLinkedLibraryFolders.decode(null), isEmpty);
      expect(IosLinkedLibraryFolders.decode('not json'), isEmpty);
      expect(IosLinkedLibraryFolders.decode('{"key":"a"}'), isEmpty);
      final folders = IosLinkedLibraryFolders.decode(
        '[{"key":"library-a","root":"/x"},{"key":"library-a","root":"/y"},{"key":"","root":"/z"},7,{"key":"library-b","root":"/y"}]',
      );
      expect(folders.map((folder) => '${folder.key}=${folder.root}'), <String>['library-a=/x', 'library-b=/y']);
      expect(IosLinkedLibraryFolders.decode(IosLinkedLibraryFolders.encode(folders)).map((folder) => folder.key),
          <String>['library-a', 'library-b']);
    });

    test('a new slot never reuses one in use', () {
      final now = DateTime.fromMillisecondsSinceEpoch(1794000000000);
      final first = IosLinkedLibraryFolders.newKey(const <String>[], now: now);
      expect(first, startsWith(IosLinkedLibraryFolders.keyPrefix));
      final second = IosLinkedLibraryFolders.newKey(<String>[first], now: now);
      final third = IosLinkedLibraryFolders.newKey(<String>[first, second], now: now);
      expect(<String>{first, second, third}, hasLength(3));
      expect(first, isNot(ExternalFolderAccess.defaultBookmarkKey));
    });

    test('a folder belongs to a linked folder when it is that folder or lies inside it', () {
      expect(IosLinkedLibraryFolders.isInside(linked, linked), isTrue);
      expect(IosLinkedLibraryFolders.isInside('$linked/roms', linked), isTrue);
      expect(IosLinkedLibraryFolders.isInside('${linked}2', linked), isFalse);
      expect(IosLinkedLibraryFolders.isInside(appGroup, linked), isFalse);
    });

    test('registered folders follow a linked folder to its new place, and only then', () async {
      const from = '/private/var/mobile/Library/LiveFiles/com.apple.filesystems.userfsd/USB-1/Roms';
      const to = '/private/var/mobile/Library/LiveFiles/com.apple.filesystems.userfsd/USB-2/Roms';
      expect(
        await IosLinkedLibraryFolders.rebase(<String>['$from/retro', '$newOwn/Documents/roms'],
            from: from, to: to, exists: existing({'$to/retro', '$newOwn/Documents/roms'})),
        <String>['$to/retro', '$newOwn/Documents/roms'],
      );
      expect(
        await IosLinkedLibraryFolders.rebase(<String>[from], from: from, to: to, exists: existing({to})),
        <String>[to],
      );
      expect(
        await IosLinkedLibraryFolders.rebase(<String>[from], from: from, to: to, exists: existing({from, to})),
        isNull,
        reason: 'a folder that still opens is not replaced',
      );
      expect(
        await IosLinkedLibraryFolders.rebase(<String>[from], from: from, to: to, exists: existing(<String>{})),
        isNull,
        reason: 'found at neither place: kept as it is',
      );
      expect(
        await IosLinkedLibraryFolders.rebase(<String>[from, to], from: from, to: to, exists: existing({to})),
        <String>[to],
        reason: 'the duplicate left by picking the folder again collapses',
      );
      expect(await IosLinkedLibraryFolders.rebase(<String>[from], from: from, to: from, exists: existing(<String>{})), isNull);
    });
  });

  group('a native failure is a reason, not a cancelled pick', () {
    const channel = MethodChannel('neostation/external_folder_access');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    Object? Function(MethodCall call)? answer;

    setUp(() {
      ExternalFolderAccess.debugIsIosOverride = true;
      messenger.setMockMethodCallHandler(channel, (call) async => answer!(call));
    });
    tearDown(() {
      ExternalFolderAccess.debugIsIosOverride = null;
      messenger.setMockMethodCallHandler(channel, null);
    });

    test('a cancelled pick is null; a pick the system refused throws its code', () async {
      answer = (_) => null;
      expect(await ExternalFolderAccess.pickAndBookmarkFolder(key: 'k'), isNull);
      answer = (_) => throw PlatformException(code: 'NO_ROOT_VC', message: 'no window');
      await expectLater(
        ExternalFolderAccess.pickAndBookmarkFolder(key: 'k'),
        throwsA(isA<ExternalFolderAccessException>().having((error) => error.code, 'code', 'NO_ROOT_VC')),
      );
    });

    test('a folder iOS does not give back is told apart from a folder never linked', () async {
      answer = (_) => null;
      expect(await ExternalFolderAccess.resolveBookmarkedFolder(key: 'never'), isNull);
      expect(ExternalFolderAccess.resolveFailure(key: 'never'), isNull);

      answer = (_) => throw PlatformException(code: 'RESOLVE_FAILED', message: 'The file doesn’t exist.');
      expect(await ExternalFolderAccess.resolveBookmarkedFolder(key: 'lost'), isNull);
      expect(ExternalFolderAccess.resolveFailure(key: 'lost')?.code, 'RESOLVE_FAILED');

      answer = (_) => '/folder';
      expect(await ExternalFolderAccess.resolveBookmarkedFolder(key: 'lost'), '/folder');
      expect(ExternalFolderAccess.resolveFailure(key: 'lost'), isNull, reason: 'the folder opened again');
    });

    test('a picked folder that cannot be reopened throws the system\'s reason', () async {
      answer = (call) => call.method == 'pickAndBookmarkFolder'
          ? '/picked'
          : throw PlatformException(code: 'ACCESS_DENIED', message: 'startAccessingSecurityScopedResource returned false');
      await expectLater(
        ExternalFolderAccess.pickAndActivateFolder(key: 'k'),
        throwsA(isA<ExternalFolderAccessException>().having((error) => error.code, 'code', 'ACCESS_DENIED')),
      );
      answer = (call) => call.method == 'pickAndBookmarkFolder' ? '/picked' : null;
      await expectLater(
        ExternalFolderAccess.pickAndActivateFolder(key: 'k'),
        throwsA(isA<ExternalFolderAccessException>().having((error) => error.code, 'code', 'NOT_ACTIVATED')),
      );
      answer = (call) => call.method == 'pickAndBookmarkFolder' ? null : '/never-asked';
      expect(await ExternalFolderAccess.pickAndActivateFolder(key: 'k'), isNull, reason: 'cancelled');
    });

    test('a slot is moved with the reason it carried', () async {
      final calls = <String>[];
      answer = (call) {
        calls.add('${call.method} ${call.arguments}');
        return call.method == 'moveBookmark' ? true : null;
      };
      expect(await ExternalFolderAccess.moveBookmark(from: 'pending', to: 'retroarch'), isTrue);
      expect(calls.single, 'moveBookmark {from: pending, to: retroarch}');
      answer = (_) => false;
      expect(await ExternalFolderAccess.moveBookmark(from: 'empty', to: 'retroarch'), isFalse);
    });
  });

  group('every failure has its sentence, in every language', () {
    test('each language has every text, with the same placeholders', () {
      final placeholder = RegExp(r'\{[a-z]+\}');
      for (final key in LibraryLinkLocale.keys) {
        final expected = placeholder.allMatches(LibraryLinkLocale.textFor('en', key)).map((match) => match.group(0)).toSet();
        for (final language in LibraryLinkLocale.languages) {
          expect(LibraryLinkLocale.has(language, key), isTrue, reason: '$language lacks $key');
          final found = placeholder.allMatches(LibraryLinkLocale.textFor(language, key)).map((match) => match.group(0)).toSet();
          expect(found, expected, reason: '$language/$key');
        }
      }
    });

    test('the language of a locale', () {
      expect(LibraryLinkLocale.languageOf(const Locale('fr')), 'fr');
      expect(LibraryLinkLocale.languageOf(const Locale('zh', 'TW')), 'zh_Hant');
      expect(LibraryLinkLocale.languageOf(const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')), 'zh_Hant');
      expect(LibraryLinkLocale.languageOf(const Locale('zh', 'CN')), 'zh');
      expect(LibraryLinkLocale.languageOf(const Locale('sv')), 'en');
    });

    test('the sentence names the cause', () {
      String failure(Object error) => LibraryLinkLocale.failureFor('en', error);
      expect(failure(const ExternalFolderAccessException('NO_ROOT_VC')), startsWith('The folder picker could not be opened.'));
      expect(failure(const ExternalFolderAccessException('PICKER_BUSY')), startsWith('A folder picker is already open.'));
      expect(
        failure(const ExternalFolderAccessException('BOOKMARK_FAILED', message: 'Operation not permitted')),
        contains('did not let RewindBox keep access to this folder (Operation not permitted)'),
      );
      for (final code in <String>['RESOLVE_FAILED', 'ACCESS_DENIED', 'NOT_ACTIVATED']) {
        expect(failure(ExternalFolderAccessException(code)), contains('no longer gives RewindBox access to this folder ($code)'));
      }
      expect(failure(const FileSystemException('The folder does not open', '/x')), startsWith('This folder cannot be read (The folder does not open)'));
      expect(failure(StateError('ROM folder registration did not complete')),
          'The folder could not be added: Bad state: ROM folder registration did not complete');
      expect(LibraryLinkLocale.failureFor('fr', const ExternalFolderAccessException('NO_ROOT_VC')), startsWith('Le sélecteur de dossier'));
    });
  });
}
