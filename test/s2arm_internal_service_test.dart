import 'dart:io';
import 'dart:ui' show Locale;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/s2arm_engine_locale.dart';
import 'package:neostation/l10n/switch2_library_locale.dart';
import 'package:neostation/l10n/switch2_settings_locale.dart';
import 'package:neostation/services/s2arm_internal_service.dart';
import 'package:path_provider/path_provider.dart';

/// The Switch 2 engine service maps the native error codes to localized messages and the native status to a runtime state,
/// and imports an export folder through a fake method channel. No native plugin runs here.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('neostation/s2arm_internal');
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const en = Locale('en');
  const fr = Locale('fr');

  tearDown(() {
    messenger.setMockMethodCallHandler(channel, null);
    S2ArmInternalService.availabilityForTesting = null;
  });

  group('error mapping', () {
    test('every native code resolves to its own localized message', () {
      const cases = <String, String>{
        'engineRestartRequired': 'restartRequired',
        'notExportFolder': 'notExportFolder',
        'exportInvalid': 'exportInvalid',
        'gameIdMismatch': 'exportInvalid',
        'gameUnsupported': 'gameUnsupported',
        'rewriterFailed': 'rewriterFailed',
        'prepareFailed': 'rewriterFailed',
        'storageError': 'storageError',
        'copyFailed': 'storageError',
        'insufficientSpace': 'insufficientSpace',
        'notEnoughSpace': 'insufficientSpace',
        'systemDataMissing': 'systemDataMissing',
        'engineChainMissing': 'engineChainMissing',
        'enginePresent': 'engineChainMissing',
        'jitUnavailable': 'jitUnavailable',
        'jitPairingRequired': 'jitUnavailable',
        'cancelled': 'cancelled',
        'unavailable': 'unavailable',
      };
      cases.forEach((code, key) {
        expect(S2ArmInternalService.messageKey(code), key, reason: code);
        expect(S2ArmInternalService.localizedError(en, {'code': code}), S2ArmEngineLocale.text(en, key));
        expect(S2ArmInternalService.localizedError(fr, {'error': code}), S2ArmEngineLocale.text(fr, key));
      });
    });

    test('an unknown code falls back to the generic launch failure', () {
      expect(S2ArmInternalService.messageKey('somethingNew'), 'launchFailed');
      expect(S2ArmInternalService.localizedError(fr, {'error': 'somethingNew'}), S2ArmEngineLocale.text(fr, 'launchFailed'));
    });

    test('every locale carries every key used by the mapping', () {
      final keys = {
        for (final code in ['engineRestartRequired', 'notExportFolder', 'exportInvalid', 'gameUnsupported', 'rewriterFailed',
                            'storageError', 'insufficientSpace', 'systemDataMissing', 'engineChainMissing', 'jitUnavailable',
                            'cancelled', 'unavailable', 'x'])
          S2ArmInternalService.messageKey(code),
      };
      expect(S2ArmEngineLocale.values.length, 12);
      for (final entry in S2ArmEngineLocale.values.entries) {
        for (final key in keys) {
          expect(entry.value[key], isNotNull, reason: '${entry.key} is missing $key');
        }
      }
    });
  });

  group('availability', () {
    test('a non-iOS host is unsupported, and the testing override wins', () async {
      // defaultTargetPlatform is not iOS under the test host: availability() reports unsupportedPlatform.
      expect((await S2ArmInternalService.availability()).state, S2ArmRuntimeState.unsupportedPlatform);
      S2ArmInternalService.availabilityForTesting = const S2ArmRuntimeAvailability(S2ArmRuntimeState.ready);
      expect((await S2ArmInternalService.availability()).ready, isTrue);
      S2ArmInternalService.availabilityForTesting =
          const S2ArmRuntimeAvailability(S2ArmRuntimeState.engineMissing);
      expect((await S2ArmInternalService.availability()).state, S2ArmRuntimeState.engineMissing);
    });
  });

  group('import', () {
    late Directory temp;
    setUp(() async {
      temp = await Directory.systemTemp.createTemp('s2arm-import-');
      S2ArmInternalService.documentsDirectory = () async => temp;
      S2ArmInternalService.freeBytes = (_) => 1 << 40;   // plenty of room
    });
    tearDown(() async {
      S2ArmInternalService.documentsDirectory = () async => temp;   // reset below
      if (await temp.exists()) await temp.delete(recursive: true);
    });

    test('a folder detectExport rejects is refused, nothing is copied', () async {
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'detectExport') return {'success': false, 'code': 'notExportFolder'};
        return null;
      });
      final source = await Directory('${temp.path}/not-a-game').create();
      final result = await S2ArmInternalService.importFolderAt(source.path);
      expect(result.imported, 0);
      expect(result.items.single.reason, 'notExportFolder');
      final games = await S2ArmInternalService.gamesDirectory();
      expect(await games.list().isEmpty, isTrue);
    });

    test('a recognised export is staged and renamed into Games/<title>', () async {
      final source = await Directory('${temp.path}/export/base/exefs').create(recursive: true);
      await File('${source.path}/main').writeAsBytes(List<int>.filled(1024, 7));
      final exportDir = Directory('${temp.path}/export');
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'detectExport') {
          return {'success': true, 'exportDir': exportDir.path, 'gid': '0100ABCDEF000000', 'programId': '0100abcdef000000'};
        }
        if (call.method == 'gameInfo') return {'success': true, 'title': 'Test Game', 'titleId': '0100abcdef000000'};
        return null;
      });
      final progress = <double?>[];
      final result = await S2ArmInternalService.importFolderAt(exportDir.path, onProgress: (p) => progress.add(p.fraction));
      expect(result.imported, 1, reason: result.items.map((i) => i.reason).join(','));
      final imported = Directory(result.items.single.destination!);
      expect(await imported.exists(), isTrue);
      expect(imported.path.endsWith('Games/Test Game'), isTrue);
      expect(await File('${imported.path}/base/exefs/main').length(), 1024);
      final staging = await S2ArmInternalService.stagingDirectory();
      expect(await staging.exists(), isFalse, reason: 'staging is cleaned up');
    });

    test('too little free space refuses the import before copying', () async {
      S2ArmInternalService.freeBytes = (_) => 1024;   // below the margin
      final source = await Directory('${temp.path}/export/base/exefs').create(recursive: true);
      await File('${source.path}/main').writeAsBytes(List<int>.filled(4096, 1));
      final exportDir = Directory('${temp.path}/export');
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'detectExport') return {'success': true, 'exportDir': exportDir.path, 'gid': '0100ABCDEF000000'};
        if (call.method == 'gameInfo') return {'success': true, 'title': 'Big Game'};
        return null;
      });
      final result = await S2ArmInternalService.importFolderAt(exportDir.path);
      expect(result.imported, 0);
      expect(result.items.single.reason, 'notEnoughSpace');
    });
  });

  group('prepare and launch', () {
    test('prepare forwards progress events and returns the native map', () async {
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'prepareGame') {
          // Deliver one progress call back through the plugin's channel handler before returning.
          await messenger.handlePlatformMessage(
            channel.name,
            channel.codec.encodeMethodCall(const MethodCall('prepareProgress', {'step': 'code', 'index': 1, 'count': 6, 'fraction': 0.5})),
            (_) {});
          return {'success': true, 'gid': '0100ABCDEF000000', 'imagesPath': '/x', 'moduleDir': '/m', 'gameData': '/g', 'docs': '/d'};
        }
        return null;
      });
      final steps = <String>[];
      final report = await S2ArmInternalService.prepare(exportFolder: '/export', onProgress: (p) => steps.add(p.name));
      expect(report['success'], isTrue);
      expect(report['gid'], '0100ABCDEF000000');
      expect(steps, contains('code'));
    });

    test('a PlatformException from launchGame becomes a localized failure', () async {
      S2ArmInternalService.availabilityForTesting = const S2ArmRuntimeAvailability(S2ArmRuntimeState.ready);
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'detectExport') return {'success': true, 'exportDir': '/export'};
        if (call.method == 'prepareGame') return {'success': true, 'gid': 'g', 'imagesPath': '/i', 'moduleDir': '/m', 'gameData': '/g', 'docs': '/d'};
        if (call.method == 'launchGame') throw PlatformException(code: 'engineRestartRequired', message: 'restart');
        return null;
      });
      final outcome = await S2ArmInternalService.launch('/export', pairingFilePath: '/pair');
      expect(outcome.success, isFalse);
      expect(S2ArmEngineLocale.text(en, S2ArmInternalService.messageKey(outcome.error)), S2ArmEngineLocale.text(en, 'restartRequired'));
    });
  });

  group('settings and launch arguments', () {
    const locales = ['en', 'fr', 'es', 'de', 'it', 'pt', 'ru', 'id', 'ja', 'ko', 'zh', 'zh_Hant'];

    test('the defaults are the documented ones', () {
      expect(S2ArmSettings.defaults.toMap(), {
        'resolutionScale': '1',
        'antiAliasing': 'None',
        'scalingFilter': 'Bilinear',
        'frameRateLimit': '0',
        'docked': false,
        'widescreen': true,
        'performanceOverlay': false,
        'gameLanguage': 'auto',
      });
      expect(S2ArmSettings.fromMap(const {}), S2ArmSettings.defaults);
      expect(S2ArmSettings.fromMap(const {'antiAliasing': 'Bogus', 'docked': 'yes'}), S2ArmSettings.defaults);
    });

    test('getSettings and setSettings round trip through the channel', () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      var stored = S2ArmSettings.defaults.toMap();
      Object? received;
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'getSettings') return stored;
        if (call.method == 'setSettings') {
          received = call.arguments;
          stored = {...stored, ...Map<String, Object?>.from(call.arguments as Map)};
          return stored;
        }
        return null;
      });
      final loaded = await S2ArmInternalService.loadSettings();
      expect(loaded, S2ArmSettings.defaults);
      final changed = loaded!.copyWith(resolutionScale: '0.5', frameRateLimit: '60', docked: true, gameLanguage: 'French');
      final saved = await S2ArmInternalService.saveSettings(changed);
      expect(received, changed.toMap());
      expect(saved, changed);
      expect(await S2ArmInternalService.loadSettings(), changed);
    });

    test('loadSettings is null off iOS and when the channel fails', () async {
      expect(await S2ArmInternalService.loadSettings(), isNull);
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      messenger.setMockMethodCallHandler(channel, (call) async => throw PlatformException(code: 'x'));
      expect(await S2ArmInternalService.loadSettings(), isNull);
      expect(await S2ArmInternalService.saveSettings(S2ArmSettings.defaults), isNull);
    });

    test('launchGame receives uiLocale and the resolved menu strings', () async {
      S2ArmInternalService.availabilityForTesting = const S2ArmRuntimeAvailability(S2ArmRuntimeState.ready);
      Map<Object?, Object?>? arguments;
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'detectExport') return {'success': true, 'exportDir': '/export'};
        if (call.method == 'prepareGame') return {'success': true, 'gid': 'g', 'imagesPath': '/i', 'moduleDir': '/m', 'gameData': '/g', 'docs': '/d'};
        if (call.method == 'launchGame') {
          arguments = call.arguments as Map<Object?, Object?>;
          return {'success': true};
        }
        return null;
      });
      final outcome = await S2ArmInternalService.launch('/export', pairingFilePath: '/pair');
      S2ArmInternalService.sessionRunningForTesting = false;
      expect(outcome.success, isTrue);
      final uiLocale = arguments!['uiLocale'] as String;
      expect(locales, contains(uiLocale));
      final strings = Map<String, String>.from(arguments!['menuStrings'] as Map);
      expect(strings['menu.quit'], Switch2SettingsLocale.menuStrings(uiLocale)['menu.quit']);
      expect(strings['menu.quit'], isNotEmpty);
      expect(strings.keys, contains('lang.French'));
    });
  });

  group('engine-absent wording', () {
    test('a build without the engine says it is not included, in every locale', () {
      for (final code in S2ArmEngineLocale.values.keys) {
        final locale = Locale(code == 'zh_Hant' ? 'zh' : code, code == 'zh_Hant' ? 'TW' : null);
        for (final key in ['engineChainMissing', 'systemDataMissing']) {
          final text = S2ArmEngineLocale.text(locale, key);
          expect(text.toLowerCase(), isNot(contains('reinstall')), reason: '$code $key');
          expect(text.toLowerCase(), isNot(contains('réinstall')), reason: '$code $key');
        }
      }
      expect(S2ArmEngineLocale.text(en, 'engineChainMissing'),
          'The Switch 2 engine (S2Arm) is not included in this version of RewindBox.');
    });
  });

  group('delete', () {
    late Directory temp;
    late Directory library;
    const gid = '0100ABCDEF000000';
    setUp(() async {
      temp = await Directory.systemTemp.createTemp('s2arm-delete-');
      library = await Directory('${temp.path}/Library').create();
      S2ArmInternalService.documentsDirectory = () async => Directory('${temp.path}/Documents');
      S2ArmInternalService.libraryDirectory = () async => library;
      S2ArmInternalService.sessionRunningForTesting = false;
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'detectExport') return {'success': true, 'exportDir': call.arguments['exportFolder'], 'gid': gid};
        return null;
      });
    });
    tearDown(() async {
      S2ArmInternalService.sessionRunningForTesting = false;
      S2ArmInternalService.documentsDirectory = getApplicationDocumentsDirectory;
      S2ArmInternalService.libraryDirectory = getLibraryDirectory;
      if (await temp.exists()) await temp.delete(recursive: true);
    });

    Future<String> makeExport(String parent, String name) async {
      final exefs = await Directory('$parent/$name/base/exefs').create(recursive: true);
      final npdm = File('${exefs.path}/main.npdm');
      await npdm.writeAsBytes(const [1]);
      return npdm.path;
    }

    Future<void> makePrepared() async {
      await Directory('${library.path}/S2Arm/$gid/docs').create(recursive: true);
      await File('${library.path}/S2Arm/$gid/docs/save.bin').writeAsBytes(const [9]);
      await Directory('${library.path}/S2Arm/$gid/module').create(recursive: true);
      await File('${library.path}/S2Arm/$gid/module/image.dylib').writeAsBytes(const [8]);
      await File('${library.path}/S2Arm/$gid/pack.bin').writeAsBytes(const [7]);
    }

    test('an export inside Documents/S2Arm/Games is deleted; prepared data goes, saves stay', () async {
      final npdm = await makeExport('${temp.path}/Documents/S2Arm/Games', 'Test Game');
      await makePrepared();
      expect(await S2ArmInternalService.isInsideGames(npdm), isTrue);
      expect(await S2ArmInternalService.deleteGame(npdm), isTrue);
      expect(await Directory('${temp.path}/Documents/S2Arm/Games/Test Game').exists(), isFalse);
      expect(await File('${library.path}/S2Arm/$gid/docs/save.bin').exists(), isTrue);
      expect(await Directory('${library.path}/S2Arm/$gid/module').exists(), isFalse);
      expect(await File('${library.path}/S2Arm/$gid/pack.bin').exists(), isFalse);
    });

    test('a linked export outside the Games folder is left on disk', () async {
      final npdm = await makeExport('${temp.path}/Linked', 'Other Game');
      await makePrepared();
      expect(await S2ArmInternalService.isInsideGames(npdm), isFalse);
      expect(await S2ArmInternalService.deleteGame(npdm), isFalse);
      expect(await File(npdm).exists(), isTrue);
      expect(await File('${library.path}/S2Arm/$gid/pack.bin').exists(), isFalse);
      expect(await File('${library.path}/S2Arm/$gid/docs/save.bin').exists(), isTrue);
    });

    test('a sibling folder named like Games is not inside it', () async {
      final npdm = await makeExport('${temp.path}/Documents/S2Arm/Games-copy', 'Game');
      expect(await S2ArmInternalService.isInsideGames(npdm), isFalse);
    });

    test('a running or preparing game refuses the deletion and nothing is deleted', () async {
      final npdm = await makeExport('${temp.path}/Documents/S2Arm/Games', 'Busy Game');
      await makePrepared();
      S2ArmInternalService.sessionRunningForTesting = true;
      expect(S2ArmInternalService.busy, isTrue);
      await expectLater(
        S2ArmInternalService.deleteGame(npdm),
        throwsA(isA<S2ArmDeleteException>().having((e) => e.code, 'code', 'deleteBusy')),
      );
      expect(await File(npdm).exists(), isTrue);
      expect(await File('${library.path}/S2Arm/$gid/pack.bin').exists(), isTrue);
    });

    test('an export the engine does not recognise is still deleted, with no prepared data touched', () async {
      messenger.setMockMethodCallHandler(channel, (call) async => {'success': false, 'code': 'exportInvalid'});
      final npdm = await makeExport('${temp.path}/Documents/S2Arm/Games', 'Odd Game');
      await makePrepared();
      expect(await S2ArmInternalService.deleteGame(npdm), isTrue);
      expect(await File('${library.path}/S2Arm/$gid/pack.bin').exists(), isTrue);
    });
  });

  group('saves', () {
    late Directory temp;
    const gid = '0100ABCDEF000000';
    setUp(() async {
      temp = await Directory.systemTemp.createTemp('s2arm-saves-');
      S2ArmInternalService.documentsDirectory = () async => Directory('${temp.path}/Documents');
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'detectExport') {
          final folder = (call.arguments as Map)['exportFolder'] as String;
          if (folder.endsWith('not-a-game')) return {'success': false, 'code': 'notExportFolder'};
          return {'success': true, 'exportDir': folder, 'gid': gid, 'programId': gid.toLowerCase()};
        }
        if (call.method == 'gameInfo') return {'success': true, 'title': 'Test: Game', 'titleId': gid.toLowerCase()};
        return null;
      });
    });
    tearDown(() async {
      S2ArmInternalService.documentsDirectory = getApplicationDocumentsDirectory;
      S2ArmInternalService.sessionRunningForTesting = false;
      if (await temp.exists()) await temp.delete(recursive: true);
    });

    Future<Directory> picked(String name, Map<String, int> files) async {
      final folder = await Directory('${temp.path}/picked/$name').create(recursive: true);
      for (final entry in files.entries) {
        final file = File('${folder.path}/${entry.key}');
        await file.parent.create(recursive: true);
        await file.writeAsBytes(List<int>.filled(entry.value, 1));
      }
      return folder;
    }

    test('each game has one save folder in Documents/S2Arm/Saves, found again by its title id', () async {
      final folder = await S2ArmInternalService.saveFolderFor('/export');
      expect(folder, isNotNull);
      expect(folder!.path, '${temp.path}/Documents/S2Arm/Saves/Test Game [$gid]');
      expect(await folder.exists(), isTrue);
      final renamed = await folder.rename('${temp.path}/Documents/S2Arm/Saves/My save [$gid]');
      expect((await S2ArmInternalService.saveFolderFor('/export'))!.path, renamed.path);
      expect(await S2ArmInternalService.saveFolderFor('/not-a-game'), isNull);
    });

    test('an imported save is copied as picked; the previous one is kept as a backup', () async {
      final first = await picked('JKSV', {'Test Game/User - 2026.11.12 @ 10.00.00/save.bin': 64});
      final result = await S2ArmInternalService.importSaveAt('/export', first.path);
      expect(result.files, 1);
      expect(result.backup, isNull);
      expect(await File('${result.folder}/JKSV/Test Game/User - 2026.11.12 @ 10.00.00/save.bin').length(), 64);
      final second = await picked('0x0100abcdef000000 Test Game', {'2026-11-12/save.bin': 32, '2026-11-12/extra.bin': 8});
      final again = await S2ArmInternalService.importSaveAt('/export', second.path);
      expect(again.files, 2);
      expect(again.backup, '${result.folder} (backup)');
      expect(await File('${again.backup}/JKSV/Test Game/User - 2026.11.12 @ 10.00.00/save.bin').exists(), isTrue);
      expect(await Directory('${again.folder}/JKSV').exists(), isFalse, reason: 'the folder holds only the new save');
      expect(await File('${again.folder}/0x0100abcdef000000 Test Game/2026-11-12/save.bin').length(), 32);
    });

    test('an empty folder, the saves folder itself and a non-export are refused, nothing changes', () async {
      final empty = await Directory('${temp.path}/picked/empty').create(recursive: true);
      await expectLater(S2ArmInternalService.importSaveAt('/export', empty.path),
          throwsA(isA<S2ArmSaveException>().having((e) => e.code, 'code', 'saveEmpty')));
      final target = (await S2ArmInternalService.saveFolderFor('/export'))!;
      await File('${target.path}/kept.bin').writeAsBytes([1, 2, 3]);
      await expectLater(S2ArmInternalService.importSaveAt('/export', target.path),
          throwsA(isA<S2ArmSaveException>().having((e) => e.code, 'code', 'saveSameFolder')));
      await expectLater(S2ArmInternalService.importSaveAt('/export', (await S2ArmInternalService.savesDirectory()).path),
          throwsA(isA<S2ArmSaveException>().having((e) => e.code, 'code', 'saveSameFolder')));
      final save = await picked('save', {'a.bin': 4});
      await expectLater(S2ArmInternalService.importSaveAt('/not-a-game', save.path),
          throwsA(isA<S2ArmSaveException>().having((e) => e.code, 'code', 'saveNotExport')));
      expect(await File('${target.path}/kept.bin').readAsBytes(), [1, 2, 3]);
    });

    test('no import while a Switch 2 game runs', () async {
      S2ArmInternalService.sessionRunningForTesting = true;
      await expectLater(S2ArmInternalService.importSave('/export'),
          throwsA(isA<S2ArmSaveException>().having((e) => e.code, 'code', 'saveGameRunning')));
    });

    test('launchGame receives the game save folder', () async {
      S2ArmInternalService.availabilityForTesting = const S2ArmRuntimeAvailability(S2ArmRuntimeState.ready);
      Map<Object?, Object?>? arguments;
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'detectExport') return {'success': true, 'exportDir': '/export', 'gid': gid};
        if (call.method == 'gameInfo') return {'success': true, 'title': 'Test Game'};
        if (call.method == 'prepareGame') return {'success': true, 'gid': gid, 'imagesPath': '/i', 'moduleDir': '/m', 'gameData': '/g', 'docs': '/d'};
        if (call.method == 'launchGame') {
          arguments = call.arguments as Map<Object?, Object?>;
          return {'success': true};
        }
        return null;
      });
      final outcome = await S2ArmInternalService.launch('/export', pairingFilePath: '/pair');
      S2ArmInternalService.sessionRunningForTesting = false;
      expect(outcome.success, isTrue);
      expect(arguments!['saveFolder'], '${temp.path}/Documents/S2Arm/Saves/Test Game [$gid]');
    });

    test('every locale carries the save strings', () {
      for (final code in Switch2LibraryLocale.values.keys) {
        for (final key in const ['importSave', 'importSaveHint', 'openSaves', 'openSavesHint', 'openSavesFailed', 'saveImported',
            'saveImportedBackup', 'saveGameRunning', 'saveEmpty', 'saveSameFolder', 'saveNotExport', 'saveFailed']) {
          expect(Switch2LibraryLocale.values[code]![key], isNotEmpty, reason: '$code $key');
        }
      }
    });
  });
}
