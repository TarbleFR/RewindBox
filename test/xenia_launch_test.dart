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
}
