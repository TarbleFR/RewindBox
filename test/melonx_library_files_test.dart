import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
// Existing transitive path_provider platform boundary; no new app dependency.
// ignore: depend_on_referenced_packages
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/services/melonx_embedded_library_service.dart';
import 'package:neostation/services/melonx_internal_service.dart';
import 'package:neostation/services/melonx_library_scanner.dart';
import 'database_test_helper.dart';

class _Paths extends PathProviderPlatform {
  _Paths(this.root);
  final String root;
  @override
  Future<String?> getApplicationDocumentsPath() async => root;
}

Future<File> write(String name, String value) async {
  final f = File(name);
  await f.parent.create(recursive: true);
  return f.writeAsString(value);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late Directory temporary, root;
  late PathProviderPlatform previous;
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    temporary = await Directory.systemTemp.createTemp('melonx-library-files-');
    previous = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Paths(temporary.path);
    root = await MelonxInternalService.rootDirectory();
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
      call,
    ) async {
      if (call.method == 'beginLibraryMutation') return true;
      if (call.method == 'endLibraryMutation') return null;
      return {'success': true};
    });
  });
  tearDown(() async {
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, null);
    PathProviderPlatform.instance = previous;
    await temporary.delete(recursive: true);
  });
  test(
    'both key files are validated before replacing their canonical destinations',
    () async {
      final prod = await write(
        p.join(temporary.path, 'source/PROD.KEYS'),
        '# personal\nheader_key = ${'a' * 64}\n',
      );
      final title = await write(
        p.join(temporary.path, 'source/title.keys'),
        '${'b' * 32} = ${'c' * 32}',
      );
      await write(p.join(root.path, 'system/prod.keys'), 'old');
      var validations = 0;
      messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
        call,
      ) async {
        if (call.method == 'beginLibraryMutation') return true;
        if (call.method == 'endLibraryMutation') return null;
        if ((call.arguments as Map)['path'] != '') {
          expect(
            await File(p.join(root.path, 'system/prod.keys')).readAsString(),
            'old',
          );
          validations++;
        }
        return {'success': true};
      });
      final result = await MelonxEmbeddedLibraryService.importKeyFiles([
        title,
        prod,
      ]);
      expect(validations, 2);
      expect(result.imported.toSet(), {'prod.keys', 'title.keys'});
      expect(result.refused, isEmpty);
      expect(result.prodMissing, false);
      expect(
        await File(p.join(root.path, 'system/prod.keys')).readAsString(),
        'header_key = ${'a' * 64}',
      );
      expect(await prod.readAsString(), contains('# personal'));
    },
  );
  test('single-key update preserves the unselected optional key', () async {
    await write(p.join(root.path, 'system/title.keys'), 'keep');
    final prod = await write(
      p.join(temporary.path, 'source/prod.keys'),
      'header_key = ${'a' * 64}',
    );
    final result = await MelonxEmbeddedLibraryService.importKeyFiles([prod]);
    expect(result.imported, ['prod.keys']);
    expect(
      await File(p.join(root.path, 'system/title.keys')).readAsString(),
      'keep',
    );
  });
  test(
    'duplicate types, unknown filenames and invalid material leave installed keys unchanged',
    () async {
      await write(p.join(root.path, 'system/prod.keys'), 'keep');
      final one = await write(
        p.join(temporary.path, 'a/prod.keys'),
        'header_key = ab',
      );
      final two = await write(
        p.join(temporary.path, 'b/prod.keys'),
        'header_key = cd',
      );
      final unknown = await write(
        p.join(temporary.path, 'a/random.keys'),
        'ab',
      );
      final title = await write(
        p.join(temporary.path, 'a/title.keys'),
        'broken',
      );
      final result = await MelonxEmbeddedLibraryService.importKeyFiles([
        one,
        two,
        unknown,
        title,
      ]);
      expect(result.imported, isEmpty);
      expect(result.refused, {
        'prod.keys': 'duplicateKey',
        'random.keys': 'unknownKey',
        'title.keys': 'invalidKey',
      });
      expect(
        await File(p.join(root.path, 'system/prod.keys')).readAsString(),
        'keep',
      );
    },
  );
  test(
    'reload failure restores both previous keys and reloads the restored set',
    () async {
      await write(p.join(root.path, 'system/prod.keys'), 'oldprod');
      await write(p.join(root.path, 'system/title.keys'), 'oldtitle');
      final prod = await write(
        p.join(temporary.path, 'a/prod.keys'),
        'header_key = ${'a' * 64}',
      );
      final title = await write(
        p.join(temporary.path, 'a/title.keys'),
        '${'b' * 32} = ${'c' * 32}',
      );
      var reloads = 0;
      messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
        call,
      ) async {
        if (call.method == 'beginLibraryMutation') return true;
        if (call.method == 'endLibraryMutation') return null;
        if ((call.arguments as Map)['path'] == '') {
          reloads++;
          return {'success': reloads > 1, 'diagnostic': 'reload failed'};
        }
        return {'success': true};
      });
      await expectLater(
        MelonxEmbeddedLibraryService.importKeyFiles([prod, title]),
        throwsStateError,
      );
      expect(reloads, 2);
      expect(
        await File(p.join(root.path, 'system/prod.keys')).readAsString(),
        'oldprod',
      );
      expect(
        await File(p.join(root.path, 'system/title.keys')).readAsString(),
        'oldtitle',
      );
    },
  );
  test(
    'missing mandatory key is reported while the optional title key can be updated',
    () async {
      final title = await write(
        p.join(temporary.path, 'a/title.keys'),
        '${'b' * 32} = ${'c' * 32}',
      );
      final result = await MelonxEmbeddedLibraryService.importKeyFiles([title]);
      expect(result.prodMissing, true);
      expect(result.imported, ['title.keys']);
    },
  );
  test(
    'real library scan discovers moved files without copying and preserves metadata through relocation',
    () async {
      final helper = DatabaseTestHelper();
      final db = await helper.setUp();
      addTearDown(helper.tearDown);
      await db.insert('app_systems', {
        'id': 'switch',
        'folder_name': 'switch',
        'real_name': 'Nintendo Switch',
      });
      await db.insert('app_system_extensions', {
        'system_id': 'switch',
        'extension': 'nro',
      });
      var inspected = 0;
      messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
        call,
      ) async {
        expect(call.method, 'metadata');
        inspected++;
        if ((call.arguments as Map)['path'].toString().endsWith('Update.nsp'))
          return {
            'success': false,
            'diagnostic': 'not a base game',
            'error': 'InvalidDataException',
          };
        return {
          'success': true,
          'titleId': '0100123456780000',
          'title': 'Personal game',
        };
      });
      final game = await write(
        p.join(root.path, 'roms/switch/Personal.nro'),
        'personal bytes',
      );
      await write(p.join(root.path, 'roms/switch/Update.nsp'), 'addon');
      final config = SqliteConfigProvider();
      addTearDown(config.dispose);
      expect(await MelonxLibraryScanner.refresh(config), 1);
      expect((await db.query('user_roms')).single['rom_path'], game.path);
      await db.execute(
        "UPDATE user_roms SET is_favorite=1,play_time=123,title_name='Custom metadata'",
      );
      final before = inspected;
      expect(await MelonxLibraryScanner.refresh(config), 0);
      // Both unchanged games and native data rejections are cached until the file or keys change.
      expect(inspected - before, 0);
      final relocated = p.join(root.path, 'roms/switch/Moved/Renamed.nro');
      await Directory(p.dirname(relocated)).create();
      await game.rename(relocated);
      expect(await MelonxLibraryScanner.refresh(config), 1);
      var rows = await db.query('user_roms');
      expect(rows, hasLength(1));
      expect(rows.single['rom_path'], relocated);
      expect(rows.single['is_favorite'], 1);
      expect(rows.single['play_time'], 123);
      expect(rows.single['title_name'], 'Custom metadata');
      final copy = p.join(root.path, 'roms/switch/duplicate.nro');
      await File(relocated).copy(copy);
      await MelonxLibraryScanner.refresh(config);
      rows = await db.query('user_roms');
      expect(rows, hasLength(1));
      expect(await File(relocated).readAsString(), 'personal bytes');
    },
  );
  test(
    'a legacy unique title can be relocated without losing its existing row',
    () async {
      final helper = DatabaseTestHelper();
      final db = await helper.setUp();
      addTearDown(helper.tearDown);
      await db.insert('app_systems', {
        'id': 'switch',
        'folder_name': 'switch',
        'real_name': 'Nintendo Switch',
      });
      await Directory(p.join(temporary.path, 'old')).create();
      await db.insert('user_roms', {
        'app_system_id': 'switch',
        'filename': 'Original.nsp',
        'rom_path': p.join(temporary.path, 'old/Original.nsp'),
        'title_id': '0100123456780000',
        'play_time': 456,
      });
      final game = await write(
        p.join(root.path, 'roms/switch/NewName.nsp'),
        'moved',
      );
      messenger.setMockMethodCallHandler(
        MelonxInternalService.channel,
        (call) async => {
          'success': true,
          'titleId': '0100123456780000',
          'title': 'Same base title',
        },
      );
      final config = SqliteConfigProvider();
      addTearDown(config.dispose);
      await MelonxLibraryScanner.refresh(config);
      final rows = await db.query('user_roms');
      expect(rows, hasLength(1));
      expect(rows.single['filename'], 'Original.nsp');
      expect(rows.single['rom_path'], game.path);
      expect(rows.single['play_time'], 456);
    },
  );
}
