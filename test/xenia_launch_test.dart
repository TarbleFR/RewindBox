import 'dart:io';
import 'dart:ui' show Locale;

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/xenia_internal_service.dart';
import 'package:neostation/services/xenia_jit_service.dart';
import 'package:neostation/services/xenia_settings_service.dart';
import 'package:path/path.dart' as path;
import 'package:xenia_internal_bridge/xenia_internal_bridge.dart';

/// XeniaInternalService.launch and the JIT transaction (review D1 of #172):
/// the cheap refusals come before the helper; a launch that never reaches
/// the bridge ends the transaction prepared for it, so the next prepareJit
/// is accepted. The bridge ends it itself on every failure it reports
/// (test/xenia_launch_transaction_test.py).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory temp;
  late List<String> calls;
  late File game;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('xenia_launch_');
    XeniaInternalService.documentsDirectory = () async =>
        Directory(path.join(temp.path, 'Documents'));
    XeniaInternalService.cachesDirectory = () async =>
        Directory(path.join(temp.path, 'Caches'));
    XeniaInternalService.availabilityForTesting =
        const XeniaRuntimeAvailability(XeniaRuntimeState.ready);
    XeniaInternalService.settingsForTesting = XeniaSettingsService(
      frontendDirectory: () async =>
          Directory(path.join(temp.path, 'Documents', 'XeniOS', 'Frontend')),
    );
    calls = <String>[];
    // A TXM device whose region is not prepared: the helper is attached for
    // the Core's handshake and the transaction stays open for the launch.
    XeniaJitService.jitState = () async => <String, dynamic>{
      'needsTool': true,
      'transportFullWidth': true,
      'codeRegionHeld': true,
      'toolAttached': false,
    };
    XeniaJitService.pairingFile = () async => File('/tmp/pairing.plist');
    XeniaJitService.probeRoute = () async {};
    XeniaJitService.prepareJit =
        ({
          required String pairingFilePath,
          required bool requiresCoreHandshake,
        }) async {
          calls.add('prepareJit');
          return <String, dynamic>{
            'success': true,
            'helperConnected': true,
            'pidAttached': true,
            'debugged': true,
          };
        };
    XeniaJitService.completeJit = () async => <String, dynamic>{
      'success': true,
    };
    XeniaInternalService.abortJit = () async => calls.add('abortJit');
    XeniaInternalService.bridgeLaunch =
        ({
          required String gamePath,
          required int contentKind,
          required String title,
          required Map<String, String> settings,
          required Map<String, String> directories,
          String? touchGameKey,
          String locale = 'en',
          Map<String, String> texts = const <String, String>{},
          String overlay = 'off',
        }) async {
          calls.add('launch:$contentKind');
          return <String, dynamic>{'success': true};
        };
    final games = await XeniaInternalService.gamesDirectory();
    await games.create(recursive: true);
    game = File(path.join(games.path, 'Game.zar'))..writeAsBytesSync([1, 2, 3]);
  });

  tearDown(() async {
    XeniaInternalService.availabilityForTesting = null;
    XeniaInternalService.settingsForTesting = null;
    await temp.delete(recursive: true);
  });

  Future<XeniaLaunchOutcome> launch(String romPath) =>
      XeniaInternalService.launch(
        romPath: romPath,
        title: 'Game',
        uiLocale: const Locale('fr'),
      );

  test(
    'a fatal error record of an earlier session is logged once, then removed',
    () async {
      final engine = await XeniaInternalService.engineDirectory();
      await engine.create(recursive: true);
      final record = File(path.join(engine.path, 'last-fatal.txt'))
        ..writeAsStringSync(
          "Xenia couldn't find room for its JIT memory in the part of the "
          'address space the JIT tool can prepare.\n',
        );
      final launched = await launch(game.path);
      expect(
        launched.success,
        isTrue,
        reason: 'the record never blocks a launch',
      );
      expect(record.existsSync(), isFalse);
      expect(await XeniaInternalService.takePreviousFatal(), isNull);
      record.writeAsStringSync('  \n');
      expect(await XeniaInternalService.takePreviousFatal(), isNull);
      expect(record.existsSync(), isFalse);
    },
  );

  test('the previous launch journal is logged once, then removed', () async {
    final engine = await XeniaInternalService.engineDirectory();
    await engine.create(recursive: true);
    final journal = File(path.join(engine.path, 'launch-journal.txt'))
      ..writeAsStringSync(
        '10.000 launch: codeRegion=host\n10.100 present\n10.400 presented\n'
        '10.401 nonce probe\n10.402 prepare\n',
      );
    final stages = await XeniaInternalService.takePreviousLaunchJournal();
    expect(stages, hasLength(5));
    expect(stages!.last, '10.402 prepare');
    expect(journal.existsSync(), isFalse);
    expect(await XeniaInternalService.takePreviousLaunchJournal(), isNull);
    journal.writeAsStringSync('1.0 present\n2.0 launched\n');
    expect(await launch(game.path), isA<XeniaLaunchOutcome>());
    expect(journal.existsSync(), isFalse, reason: 'read before each launch');
  });

  test(
    'no code region below 8 GB: refused before the helper and the bridge',
    () async {
      XeniaJitService.jitState = () async => <String, dynamic>{
        'needsTool': true,
        'transportFullWidth': true,
        'toolAttached': false,
        'codeRegionHeld': false,
      };
      final refused = await launch(game.path);
      expect(refused.success, isFalse);
      expect(refused.error, 'jitMemoryUnavailable');
      expect(calls, isEmpty, reason: 'no helper attach, no bridge launch');
    },
  );

  test(
    'a JIT tool without full-width addresses: refused before the helper and the bridge',
    () async {
      XeniaJitService.jitState = () async => <String, dynamic>{
        'needsTool': true,
        'transportFullWidth': false,
        'codeRegionHeld': true,
        'toolAttached': false,
      };
      final refused = await launch(game.path);
      expect(refused.success, isFalse);
      expect(refused.error, 'jitToolUnsupported');
      expect(calls, isEmpty, reason: 'no helper attach, no bridge launch');
    },
  );

  test(
    'an unsupported or missing game is refused before any JIT helper',
    () async {
      final unsupported = await launch(path.join(temp.path, 'notes.txt'));
      expect(unsupported.error, 'unsupported');
      final missing = await launch(path.join(temp.path, 'Gone.iso'));
      expect(missing.error, 'gameUnreadable');
      expect(
        calls,
        isEmpty,
        reason: 'no transaction opened for a launch that cannot happen',
      );
    },
  );

  test(
    'a launch that never reaches the bridge ends its transaction; the next one prepares again',
    () async {
      XeniaInternalService.bridgeLaunch =
          ({
            required String gamePath,
            required int contentKind,
            required String title,
            required Map<String, String> settings,
            required Map<String, String> directories,
            String? touchGameKey,
            String locale = 'en',
            Map<String, String> texts = const <String, String>{},
            String overlay = 'off',
          }) async {
            throw PlatformException(code: 'channel-error');
          };
      final failed = await launch(game.path);
      expect(failed.success, isFalse);
      expect(failed.error, 'launchFailed');
      expect(calls, <String>['prepareJit', 'abortJit']);

      calls.clear();
      XeniaInternalService.bridgeLaunch =
          ({
            required String gamePath,
            required int contentKind,
            required String title,
            required Map<String, String> settings,
            required Map<String, String> directories,
            String? touchGameKey,
            String locale = 'en',
            Map<String, String> texts = const <String, String>{},
            String overlay = 'off',
          }) async {
            calls.add('launch:$contentKind');
            return <String, dynamic>{'success': true};
          };
      final next = await launch(game.path);
      expect(next.success, isTrue);
      expect(calls, <String>['prepareJit', 'launch:2']);
    },
  );

  test(
    'a failure the bridge reports is passed on; the bridge itself ends the transaction',
    () async {
      XeniaInternalService.bridgeLaunch =
          ({
            required String gamePath,
            required int contentKind,
            required String title,
            required Map<String, String> settings,
            required Map<String, String> directories,
            String? touchGameKey,
            String locale = 'en',
            Map<String, String> texts = const <String, String>{},
            String overlay = 'off',
          }) async {
            calls.add('launch:$contentKind');
            return <String, dynamic>{
              'success': false,
              'error': 'bootFailed',
              'detail': 'x',
            };
          };
      final failed = await launch(game.path);
      expect(failed.error, 'bootFailed');
      expect(calls, <String>['prepareJit', 'launch:2']);
    },
  );

  test('the launch sends the overlay level and the in-game menu texts', () async {
    await XeniaInternalService.settings.setPerformanceOverlay('detailed');
    String? sentOverlay;
    Map<String, String>? sentTexts;
    Map<String, String>? sentSettings;
    XeniaInternalService.bridgeLaunch =
        ({
          required String gamePath,
          required int contentKind,
          required String title,
          required Map<String, String> settings,
          required Map<String, String> directories,
          String? touchGameKey,
          String locale = 'en',
          Map<String, String> texts = const <String, String>{},
          String overlay = 'off',
        }) async {
          sentOverlay = overlay;
          sentTexts = texts;
          sentSettings = settings;
          return <String, dynamic>{'success': true};
        };
    expect((await launch(game.path)).success, isTrue);
    expect(sentOverlay, 'detailed');
    expect(sentSettings!.keys, containsAll(<String>['widescreen', 'internal_display_resolution']));
    expect(sentSettings!['widescreen'], 'true');
    expect(sentSettings!['internal_display_resolution'], '8');
    expect(sentTexts!.keys.toSet(), <String>{'menu', 'resume', 'quit', ...XeniaInternalService.sessionTextKeys});
    expect(sentTexts!.length, 28);
    expect(sentTexts!['display'], 'Affichage');
    expect(sentTexts!['overlay'], 'Surimpression de performances');
    expect(sentTexts!['aspectWide'], '16:9 (grand écran)');
    expect(sentTexts!['aspectStandard'], '4:3');
    expect(sentTexts!['saveFailed'], 'Réglage non enregistré.');
    expect(sentTexts!['fps'], 'FPS');
    for (final entry in sentTexts!.entries) {
      expect(entry.value.trim(), isNotEmpty, reason: entry.key);
    }
  });

  test('the overlay defaults to off at launch', () async {
    String? sentOverlay;
    XeniaInternalService.bridgeLaunch =
        ({
          required String gamePath,
          required int contentKind,
          required String title,
          required Map<String, String> settings,
          required Map<String, String> directories,
          String? touchGameKey,
          String locale = 'en',
          Map<String, String> texts = const <String, String>{},
          String overlay = 'off',
        }) async {
          sentOverlay = overlay;
          return <String, dynamic>{'success': true};
        };
    await launch(game.path);
    expect(sentOverlay, 'off');
  });

  test('in-game changes are persisted for the running game only when accepted', () async {
    await launch(game.path);
    final key = await XeniaSettingsService.gameKeyForFile(game.path);
    final settings = XeniaInternalService.settings;
    await XeniaInternalService.onSettingChanged('widescreen', 'false');
    await XeniaInternalService.onSettingChanged('internal_display_resolution', '16');
    await XeniaInternalService.onSettingChanged('present_letterbox', 'false');
    expect(settings.gameValue(key, 'widescreen'), 'false');
    expect(settings.gameValue(key, 'internal_display_resolution'), '16');
    expect(settings.gameValue(key, 'present_letterbox'), 'false');
    expect(settings.globalValue('widescreen'), isNull);
    // Unknown key, value outside the list, 17 (custom): ignored, no throw.
    await XeniaInternalService.onSettingChanged('draw_resolution_scale', '2');
    await XeniaInternalService.onSettingChanged('internal_display_resolution', '17');
    await XeniaInternalService.onSettingChanged('widescreen', 'maybe');
    await XeniaInternalService.onSettingChanged(null, 'x');
    expect(settings.gameValue(key, 'internal_display_resolution'), '16');
    expect(settings.gameValue(key, 'widescreen'), 'false');

    await XeniaInternalService.onOverlayChanged('simple');
    expect(settings.performanceOverlay, 'simple');
    await XeniaInternalService.onOverlayChanged('bogus');
    expect(settings.performanceOverlay, 'simple');
  });

  test('an unwritable settings file does not crash the in-game handlers', () async {
    await launch(game.path);
    final frontend = Directory(path.join(temp.path, 'Documents', 'XeniOS', 'Frontend'));
    await frontend.create(recursive: true);
    // A directory where the temporary file must go: the save fails.
    await Directory(path.join(frontend.path, '${XeniaSettingsService.fileName}.tmp')).create();
    await XeniaInternalService.onSettingChanged('widescreen', 'false');
    await XeniaInternalService.onOverlayChanged('detailed');
    expect(XeniaInternalService.settings.performanceOverlay, 'off');
  });
}
