import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
// Existing transitive path_provider platform boundary; no new app dependency.
// ignore: depend_on_referenced_packages
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/services/frontend_media_gate.dart';
import 'package:neostation/services/ios_library_root_relocation.dart';
import 'package:neostation/services/melonx_internal_service.dart';
import 'package:neostation/services/melonx_library_scanner.dart';
import 'database_test_helper.dart';

// Switch discovery used to hash whole 7-16 GB games on the root isolate (the
// iOS main thread) and kept hashing into MeloNX sessions (builds 575-576
// app.log). These tests cover the native digest path, the stop at a launch,
// the index kept across a stop, and index entries that follow their files
// into a new iOS app container.

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
  const launch = 'test launch';
  late Directory temporary, root;
  late PathProviderPlatform previous;
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    temporary = await Directory.systemTemp.createTemp('melonx-discovery-');
    previous = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Paths(temporary.path);
    root = await MelonxInternalService.rootDirectory();
  });
  tearDown(() async {
    FrontendMediaGate.instance.release(launch);
    MelonxLibraryScanner.nativeDigests = false;
    MelonxLibraryScanner.containerOf = IosLibraryRootRelocation.split;
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, null);
    PathProviderPlatform.instance = previous;
    await temporary.delete(recursive: true);
  });

  Future<dynamic> database() async {
    final helper = DatabaseTestHelper();
    final db = await helper.setUp();
    addTearDown(helper.tearDown);
    await db.insert('app_systems', {
      'id': 'switch',
      'folder_name': 'switch',
      'real_name': 'Nintendo Switch',
    });
    return db;
  }

  test('the whole-file digest is unchanged and computed off the root isolate',
      () async {
    final game = await write(p.join(temporary.path, 'Game.nsp'), 'game bytes');
    expect(
      await MelonxLibraryScanner.fingerprint(game),
      sha256.convert(utf8.encode('game bytes')).toString(),
    );
  });

  test('an index entry follows its file into the current app container', () {
    const old =
        '/var/mobile/Containers/Data/Application/11111111-1111-1111-1111-111111111111';
    const now =
        '/var/mobile/Containers/Data/Application/22222222-2222-2222-2222-222222222222';
    final game = {
      'stamp': '5:7',
      'sha256': 'a' * 64,
      'info': {'titleId': '0100123456780000'},
    };
    final index = <String, dynamic>{
      '$old/Documents/MeloNX/roms/switch/Game.nsp': game,
      // Outside every scan root: not mapped.
      '$old/Documents/Other/Elsewhere.nsp': {'stamp': '1:1'},
      // Not in an app container.
      '/tmp/library/Loose.nsp': {'stamp': '1:1'},
      // Already indexed in the current container: kept as it is.
      '$now/Documents/MeloNX/roms/switch/Known.nsp': {'stamp': '2:2'},
      '$old/Documents/MeloNX/roms/switch/Known.nsp': {'stamp': '9:9'},
    };
    final moves = MelonxLibraryScanner.containerMoves(index, [
      '$now/Documents/MeloNX',
      '$now/Documents/MeloNX/roms',
      '/tmp/library',
    ]);
    expect(moves.keys, ['$now/Documents/MeloNX/roms/switch/Game.nsp']);
    expect(moves.values.single.toSet(), {game});
    expect(MelonxLibraryScanner.containerMoves(index, ['/tmp/library']), isEmpty);
  });

  test('discovery does not start while a game holds the frontend', () async {
    await database();
    var calls = 0;
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
      call,
    ) async {
      calls++;
      return null;
    });
    await write(p.join(root.path, 'roms/switch/Game.nsp'), 'game');
    final config = SqliteConfigProvider();
    addTearDown(config.dispose);
    await FrontendMediaGate.instance.hold(launch);
    expect(await MelonxLibraryScanner.refresh(config), 0);
    expect(calls, 0);
    expect(
      await File(p.join(root.path, 'cache', 'rewindbox-library.json')).exists(),
      false,
    );
  });

  test(
    'a launch stops discovery at its native hash; what was indexed is kept and not hashed again',
    () async {
      final db = await database();
      MelonxLibraryScanner.nativeDigests = true;
      final inspected = <String>[];
      final hashed = <String>[];
      var cancels = 0;
      var launchDuringSecondHash = true;
      messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
        call,
      ) async {
        switch (call.method) {
          case 'cancelFingerprint':
            cancels++;
            return null;
          case 'metadata':
            final name = p.basename((call.arguments as Map)['path'] as String);
            inspected.add(name);
            return {
              'success': true,
              'titleId': '0100123456780${name.codeUnitAt(0) - 64}00',
              'title': name,
            };
          case 'fingerprint':
            final location = (call.arguments as Map)['path'] as String;
            hashed.add(p.basename(location));
            if (hashed.length == 2 && launchDuringSecondHash) {
              // A launch takes the frontend while this file is being hashed.
              FrontendMediaGate.instance.hold(launch);
              throw PlatformException(code: 'cancelled');
            }
            return sha256.convert(utf8.encode(location)).toString();
        }
        return null;
      });
      for (final name in ['A.nsp', 'B.nsp', 'C.nsp'])
        await write(p.join(root.path, 'roms/switch/$name'), name);
      final config = SqliteConfigProvider();
      addTearDown(config.dispose);

      expect(await MelonxLibraryScanner.refresh(config), 1);
      await pumpEventQueue();
      expect(cancels, 1);
      expect(hashed, hasLength(2));
      // The third file was never opened.
      expect(inspected, hasLength(2));
      expect(await db.query('user_roms'), hasLength(1));
      final first = hashed.first;
      final cache = File(p.join(root.path, 'cache', 'rewindbox-library.json'));
      final index = jsonDecode(await cache.readAsString()) as Map;
      expect(index.keys.map((key) => p.basename(key as String)), [first]);

      // Nothing runs while the game is up.
      expect(await MelonxLibraryScanner.refresh(config), 0);
      expect(hashed, hasLength(2));

      FrontendMediaGate.instance.release(launch);
      launchDuringSecondHash = false;
      expect(await MelonxLibraryScanner.refresh(config), 2);
      expect(await db.query('user_roms'), hasLength(3));
      // Four digests in all: the file indexed before the stop is not hashed again.
      expect(hashed, hasLength(4));
      expect(hashed.where((name) => name == first), hasLength(1));
    },
  );

  test('a launch during the metadata call sends no native hash request', () async {
    final db = await database();
    MelonxLibraryScanner.nativeDigests = true;
    final calls = <String>[];
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
      call,
    ) async {
      calls.add(call.method);
      if (call.method == 'metadata') {
        // The player starts a game while the native metadata call runs.
        FrontendMediaGate.instance.hold(launch);
        return {
          'success': true,
          'titleId': '0100123456780000',
          'title': 'Game',
        };
      }
      if (call.method == 'fingerprint') return 'f' * 64;
      return null;
    });
    await write(p.join(root.path, 'roms/switch/Game.nsp'), 'game');
    final config = SqliteConfigProvider();
    addTearDown(config.dispose);
    expect(await MelonxLibraryScanner.refresh(config), 0);
    await pumpEventQueue();
    expect(calls, ['metadata', 'cancelFingerprint']);
    expect(await db.query('user_roms'), isEmpty);
  });

  test(
    'after a container move, a game whose row is already at its new path keeps its digest there',
    () async {
      final db = await database();
      const oldContainer = '11111111-1111-1111-1111-111111111111';
      const newContainer = '22222222-2222-2222-2222-222222222222';
      final containers = p.join(temporary.path, 'Containers');
      final pattern = RegExp(
        '^(${RegExp.escape(containers)}/[0-9A-Fa-f-]{36})(?:/(.*))?\$',
      );
      MelonxLibraryScanner.containerOf = (location) {
        final match = pattern.firstMatch(p.normalize(location));
        return match == null
            ? null
            : (container: match.group(1)!, relative: match.group(2) ?? '');
      };
      PathProviderPlatform.instance = _Paths(
        p.join(containers, newContainer, 'Documents'),
      );
      root = await MelonxInternalService.rootDirectory();
      MelonxLibraryScanner.nativeDigests = true;
      final hashed = <String>[];
      final inspected = <String>[];
      messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
        call,
      ) async {
        final location = (call.arguments as Map?)?['path'] as String?;
        if (call.method == 'metadata') {
          inspected.add(p.basename(location!));
          return {
            'success': true,
            'titleId': '0100123456780000',
            'title': 'Game',
          };
        }
        if (call.method == 'fingerprint') {
          hashed.add(p.basename(location!));
          return sha256.convert(await File(location).readAsBytes()).toString();
        }
        return null;
      });
      final game = await write(p.join(root.path, 'roms/switch/Game.nsp'), 'game');
      final stat = await game.stat();
      final digest = sha256.convert(utf8.encode('game')).toString();
      // Indexed in the former container; the general scan already added the
      // row at the new path, as it does at startup after a container move.
      final oldPath = p.join(
        containers,
        oldContainer,
        'Documents/MeloNX/roms/switch/Game.nsp',
      );
      await write(
        p.join(root.path, 'cache', 'rewindbox-library.json'),
        jsonEncode({
          oldPath: {
            'stamp': '${stat.size}:${stat.modified.microsecondsSinceEpoch}',
            'sha256': digest,
            'info': {'titleId': '0100123456780000', 'title': 'Game'},
          },
        }),
      );
      await db.insert('user_roms', {
        'app_system_id': 'switch',
        'filename': 'Game.nsp',
        'rom_path': game.path,
        'title_id': '0100123456780000',
      });
      final config = SqliteConfigProvider();
      addTearDown(config.dispose);

      expect(await MelonxLibraryScanner.refresh(config), 0);
      expect(hashed, isEmpty);
      expect(inspected, isEmpty);
      final index =
          jsonDecode(
                await File(
                  p.join(root.path, 'cache', 'rewindbox-library.json'),
                ).readAsString(),
              )
              as Map;
      expect((index[game.path] as Map)['sha256'], digest);

      // A copy of the game is still recognized as a duplicate of its row.
      await Directory(p.join(root.path, 'games')).create(recursive: true);
      await File(game.path).copy(p.join(root.path, 'games/Copy.nsp'));
      await MelonxLibraryScanner.refresh(config);
      expect(hashed, ['Copy.nsp']);
      expect(await db.query('user_roms'), hasLength(1));
    },
  );
}
