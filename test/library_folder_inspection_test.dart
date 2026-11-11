import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_link_locale.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/screens/libretro/libretro_library_actions.dart';
import 'package:neostation/services/neostation_rom_library.dart';
import 'package:neostation/services/library_folder_inspection.dart';
import 'package:neostation/services/library_folder_linker.dart';
import 'package:neostation/widgets/library_folder_report_dialog.dart';
import 'package:path/path.dart' as path;

/// What RewindBox reads in a library folder before it is added: which folder
/// feeds which playlist, and what is left out with its reason (11 November
/// 2026: a tester's linked folder showed no game and no reason).
void main() {
  const snes = InspectionSystem(
    id: 'snes',
    name: 'Super Nintendo',
    folderNames: <String>['snes', 'sfc'],
    extensions: <String>{'sfc', 'smc', 'zip'},
  );
  const gba = InspectionSystem(
    id: 'gba',
    name: 'Game Boy Advance',
    folderNames: <String>['gba'],
    extensions: <String>{'gba', 'zip'},
  );
  const flat = InspectionSystem(
    id: 'nes',
    name: 'NES',
    folderNames: <String>['nes'],
    extensions: <String>{'nes'},
    recursive: false,
  );
  const gamecube = InspectionSystem(
    id: 'gc',
    name: 'GameCube',
    folderNames: <String>['gc', 'gamecube'],
    extensions: <String>{'iso', 'rvz'},
    importOnly: true,
  );
  const systems = <InspectionSystem>[snes, gba, flat, gamecube];

  late Directory root;

  Future<void> file(String relative) async {
    final target = File(path.join(root.path, relative));
    await target.parent.create(recursive: true);
    await target.writeAsString('x');
  }

  setUp(() async => root = await Directory.systemTemp.createTemp('library-inspection-'));
  tearDown(() async => root.delete(recursive: true));

  test('each console folder feeds its playlist; aliases and letter case are accepted', () async {
    await file('SNES/Zelda.sfc');
    await file('SNES/Mario.smc');
    await file('SNES/hacks/Kaizo.sfc');
    await file('SNES/readme.txt');
    await file('gba/Metroid.gba');
    final inspection = await LibraryFolderInspector.inspect(root.path, systems);
    expect(inspection.recognised, isTrue);
    final byId = {for (final console in inspection.consoles) console.system.id: console};
    expect(byId['snes']!.folderName, 'SNES');
    expect(byId['snes']!.games, 3, reason: 'sub-folders are read for a recursive console');
    expect(byId['snes']!.otherFiles, 1);
    expect(byId['snes']!.examples, hasLength(3));
    expect(byId['snes']!.examples, contains('Zelda'));
    expect(byId['gba']!.games, 1);
    expect(inspection.games, 4);
    expect(inspection.playlists, 2);
    expect(inspection.unknownFolders, isEmpty);
    expect(inspection.looseGames, 0);
  });

  test('a console that does not read its sub-folders counts only its own files', () async {
    await file('nes/Contra.nes');
    await file('nes/deeper/Hidden.nes');
    final inspection = await LibraryFolderInspector.inspect(root.path, systems);
    expect(inspection.consoles.single.games, 1);
  });

  test('a console folder under another name is reported, with the console its files point to', () async {
    await file('Super Nintendo/Zelda.sfc');
    await file('Super Nintendo/Mario.smc');
    await file('My archives/a.zip');
    await file('My archives/b.zip');
    await file('Documents/notes.txt');
    final inspection = await LibraryFolderInspector.inspect(root.path, systems);
    expect(inspection.recognised, isFalse);
    final unknown = {for (final folder in inspection.unknownFolders) folder.folderName: folder};
    expect(unknown.keys, unorderedEquals(<String>['Super Nintendo', 'My archives']),
        reason: 'a folder without any game file is not a console folder under another name');
    expect(unknown['Super Nintendo']!.files, 2);
    expect(unknown['Super Nintendo']!.suggestion?.id, 'snes', reason: '.sfc and .smc belong to one console only');
    expect(unknown['My archives']!.suggestion, isNull, reason: '.zip is read by several consoles: no guess');
  });

  test('games outside a console folder, RetroArch\'s own folders and hidden entries', () async {
    await file('Loose.gba');
    await file('notes.txt');
    await file('saves/Zelda.srm');
    await file('system/bios.zip');
    await file('.Trash/Old.gba');
    await file('.hidden.gba');
    await file('gba/Metroid.gba');
    final inspection = await LibraryFolderInspector.inspect(root.path, systems);
    expect(inspection.looseGames, 1, reason: 'only files a console reads count; hidden files do not');
    expect(inspection.unknownFolders, isEmpty, reason: 'saves and system are RetroArch folders, .Trash is hidden');
    expect(inspection.games, 1);
  });

  test('a console that keeps its games in RewindBox is found but not counted as read', () async {
    await file('gc/Melee.iso');
    await file('gba/Metroid.gba');
    final inspection = await LibraryFolderInspector.inspect(root.path, systems);
    expect(inspection.importOnly.single.system.id, 'gc');
    expect(inspection.importOnly.single.games, 1);
    expect(inspection.scanned.single.system.id, 'gba');
    expect(inspection.games, 1);
    expect(inspection.playlists, 1);
  });

  test('a very large folder stops at the limit and says so', () async {
    for (var index = 0; index < 6; index++) {
      await file('gba/Game $index.gba');
    }
    final inspection = await LibraryFolderInspector.inspect(root.path, systems, entryLimit: 4);
    expect(inspection.truncated, isTrue);
    expect(inspection.consoles.single.games, lessThanOrEqualTo(4));
  });

  group('report', () {
    List<String> texts(LibraryFolderInspection inspection) => [
      for (final line in LibraryFolderReport.lines(
        inspection,
        language: 'en',
        location: 'Roms',
        exampleFolders: const <String>['snes', 'gba'],
      ))
        '${line.kind.name}: ${line.text}',
    ];

    test('says which folder goes to which playlist, then what is left out and why', () async {
      await file('snes/Zelda.sfc');
      await file('gba/readme.txt');
      await file('gc/Melee.iso');
      await file('Super Nintendo/Mario.smc');
      await file('Loose.gba');
      final lines = texts(await LibraryFolderInspector.inspect(root.path, systems));
      expect(lines, contains('folder: Folder: Roms'));
      expect(lines, contains('playlist: Super Nintendo ← “snes”: 1 game(s)'));
      expect(lines, contains('detail: for example: Zelda'));
      expect(lines, contains('playlist: Game Boy Advance ← “gba”: no game yet'));
      expect(lines.any((line) => line.startsWith('warning: GameCube ← “gc”: 1 game(s) found, but this console keeps')), isTrue);
      expect(
        lines,
        contains(
          'warning: “Super Nintendo”: 1 file(s). They look like Super Nintendo games: rename the folder to “snes”.',
        ),
      );
      expect(lines.any((line) => line.startsWith('warning: 1 game file(s) lie directly in the folder')), isTrue);
      expect(lines.any((line) => line.startsWith('problem:')), isFalse);
    });

    test('a folder without any console folder says what a console folder is, with real names', () async {
      await file('My games/a.zip');
      final lines = texts(await LibraryFolderInspector.inspect(root.path, systems));
      expect(lines.any((line) => line.startsWith('problem: No console folder was recognised here.') && line.contains('snes, gba')), isTrue);
      expect(lines, contains('warning: “My games”: 1 file(s). No console uses this folder name.'));
    });

    test('the folder of one console, picked instead of the one that contains it, says which to choose', () async {
      // The user opened "gba" itself: its games lie directly in the picked folder.
      final picked = Directory(path.join(root.path, 'GBA'));
      await picked.create();
      await File(path.join(picked.path, 'Metroid.gba')).writeAsString('x');
      await File(path.join(picked.path, 'Zelda.gba')).writeAsString('x');
      await File(path.join(picked.path, 'notes.txt')).writeAsString('x');
      final inspection = await LibraryFolderInspector.inspect(picked.path, systems);
      expect(inspection.recognised, isFalse);
      expect(inspection.pickedConsole?.system.id, 'gba');
      expect(inspection.pickedConsole?.games, 2);
      expect(inspection.pickedConsole?.folderName, 'GBA');
      final lines = texts(inspection);
      expect(lines, hasLength(2));
      expect(lines.first, 'folder: Folder: Roms');
      expect(
        lines.last,
        'problem: “GBA” is the folder of one console (Game Boy Advance: 2 game(s) inside). '
        'Choose the folder that contains “GBA” instead: a library folder holds one folder per console.',
      );
    });

    test('a library folder that happens to bear a console name is read as a library', () async {
      // "snes" containing console folders is a library: the name alone decides nothing.
      final library = Directory(path.join(root.path, 'snes'));
      await File(path.join(library.path, 'gba', 'Metroid.gba')).create(recursive: true);
      final inspection = await LibraryFolderInspector.inspect(library.path, systems);
      expect(inspection.recognised, isTrue);
      expect(inspection.pickedConsole, isNull);
    });

    test('the picked-console sentence exists in the twelve languages', () {
      const languages = ['en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'id', 'ja', 'ko', 'zh', 'zh_Hant'];
      final english = LibraryLinkLocale.textFor('en', 'reportPickedConsole');
      for (final language in languages) {
        final text = LibraryLinkLocale.textFor(language, 'reportPickedConsole');
        for (final placeholder in ['{folder}', '{console}', '{count}']) {
          expect(text, contains(placeholder), reason: '$language $placeholder');
        }
        if (language != 'en') expect(text, isNot(english), reason: language);
      }
    });

    test('a picked console folder counts the games of its sub-folders', () async {
      await file('psx/A/a.chd');
      await file('psx/B/b.chd');
      await file('psx/C/c.chd');
      const psx = InspectionSystem(id: 'psx', name: 'PlayStation', folderNames: <String>['psx'], extensions: <String>{'chd'});
      final inspection = await LibraryFolderInspector.inspect(path.join(root.path, 'psx'), <InspectionSystem>[psx]);
      expect(inspection.pickedConsole?.games, 3);
    });

    test('a library folder named after a console alias, with other console folders, is a library', () async {
      await file('Nintendo/Gameboy Advance/Metroid.gba');
      const nes = InspectionSystem(id: 'nes', name: 'NES', folderNames: <String>['nes', 'nintendo'], extensions: <String>{'nes'});
      final inspection =
          await LibraryFolderInspector.inspect(path.join(root.path, 'Nintendo'), <InspectionSystem>[nes, gba]);
      expect(inspection.pickedConsole, isNull);
      expect(inspection.unknownFolders.single.folderName, 'Gameboy Advance');
      expect(texts(inspection).join('\n'), isNot(contains('folder of one console')));
    });

    test('a picked import-only console says it keeps its games in RewindBox', () async {
      await file('gc/Melee.iso');
      final inspection = await LibraryFolderInspector.inspect(path.join(root.path, 'gc'), systems);
      final lines = texts(inspection);
      expect(lines, hasLength(2));
      expect(lines.last, contains('keeps its games inside RewindBox'));
      expect(lines.last, isNot(contains('Choose the folder')));
    });

    test('a picked console says when the listing was cut', () async {
      await file('gba/a.gba');
      await file('gba/b.gba');
      await file('gba/c.gba');
      final inspection = await LibraryFolderInspector.inspect(path.join(root.path, 'gba'), systems, entryLimit: 2);
      expect(inspection.truncated, isTrue);
      expect(texts(inspection).last, 'detail: ${LibraryLinkLocale.textFor('en', 'reportTruncated')}');
    });

    test('a long list of unrecognised folders is cut, with the count of the rest', () async {
      for (var index = 0; index < LibraryFolderReport.unknownLimit + 3; index++) {
        await file('Folder ${index.toString().padLeft(2, '0')}/a.zip');
      }
      final lines = texts(await LibraryFolderInspector.inspect(root.path, systems));
      expect(lines.where((line) => line.contains('No console uses this folder name.')), hasLength(LibraryFolderReport.unknownLimit));
      expect(lines, contains('detail: + 3'));
    });
  });

  group('linker', () {
    SystemModel system(String id, String folder, {List<String> folders = const <String>[], bool recursive = true}) =>
        SystemModel(id: id, folderName: folder, realName: 'Console $id', iconImage: '', color: '', folders: folders, recursiveScan: recursive);

    test('the consoles of the inspection come from the systems and their file types', () async {
      final result = await LibraryFolderLinker.inspectionSystems(
        <SystemModel>[
          system('1', 'snes', folders: const <String>['sfc']),
          system('2', 'gc'),
          system('3', 'ps2'),
          system('4', 'all'),
          system('5', 'empty'),
        ],
        ios: true,
        extensionsOf: (id) async => id == '5' ? <String>{} : <String>{'ISO', 'sfc'},
      );
      expect(result.map((entry) => entry.primaryFolder), <String>['snes', 'gc', 'ps2'],
          reason: 'virtual playlists and consoles without a file type are left out');
      expect(result.first.folderNames, <String>['snes', 'sfc']);
      expect(result.first.extensions, <String>{'iso', 'sfc'});
      expect(result.where((entry) => entry.importOnly).map((entry) => entry.primaryFolder), <String>['gc', 'ps2']);
      final desktop = await LibraryFolderLinker.inspectionSystems(
        <SystemModel>[system('2', 'gc')],
        ios: false,
        extensionsOf: (_) async => <String>{'iso'},
      );
      expect(desktop.single.importOnly, isFalse, reason: 'elsewhere the library folder is read for every console');
    });

    test('example folder names are real ones, the best known first', () {
      expect(LibraryFolderLinker.exampleFolders(const <InspectionSystem>[gamecube, gba, snes]), <String>['snes', 'gba', 'gc']);
    });

    test('a folder is named as the Files app shows it', () {
      const appGroup = '/private/var/mobile/Containers/Shared/AppGroup/D64BBD85-0CBC-452D-9492-336D580EFECC';
      expect(LibraryFolderLinker.describe('$appGroup/File Provider Storage/Roms'), 'Roms');
      expect(LibraryFolderLinker.describe('$appGroup/File Provider Storage/Games/Retro'), 'Games › Retro');
      expect(
        LibraryFolderLinker.describe('/var/mobile/Containers/Data/Application/6AA78A94-8BA7-4733-BFC3-66B22495B12A/Documents/RetroArch/roms'),
        'RetroArch › roms',
      );
      expect(
        LibraryFolderLinker.describe('/private/var/mobile/Library/Mobile Documents/com~apple~CloudDocs/Roms'),
        'iCloud Drive › Roms',
      );
      expect(LibraryFolderLinker.describe('/Volumes/Card/roms'), 'Card › roms');
    });

    test('a folder that does not open is refused before it is registered', () async {
      await LibraryFolderLinker.ensureReadable(root.path);
      await expectLater(
        LibraryFolderLinker.ensureReadable(path.join(root.path, 'missing')),
        throwsA(isA<FileSystemException>()),
      );
    });
  });

  group('moving a library into RewindBox', () {
    test('a move of nothing replaces nothing: the folders registered in the picked folder stay', () {
      expect(libraryMoveReplacesSource(const RomLibraryMove()), isFalse,
          reason: 'no console folder was recognised: an empty move used to count as complete');
      expect(libraryMoveReplacesSource(const RomLibraryMove(ownLibrary: true)), isFalse,
          reason: 'RewindBox\'s own folder was picked');
      expect(libraryMoveReplacesSource(const RomLibraryMove(moved: 3)), isTrue);
      expect(libraryMoveReplacesSource(const RomLibraryMove(moved: 1, alreadyPresent: 2, notRemoved: 1)), isTrue);
      expect(libraryMoveReplacesSource(const RomLibraryMove(moved: 3, failed: 1)), isFalse,
          reason: 'a game is still only in the source');
    });

    test('a plan is movable when it holds a game the move takes', () async {
      await file('gc/Melee.iso');
      final onlyKept = LibraryMovePlan(
        location: 'Roms',
        inspection: await LibraryFolderInspector.inspect(root.path, systems),
        exampleFolders: const <String>['snes'],
      );
      expect(onlyKept.movable, isFalse, reason: 'GameCube keeps its games in RewindBox: its folder is not moved');
      await file('snes/Zelda.sfc');
      final withGames = LibraryMovePlan(
        location: 'Roms',
        inspection: await LibraryFolderInspector.inspect(root.path, systems),
        exampleFolders: const <String>['snes'],
      );
      expect(withGames.movable, isTrue);
    });

    test('the folders of consoles that keep their games in RewindBox are left in the source', () async {
      await file('source/snes/Zelda.sfc');
      await file('source/gc/Melee.iso');
      final roms = Directory(path.join(root.path, 'roms'));
      await roms.create();
      final moved = <String>{
        for (final console in systems)
          if (!console.importOnly) ...console.folderNames,
      };
      final move = await NeoStationRomLibrary.moveLibrary(
        sourceRoot: path.join(root.path, 'source'),
        romsRoot: roms.path,
        consoleFolderNames: moved,
      );
      expect(move.moved, 1);
      expect(File(path.join(roms.path, 'snes', 'Zelda.sfc')).existsSync(), isTrue);
      expect(File(path.join(root.path, 'source', 'gc', 'Melee.iso')).existsSync(), isTrue,
          reason: 'moved into roms it would show in no playlist');
      expect(Directory(path.join(roms.path, 'gc')).existsSync(), isFalse);
    });
  });
}
