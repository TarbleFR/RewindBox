import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/nextendo/nextendo_catalog.dart';
import 'package:neostation/services/nextendo/nextendo_game_versions.dart';
import 'package:neostation/services/nextendo/nextendo_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

// A Switch game's installed version (base file, selected update) against Nextendo's signed catalog, as the game's
// page shows it. test/fixtures/nextendo/game-catalog.json is the public catalog of 17 November 2026 (revision 23).
class _MemoryStore implements NextendoStore {
  String? value;
  @override
  Future<String?> read() async => value;
  @override
  Future<void> write(String value) async => this.value = value;
  @override
  Future<void> clear() async => value = null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final catalog = NextendoCatalog.parse(File('test/fixtures/nextendo/game-catalog.json').readAsStringSync())!;
  const smash = '01006a800016e000';
  late Directory root;
  late File game;

  setUp(() async {
    root = await Directory.systemTemp.createTemp('nextendo-versions-');
    game = File('${root.path}/roms/smash.nsp')..createSync(recursive: true);
  });
  tearDown(() async => root.delete(recursive: true));

  Future<Map<String, dynamic>> Function(String, {String? filePath, String? titleId}) engine({
    String version = '1.0.0',
    String? updateVersion,
    List<String>? calls,
  }) =>
      (method, {filePath, titleId}) async {
        calls?.add('$method ${filePath?.split('/').last} ${titleId ?? ''}'.trim());
        if (method == 'metadata') return {'titleId': '01006A800016E000', 'version': version};
        if (method == 'inspectUpdate') return {'kind': 'update', if (updateVersion != null) 'displayVersion': updateVersion};
        throw StateError(method);
      };

  void selectUpdate(String name) {
    File('${root.path}/addons/$smash/$name').createSync(recursive: true);
    File('${root.path}/games/$smash/updates.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(jsonEncode({'selected': 'addons/$smash/$name', 'paths': ['addons/$smash/$name']}));
  }

  Future<NextendoGameVersionInfo?> read(Future<Map<String, dynamic>> Function(String, {String? filePath, String? titleId}) content,
          {NextendoCatalog? use}) =>
      NextendoGameVersions.read(gamePath: game.path, root: root, content: content, catalog: () async => use ?? catalog);

  test('the selected update at the required version is compatible', () async {
    selectUpdate('smash-13.0.5.nsp');
    final calls = <String>[];
    final info = (await read(engine(updateVersion: '13.0.5', calls: calls)))!;
    expect(calls, ['metadata smash.nsp', 'inspectUpdate smash-13.0.5.nsp $smash']);
    expect(info.titleId, smash);
    expect(info.baseVersion, '1.0.0');
    expect(info.installedVersion, '13.0.5');
    expect(info.requirement!.accepted, ['13.0.5']);
    expect(info.status, NextendoVersionStatus.matches);
  });

  test('another update, or none, asks for the required update', () async {
    selectUpdate('smash-13.0.1.nsp');
    expect((await read(engine(updateVersion: '13.0.1')))!.status, NextendoVersionStatus.mismatch);
    File('${root.path}/games/$smash/updates.json').deleteSync();
    final base = (await read(engine()))!;
    expect(base.updateInstalled, isFalse);
    expect(base.installedVersion, '1.0.0');
    expect(base.status, NextendoVersionStatus.mismatch);
  });

  test("an engine that does not report an update's version leaves it unknown, not wrong", () async {
    selectUpdate('smash-update.nsp');
    final info = (await read(engine()))!;
    expect(info.updateInstalled, isTrue);
    expect(info.installedVersion, isNull);
    expect(info.status, NextendoVersionStatus.installedUnknown);
  });

  test('a selected update outside the data root or missing is ignored', () async {
    File('${root.path}/games/$smash/updates.json')
      ..createSync(recursive: true)
      ..writeAsStringSync(jsonEncode({'selected': '../../etc/hosts'}));
    final calls = <String>[];
    expect((await read(engine(calls: calls)))!.updateInstalled, isFalse);
    expect(calls, ['metadata smash.nsp']);
  });

  test('status: unlisted, disabled and no catalog', () {
    expect(NextendoGameVersionInfo.statusOf(catalog: catalog, requirement: null, installed: '1.0.0'), NextendoVersionStatus.notListed);
    const off = NextendoGameRequirement(name: 'x', titleIds: ['0123456789abcdef'], enabled: false, protocol: '', accepted: ['1.0.0'], recommended: '1.0.0');
    expect(NextendoGameVersionInfo.statusOf(catalog: catalog, requirement: off, installed: '1.0.0'), NextendoVersionStatus.disabled);
    expect(NextendoGameVersionInfo.statusOf(catalog: null, requirement: null, installed: '1.0.0'), NextendoVersionStatus.catalogUnavailable);
  });

  test('a signed-out player without a kept catalog sees no card and nothing is asked', () async {
    SharedPreferences.setMockInitialValues({});
    final calls = <String>[];
    final info = await NextendoGameVersions.forLibrary(
      gamePath: game.path,
      root: root,
      content: engine(calls: calls),
      service: NextendoService(store: _MemoryStore()),
      preferences: await SharedPreferences.getInstance(),
    );
    expect(info, isNull);
    expect(calls, isEmpty);
  });
}
