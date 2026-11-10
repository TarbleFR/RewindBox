import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/xenia_internal_service.dart';
import 'package:path/path.dart' as path;

import 'xenia_test_images.dart';

/// XeniaInternalService.importFiles: the copy behind the Xbox 360 playlist's
/// import button (the Files picker itself is the existing file_picker path).
void main() {
  late Directory temp;
  late Directory sources;
  late Directory games;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('xenia_import_');
    sources = await Directory(path.join(temp.path, 'picked')).create();
    XeniaInternalService.documentsDirectory = () async =>
        Directory(path.join(temp.path, 'Documents'));
    XeniaInternalService.cachesDirectory = () async =>
        Directory(path.join(temp.path, 'Caches'));
    XeniaInternalService.freeBytes = (_) => null;
    await XeniaInternalService.ensureLayout();
    games = await XeniaInternalService.gamesDirectory();
  });

  tearDown(() async {
    await temp.delete(recursive: true);
  });

  Future<String> image(String name, {int titleId = 0x4D5307E6, int padding = 0}) async =>
      (await writeXboxImage(path.join(sources.path, name), titleId: titleId, padding: padding)).path;

  List<String> library() => games
      .listSync()
      .map((entity) => path.basename(entity.path))
      .toList()
    ..sort();

  test('a valid disc image is copied into XeniOS/Games, the source kept', () async {
    final source = await image('Halo 3.iso');
    final before = await File(source).readAsBytes();
    final result = await XeniaInternalService.importFiles(<String>[source]);
    expect(result.imported, 1);
    expect(library(), <String>['Halo 3.iso']);
    expect(await File(path.join(games.path, 'Halo 3.iso')).readAsBytes(), before);
    expect(await File(source).readAsBytes(), before, reason: 'the source is never modified');
  });

  test('a second import of the same game is skipped, a different one with the same name is not', () async {
    final source = await image('Game.iso');
    await XeniaInternalService.importFiles(<String>[source]);
    final again = await XeniaInternalService.importFiles(<String>[source]);
    expect(again.imported, 0);
    expect(again.duplicates, 1);
    // Same disc under another name and same size: still a duplicate.
    final renamed = await File(source).copy(path.join(sources.path, 'Copy of Game.iso'));
    final copy = await XeniaInternalService.importFiles(<String>[renamed.path]);
    expect(copy.duplicates, 1);
    // Another game picked under the same name: kept beside it.
    await Directory(path.join(sources.path, 'other')).create();
    final other = (await writeXboxImage(
      path.join(sources.path, 'other', 'Game.iso'),
      titleId: 0x41560817,
      padding: 4096,
    )).path;
    final second = await XeniaInternalService.importFiles(<String>[other]);
    expect(second.imported, 1);
    expect(library(), <String>['Game (2).iso', 'Game.iso']);
  });

  test('profiles, touch layouts, loose executables and foreign files are refused with their reason', () async {
    final profile = File(path.join(sources.path, 'me.xeniosprofile'))..writeAsStringSync('x');
    final layout = File(path.join(sources.path, 'pad.toml'))..writeAsStringSync('x');
    final xex = File(path.join(sources.path, 'default.xex'))..writeAsStringSync('XEX2');
    final foreign = File(path.join(sources.path, 'disc.iso'))..writeAsBytesSync(List<int>.filled(100000, 1));
    final cut = (await writeXboxImage(path.join(sources.path, 'cut.iso'), truncateExecutable: true)).path;
    final empty = File(path.join(sources.path, 'empty.zar'))..writeAsBytesSync(const <int>[]);
    final result = await XeniaInternalService.importFiles(<String>[
      profile.path, layout.path, xex.path, foreign.path, cut, empty.path,
    ]);
    expect(result.imported, 0);
    expect({for (final item in result.items) item.name: item.reason}, <String, String>{
      'me.xeniosprofile': 'profileNotGame',
      'pad.toml': 'touchLayoutNotGame',
      'default.xex': 'folderRequired',
      'disc.iso': 'notXboxImage',
      'cut.iso': 'incomplete',
      'empty.zar': 'unreadable',
    });
    expect(library(), isEmpty);
  });

  test('cancelling keeps no partial game and leaves the source; a new import then works', () async {
    final source = await image('Big.iso', padding: 64 * 1024 * 1024);
    final control = XeniaImportControl();
    final result = await XeniaInternalService.importFiles(
      <String>[source],
      control: control,
      onProgress: (progress) {
        if (progress.done > 0) control.cancel();
      },
    );
    expect(result.cancelled, isTrue);
    expect(result.imported, 0);
    expect(library(), isEmpty, reason: 'no .importing file and no game left behind');
    expect(File(source).existsSync(), isTrue);
    final retry = await XeniaInternalService.importFiles(<String>[source]);
    expect(retry.imported, 1);
    expect(library(), <String>['Big.iso']);
  });

  test('not enough free space refuses the copy before it starts', () async {
    final source = await image('Space.iso');
    XeniaInternalService.freeBytes = (_) => 1024;
    final result = await XeniaInternalService.importFiles(<String>[source]);
    expect(result.items.single.reason, 'notEnoughSpace');
    expect(library(), isEmpty);
  });

  test('the content kind sent to the engine follows the file', () {
    expect(XeniaInternalService.contentKindFor('/a/b.iso'), 1);
    expect(XeniaInternalService.contentKindFor('/a/b.zar'), 2);
    expect(XeniaInternalService.contentKindFor('/a/default.xex'), 3);
    expect(XeniaInternalService.contentKindFor('/a/pad.toml'), isNull);
  });
}
