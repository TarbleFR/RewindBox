import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/melonx_mods_service.dart';

// A Switch game's mods as the embedded engine's ModLoader reads them: <root>/mods/contents/<title id>/<mod>/{romfs,exefs},
// turned off by moving the folder to <root>/mods/rewindbox-disabled/<title id>/<mod>.
const _smash = '01006a800016e000';

File _zip(Directory dir, String name, Map<String, List<int>> files) {
  final archive = Archive();
  files.forEach((path, content) => archive.addFile(ArchiveFile(path, content.length, content)));
  return File('${dir.path}/$name')..writeAsBytesSync(ZipEncoder().encode(archive));
}

void main() {
  late Directory root;
  late Directory downloads;

  setUp(() async {
    root = await Directory.systemTemp.createTemp('melonx-mods-');
    downloads = await Directory.systemTemp.createTemp('melonx-mod-zips-');
  });
  tearDown(() async {
    await root.delete(recursive: true);
    await downloads.delete(recursive: true);
  });

  String contents(String relative) => '${root.path}/mods/contents/$_smash/$relative';

  test('romfs at the top is named after the archive; files outside romfs/exefs are skipped', () async {
    final zip = _zip(downloads, 'Better Menus.zip', {
      'romfs/ui/menu.arc': [1, 2],
      'exefs/main.ips': [3],
      'README.txt': [9],
    });
    expect(await MelonxModsService.importArchive(root, _smash.toUpperCase(), zip.path), ['Better Menus']);
    expect(File(contents('Better Menus/romfs/ui/menu.arc')).readAsBytesSync(), [1, 2]);
    expect(File(contents('Better Menus/exefs/main.ips')).readAsBytesSync(), [3]);
    expect(File(contents('Better Menus/README.txt')).existsSync(), isFalse);
    final mods = await MelonxModsService.list(root, _smash);
    expect(mods.single.name, 'Better Menus');
    expect(mods.single.enabled && mods.single.romfs && mods.single.exefs && !mods.single.cheats, isTrue);
    expect(Directory('${root.path}/mods/contents/$_smash').listSync().map((e) => e.path.split('/').last), ['Better Menus']);
  });

  test('a folder per mod, and the Atmosphère layout for this game or its update, import as named mods', () async {
    final zip = _zip(downloads, 'pack.zip', {
      'Stage Pack/romfs/stage/a.bin': [1],
      'atmosphere/contents/01006A800016E800/Music/romfs/sound/b.bin': [2],
    });
    expect(await MelonxModsService.importArchive(root, _smash, zip.path), ['Music', 'Stage Pack']);
    expect(File(contents('Stage Pack/romfs/stage/a.bin')).existsSync(), isTrue);
    expect(File(contents('Music/romfs/sound/b.bin')).existsSync(), isTrue);
  });

  test("another game's mod, an unsafe path, a duplicate name or an archive without a mod refuse the whole import", () async {
    final wrong = _zip(downloads, 'other.zip', {'atmosphere/contents/0100152000022000/romfs/x.bin': [1]});
    await expectLater(MelonxModsService.importArchive(root, _smash, wrong.path),
        throwsA(isA<MelonxModException>().having((e) => e.code, 'code', 'wrongGame')));
    final unsafe = _zip(downloads, 'unsafe.zip', {'ok/romfs/a.bin': [1], '../escape/romfs/b.bin': [2]});
    await expectLater(MelonxModsService.importArchive(root, _smash, unsafe.path),
        throwsA(isA<MelonxModException>().having((e) => e.code, 'code', 'unsafePath')));
    final none = _zip(downloads, 'readme.zip', {'docs/readme.txt': [1], 'only/cheats/0123.txt': [2]});
    await expectLater(MelonxModsService.importArchive(root, _smash, none.path),
        throwsA(isA<MelonxModException>().having((e) => e.code, 'code', 'noMod')));
    final first = _zip(downloads, 'Skin.zip', {'romfs/a.bin': [1]});
    await MelonxModsService.importArchive(root, _smash, first.path);
    await expectLater(MelonxModsService.importArchive(root, _smash, first.path),
        throwsA(isA<MelonxModException>().having((e) => e.code, 'code', 'exists')));
    // Nothing half-written: only the first good import is there, no staging folder.
    expect(Directory('${root.path}/mods/contents/$_smash').listSync().map((e) => e.path.split('/').last), ['Skin']);
    expect(Directory('${root.path}/escape').existsSync(), isFalse);
    expect(Directory('${downloads.path}/../escape').existsSync(), isFalse);
  });

  test('turning a mod off moves it where the engine never looks; on brings it back and clears a mods.json off entry', () async {
    await MelonxModsService.importArchive(root, _smash, _zip(downloads, 'Skin.zip', {'romfs/a.bin': [1]}).path);
    await MelonxModsService.setEnabled(root, _smash, 'Skin', false);
    expect(Directory(contents('Skin')).existsSync(), isFalse);
    expect(File('${root.path}/mods/rewindbox-disabled/$_smash/Skin/romfs/a.bin').existsSync(), isTrue);
    expect((await MelonxModsService.list(root, _smash)).single.enabled, isFalse);
    File('${root.path}/games/$_smash/mods.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(jsonEncode({
        'mods': [
          {'name': 'Skin', 'path': contents('Skin'), 'enabled': false},
          {'name': 'Other', 'path': contents('Other'), 'enabled': false},
        ],
      }));
    await MelonxModsService.setEnabled(root, _smash, 'Skin', true);
    expect(File(contents('Skin/romfs/a.bin')).existsSync(), isTrue);
    final json = jsonDecode(File('${root.path}/games/$_smash/mods.json').readAsStringSync()) as Map;
    expect((json['mods'] as List).map((m) => (m as Map)['name']), ['Other']);
    expect((await MelonxModsService.list(root, _smash)).single.enabled, isTrue);
  });

  test("a mod the engine's mods.json turns off shows as off; cheats-only folders are left to the Cheats screen", () async {
    await MelonxModsService.importArchive(root, _smash, _zip(downloads, 'Skin.zip', {'romfs/a.bin': [1]}).path);
    Directory(contents('RewindBox/cheats')).createSync(recursive: true);
    File('${root.path}/games/$_smash/mods.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(jsonEncode({'mods': [{'name': 'Skin', 'path': contents('Skin'), 'enabled': false}]}));
    final mods = await MelonxModsService.list(root, _smash);
    expect(mods.map((m) => m.name), ['Skin']);
    expect(mods.single.enabled, isFalse);
  });

  test("RewindBox's own folder (exefs patches and cheats) is never a mod: not listed, turned off, deleted or imported over", () async {
    await MelonxModsService.importArchive(root, _smash, _zip(downloads, 'Skin.zip', {'romfs/a.bin': [1]}).path);
    // What the Cheats & Enhancements page writes while an exefs mod and a cheat are on.
    final patch = File(contents('RewindBox/exefs/fl4sh-120fps-v1-3-2-0.pchtxt'))
      ..createSync(recursive: true)
      ..writeAsStringSync('@nsobid-0123456789ABCDEF0123456789ABCDEF\n@enabled\n00001000 1F2003D5\n@stop\n');
    final cheat = File(contents('RewindBox/cheats/0123456789ABCDEF.txt'))
      ..createSync(recursive: true)
      ..writeAsStringSync('[Infinite Health]\n04000000 00000000 00000001\n');
    expect((await MelonxModsService.list(root, _smash)).map((m) => m.name), ['Skin']);

    await expectLater(MelonxModsService.setEnabled(root, _smash, 'RewindBox', false), throwsA(isA<MelonxModException>()));
    await MelonxModsService.delete(root, _smash, 'RewindBox');
    expect(patch.existsSync() && cheat.existsSync(), isTrue, reason: 'the files the page recorded stay where it wrote them');
    expect(Directory('${root.path}/mods/rewindbox-disabled').existsSync(), isFalse);

    // A copy an older version let the player turn off is not offered either (turning it back on would apply codes the
    // page may no longer track).
    File('${root.path}/mods/rewindbox-disabled/$_smash/RewindBox/exefs/old-0.pchtxt')
      ..createSync(recursive: true)
      ..writeAsStringSync('@nsobid-0123456789ABCDEF0123456789ABCDEF\n@stop\n');
    expect((await MelonxModsService.list(root, _smash)).map((m) => m.name), ['Skin']);
    await expectLater(MelonxModsService.setEnabled(root, _smash, 'RewindBox', true), throwsA(isA<MelonxModException>()));
    expect(patch.existsSync(), isTrue);

    // No archive takes the name, in any case: it is reserved (its own message), not an existing mod.
    final named = _zip(downloads, 'named.zip', {'rewindbox/romfs/a.bin': [1]});
    await expectLater(MelonxModsService.importArchive(root, _smash, named.path),
        throwsA(isA<MelonxModException>().having((e) => (e.code, e.detail), 'code', ('reservedName', 'rewindbox'))));
    expect(Directory('${root.path}/mods/contents/$_smash').listSync().map((e) => e.path.split('/').last).toSet(),
        {'Skin', 'RewindBox'});
    expect(MelonxModsService.ownFolder('RewindBox') && MelonxModsService.ownFolder('rewindbox'), isTrue);
    expect(MelonxModsService.ownFolder('Skin'), isFalse);
  });

  test("a copy of RewindBox's folder an older version turned off is moved back only where asked and free, else "
      'deleted', () async {
    final copy = Directory('${root.path}/mods/rewindbox-disabled/$_smash/RewindBox');
    final live = Directory(contents('RewindBox'));
    expect(await MelonxModsService.reclaimOwnFolder(root, _smash, restore: true), isNull, reason: 'no copy');

    File('${copy.path}/exefs/a-0.pchtxt').createSync(recursive: true);
    expect(await MelonxModsService.reclaimOwnFolder(root, _smash.toUpperCase(), restore: true), isTrue);
    expect(File('${live.path}/exefs/a-0.pchtxt').existsSync(), isTrue);
    expect(Directory('${root.path}/mods/rewindbox-disabled').existsSync(), isFalse, reason: 'empty folders go too');

    // Its place is taken (the page wrote it again), or nothing records it: deleted.
    File('${copy.path}/exefs/b-0.pchtxt').createSync(recursive: true);
    expect(await MelonxModsService.reclaimOwnFolder(root, _smash, restore: true), isFalse);
    expect(File('${live.path}/exefs/b-0.pchtxt').existsSync() || copy.existsSync(), isFalse);
    live.deleteSync(recursive: true);
    File('${copy.path}/exefs/c-0.pchtxt').createSync(recursive: true);
    await MelonxModsService.importArchive(root, _smash, _zip(downloads, 'Skin.zip', {'romfs/a.bin': [1]}).path);
    await MelonxModsService.setEnabled(root, _smash, 'Skin', false);
    expect(await MelonxModsService.reclaimOwnFolder(root, _smash, restore: false), isFalse);
    expect(live.existsSync() || copy.existsSync(), isFalse);
    expect((await MelonxModsService.list(root, _smash)).single.name, 'Skin', reason: "a player's mod turned off stays");
  });

  test('delete removes the mod wherever it is; bad names are refused', () async {
    await MelonxModsService.importArchive(root, _smash, _zip(downloads, 'Skin.zip', {'romfs/a.bin': [1]}).path);
    await MelonxModsService.setEnabled(root, _smash, 'Skin', false);
    await MelonxModsService.delete(root, _smash, 'Skin');
    expect(await MelonxModsService.list(root, _smash), isEmpty);
    for (final name in ['..', '.', 'a/b', '', '.hidden']) {
      await expectLater(MelonxModsService.delete(root, _smash, name), throwsA(isA<MelonxModException>()), reason: name);
    }
    expect(() => MelonxModsService.contents(root, 'not-a-title'), throwsA(isA<MelonxModException>()));
  });
}
