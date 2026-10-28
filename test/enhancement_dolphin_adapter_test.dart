import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/enhancements/adapters/dolphin_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/enhancement_models.dart';
import 'package:neostation/services/enhancements/enhancement_service.dart';
import 'package:neostation/services/enhancements/enhancement_store.dart';
import 'package:path/path.dart' as path;

import 'enhancement_test_support.dart';

/// Viewtiful Joe 2 (USA): its Sys/GameSettings lists a Gecko 16:9 code.
const _gameId = 'G2VE08';

void main() {
  late Directory temp;
  late Directory user;
  late EnhancementService service;

  setUp(() {
    temp = Directory.systemTemp.createTempSync('enh-dolphin-');
    user = Directory(path.join(temp.path, 'User'))..createSync();
    service = EnhancementService(
      catalog: repositoryCatalog(Directory(path.join(temp.path, 'cache'))),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [
        DolphinEnhancementAdapter(
          userDirectory: () async => user,
          nativeIdentity: (gamePath, system) async => {'system': system, 'gameId': _gameId, 'region': 'USA'},
        ),
      ],
      texturesSupported: (_) => true,
    );
  });
  tearDown(() => temp.deleteSync(recursive: true));

  File local() => File(path.join(user.path, 'GameSettings', '$_gameId.ini'));
  File config() => File(path.join(user.path, 'Config', 'Dolphin.ini'));

  test('the disc revision is read from plain and RVZ headers', () async {
    final iso = File(path.join(temp.path, 'game.iso'))
      ..writeAsBytesSync(Uint8List.fromList([..._gameId.codeUnits, 0, 2, ...List.filled(32, 0)]));
    expect(await DolphinEnhancementAdapter.discRevision(iso.path, _gameId), 2);
    final rvz = File(path.join(temp.path, 'game.rvz'))
      ..writeAsBytesSync(Uint8List.fromList([...List.filled(0x58, 0), ..._gameId.codeUnits, 0, 1]));
    expect(await DolphinEnhancementAdapter.discRevision(rvz.path, _gameId), 1);
    expect(await DolphinEnhancementAdapter.discRevision(iso.path, 'GZLE01'), isNull, reason: 'header of another game');
    expect(await DolphinEnhancementAdapter.discRevision(path.join(temp.path, 'game.gcz'), _gameId), isNull);
  });

  test('a Gecko widescreen code is enabled by name with the cheat switch', () async {
    final rom = File(path.join(temp.path, 'vj2.rvz'))..writeAsBytesSync([0]);
    final game = testGame(name: 'Viewtiful Joe 2', romPath: rom.path);
    var view = await service.open(game, 'gc', download: true);
    final widescreen = view.items.firstWhere((item) => item.name == '16:9 Widescreen');
    expect(widescreen.category, EnhancementCategory.ultrawide);
    expect(widescreen.status, EnhancementStatus.installed, reason: 'the body ships with the engine');
    view = await service.setActive(game, 'gc', view, widescreen, true);
    expect(local().readAsStringSync(), '[Gecko_Enabled]\n\$16:9 Widescreen\n');
    expect(config().readAsStringSync(), contains('EnableCheats = True'));
    expect(view.items.firstWhere((i) => i.id == widescreen.id).status, EnhancementStatus.active);

    await service.restore(view.identity.storeKey);
    expect(local().existsSync(), isFalse);
  });

  test('a code disabled in-game is lifted, then put back on restore', () async {
    final revision = File(path.join(user.path, 'GameSettings', '${_gameId}r0.ini'))
      ..createSync(recursive: true)
      ..writeAsStringSync('[Gecko_Disabled]\n\$16:9 Widescreen\n[Gecko_Enabled]\n\$Mine\n');
    final rom = File(path.join(temp.path, 'vj2.iso'))..writeAsBytesSync([0]);
    final game = testGame(name: 'Viewtiful Joe 2', romPath: rom.path);
    var view = await service.open(game, 'gc', download: true);
    final widescreen = view.items.firstWhere((item) => item.name == '16:9 Widescreen');
    expect(widescreen.status, EnhancementStatus.installed);
    view = await service.setActive(game, 'gc', view, widescreen, true);
    expect(revision.readAsStringSync(), isNot(contains('\$16:9 Widescreen')));
    expect(revision.readAsStringSync(), contains('\$Mine'));
    await service.restore(view.identity.storeKey);
    expect(revision.readAsStringSync(), contains('[Gecko_Disabled]\n\$16:9 Widescreen'));
  });
}
