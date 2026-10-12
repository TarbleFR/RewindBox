// Core option store (3DS system settings, docs/libretro-3ds-system-settings.md
// § 3.3): the Dart side of Documents/Libretro/Config/<core>.json, the file
// the native LibretroCoreOptions saves as {"values": {...}}. Reads tolerate
// a missing file and ignore non-string values, writes merge key by key
// (null removes, unknown keys survive) through <name>.json.tmp and a
// rename, and every write is refused while a libretro session is active
// or launching (isSessionActive, simulated on the method channel) or when
// the probe fails. All roots are temporary folders.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/libretro_core_option_store.dart';
import 'package:path/path.dart' as p;

/// `Config/Azahar.json` exactly as NSJSONSerialization pretty-prints it
/// (space before the colon, unsorted keys, a non-string value a core could
/// never have stored but the loader must ignore).
const String _nativeFixture = '''
{
  "values" : {
    "citra_region_value" : "Japan",
    "citra_use_libretro_save_path" : "LibRetro Default",
    "citra_is_new_3ds" : "Old 3DS",
    "unexpected_number" : 3
  }
}
''';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory root;
  late Directory config;

  setUp(() async {
    root = await Directory.systemTemp.createTemp('neostation-option-store-');
    config = Directory(p.join(root.path, 'Config'));
  });

  tearDown(() async {
    if (await root.exists()) await root.delete(recursive: true);
  });

  LibretroCoreOptionStore store({
    bool active = false,
    bool probeFails = false,
  }) => LibretroCoreOptionStore(
    configDirectory: () async => config,
    sessionProbe: () async {
      if (probeFails) throw PlatformException(code: 'transient');
      return active;
    },
  );

  File azaharFile() => File(
    p.join(
      config.path,
      LibretroCoreOptionStore.libraryFileName(
        LibretroCoreOptionStore.azaharLibraryName,
      ),
    ),
  );

  Future<List<String>> listing() async {
    if (!await config.exists()) return const [];
    return [for (final entity in config.listSync()) p.basename(entity.path)]
      ..sort();
  }

  group('file name', () {
    test('reproduces SafeFolderName of LibretroCoreHost.m', () {
      expect(LibretroCoreOptionStore.safeFolderName('Azahar'), 'Azahar');
      expect(LibretroCoreOptionStore.safeFolderName('a/b\\c:d'), 'a_b_c_d');
      expect(LibretroCoreOptionStore.safeFolderName('/'), '_');
      expect(LibretroCoreOptionStore.safeFolderName('::'), '__');
      expect(LibretroCoreOptionStore.safeFolderName(''), 'core');
      expect(
        LibretroCoreOptionStore.safeFolderName('Snes9x 2010'),
        'Snes9x 2010',
      );
      expect(LibretroCoreOptionStore.libraryFileName('Azahar'), 'Azahar.json');
      expect(
        LibretroCoreOptionStore.libraryFileName('PCSX-ReARMed'),
        'PCSX-ReARMed.json',
      );
      expect(LibretroCoreOptionStore.libraryFileName(''), 'core.json');
    });

    test('azaharLibraryName is the library name the core declares', () {
      final fixture =
          jsonDecode(
                File(
                  'test/fixtures/libretro_bios/core_info_5a74858a.json',
                ).readAsStringSync(),
              )
              as Map<String, dynamic>;
      final cores =
          (fixture['coreInfo'] as Map<String, dynamic>)['cores']
              as Map<String, dynamic>;
      final azahar = cores['azahar'] as Map<String, dynamic>;
      expect(azahar['corename'], LibretroCoreOptionStore.azaharLibraryName);
      expect(
        LibretroCoreOptionStore.libraryFileName(
          LibretroCoreOptionStore.azaharLibraryName,
        ),
        'Azahar.json',
      );
    });

    test('filePath joins the config directory and the file name', () async {
      expect(
        await store().filePath('Azahar'),
        p.join(config.path, 'Azahar.json'),
      );
    });
  });

  group('read', () {
    test('absent file is an empty map and creates nothing', () async {
      expect(await store().read('Azahar'), isEmpty);
      expect(await config.exists(), isFalse);
    });

    test('reads the native format and ignores non-string values', () async {
      await config.create(recursive: true);
      await azaharFile().writeAsString(_nativeFixture);
      expect(await store().read('Azahar'), {
        'citra_region_value': 'Japan',
        'citra_use_libretro_save_path': 'LibRetro Default',
        'citra_is_new_3ds': 'Old 3DS',
      });
    });

    test(
      'unreadable JSON, a non-object root and a missing values key are empty',
      () async {
        await config.create(recursive: true);
        await azaharFile().writeAsString('{"values": {');
        expect(await store().read('Azahar'), isEmpty);
        await azaharFile().writeAsString('[1, 2]');
        expect(await store().read('Azahar'), isEmpty);
        await azaharFile().writeAsString('{"other": {"a": "b"}}');
        expect(await store().read('Azahar'), isEmpty);
        await azaharFile().writeAsString('{"values": "not a map"}');
        expect(await store().read('Azahar'), isEmpty);
      },
    );
  });

  group('write', () {
    test('creates the file in the native {"values": {...}} format', () async {
      final written = await store().write('Azahar', {
        'citra_region_value': 'Auto',
        'citra_language_value': 'French',
      });
      expect(written, {
        'citra_region_value': 'Auto',
        'citra_language_value': 'French',
      });
      expect(await listing(), ['Azahar.json']);

      final text = await azaharFile().readAsString();
      final decoded = jsonDecode(text) as Map<String, dynamic>;
      expect(decoded.keys, ['values']);
      expect(decoded['values'], {
        'citra_language_value': 'French',
        'citra_region_value': 'Auto',
      });
      expect(
        text,
        const JsonEncoder.withIndent('  ').convert({
          'values': {
            'citra_language_value': 'French',
            'citra_region_value': 'Auto',
          },
        }),
      );
      // What the native loader keeps from this file is what we wrote.
      expect(LibretroCoreOptionStore.decode(text), written);
      expect(await store().read('Azahar'), written);
    });

    test(
      'merges key by key, removes with null and keeps unknown keys',
      () async {
        await config.create(recursive: true);
        await azaharFile().writeAsString(_nativeFixture);

        final after = await store().write('Azahar', {
          'citra_region_value': 'Auto',
          'citra_language_value': 'Japanese',
          'citra_is_new_3ds': null,
          'never_stored': null,
        });
        expect(after, {
          'citra_region_value': 'Auto',
          'citra_language_value': 'Japanese',
          'citra_use_libretro_save_path': 'LibRetro Default',
        });
        expect(await store().read('Azahar'), after);
        final decoded = jsonDecode(await azaharFile().readAsString()) as Map;
        expect(
          (decoded['values'] as Map).containsKey('citra_is_new_3ds'),
          isFalse,
        );
        expect(
          (decoded['values'] as Map).containsKey('unexpected_number'),
          isFalse,
        );
      },
    );

    test('is atomic: no .tmp left, a stale .tmp is replaced', () async {
      await config.create(recursive: true);
      final stale = File(
        '${azaharFile().path}${LibretroCoreOptionStore.temporarySuffix}',
      );
      await stale.writeAsString(
        '{"values": {"citra_region_value": "Korea"}} garbage',
      );

      await store().write('Azahar', {'citra_region_value': 'Europe'});
      expect(await listing(), ['Azahar.json']);
      expect(await stale.exists(), isFalse);
      expect(await store().read('Azahar'), {'citra_region_value': 'Europe'});
    });

    test('raw option values are written unchanged', () async {
      await store().write('Azahar', {
        'citra_language_value': 'Traditional Chinese',
        'citra_is_new_3ds': 'New 3DS',
      });
      expect(await store().read('Azahar'), {
        'citra_language_value': 'Traditional Chinese',
        'citra_is_new_3ds': 'New 3DS',
      });
    });

    test('other cores get their own SafeFolderName file', () async {
      await store().write('a/b:c', {'k': 'v'});
      expect(await listing(), ['a_b_c.json']);
      expect(await store().read('a/b:c'), {'k': 'v'});
      expect(await store().read('Azahar'), isEmpty);
    });
  });

  group('session guard', () {
    test('an active session refuses the write and touches nothing', () async {
      await config.create(recursive: true);
      await azaharFile().writeAsString(_nativeFixture);

      await expectLater(
        store(active: true).write('Azahar', {'citra_region_value': 'Auto'}),
        throwsA(
          isA<LibretroCoreOptionStoreException>().having(
            (e) => e.error,
            'error',
            LibretroCoreOptionStoreError.sessionActive,
          ),
        ),
      );
      expect(await azaharFile().readAsString(), _nativeFixture);
      expect(await listing(), ['Azahar.json']);
    });

    test('an active session refuses before the folder exists', () async {
      await expectLater(
        store(active: true).write('Azahar', {'citra_region_value': 'Auto'}),
        throwsA(isA<LibretroCoreOptionStoreException>()),
      );
      expect(await config.exists(), isFalse);
    });

    test('a failing probe is a refusal, never a write', () async {
      await expectLater(
        store(probeFails: true).write('Azahar', {'citra_region_value': 'Auto'}),
        throwsA(
          isA<LibretroCoreOptionStoreException>()
              .having(
                (e) => e.error,
                'error',
                LibretroCoreOptionStoreError.sessionActive,
              )
              .having(
                (e) => e.technicalDetail,
                'detail',
                contains('transient'),
              ),
        ),
      );
      expect(await config.exists(), isFalse);
    });

    test('reads are never refused by the session', () async {
      await config.create(recursive: true);
      await azaharFile().writeAsString(_nativeFixture);
      expect(
        (await store(active: true).read('Azahar'))['citra_region_value'],
        'Japan',
      );
    });

    test(
      'the default probe is isSessionActive on neostation/libretro_internal',
      () async {
        const channel = MethodChannel('neostation/libretro_internal');
        var active = true;
        final calls = <String>[];
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(channel, (call) async {
              calls.add(call.method);
              return active;
            });
        addTearDown(() {
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
              .setMockMethodCallHandler(channel, null);
        });

        final defaultProbe = LibretroCoreOptionStore(
          configDirectory: () async => config,
        );
        await expectLater(
          defaultProbe.write('Azahar', {'citra_region_value': 'Auto'}),
          throwsA(
            isA<LibretroCoreOptionStoreException>().having(
              (e) => e.error,
              'error',
              LibretroCoreOptionStoreError.sessionActive,
            ),
          ),
        );
        expect(calls, ['isSessionActive']);
        expect(await config.exists(), isFalse);

        active = false;
        expect(
          await defaultProbe.write('Azahar', {'citra_region_value': 'Auto'}),
          {'citra_region_value': 'Auto'},
        );
        expect(calls, ['isSessionActive', 'isSessionActive']);
        expect(await listing(), ['Azahar.json']);
      },
    );
  });
}
