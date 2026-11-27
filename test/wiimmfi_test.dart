import 'dart:io';
import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/wiimmfi_locale.dart';
import 'package:neostation/services/dolphin_internal_v2_service.dart';
import 'package:neostation/services/dolphin_system_files.dart';
import 'package:neostation/services/wiimmfi/wiimmfi_service.dart';
import 'package:neostation/services/wiimmfi/wiimmfi_store.dart';
import 'package:path/path.dart' as p;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('neostation/dolphin_internal');
  const paths = MethodChannel('plugins.flutter.io/path_provider');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late Directory root;
  late WiimmfiStore store;
  bool running = false;
  bool supported = true;
  bool cancelOnProtect = false;
  Future<int> Function(Map<dynamic, dynamic>)? nativeImport;
  List<Map<String, dynamic>>? picks;
  final calls = <String>[];

  Future<File> write(String relative, String data) async {
    final file = File(p.join(root.path, relative));
    await file.parent.create(recursive: true);
    return file.writeAsString(data, flush: true);
  }

  setUpAll(() async {
    root = await Directory.systemTemp.createTemp('wiimmfi-behavior-');
    messenger.setMockMethodCallHandler(paths, (_) async => root.path);
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call.method);
      if (call.method == 'wiimmfiImport') {
        return nativeImport!(call.arguments as Map);
      }
      if (call.method == 'wiimmfiCancelImport') return null;
      if (call.method == 'wiimmfiProtectNand') {
        if (cancelOnProtect) await WiimmfiService.cancelImport();
        return null;
      }
      return switch (call.method) {
        'isRunning' => running,
        'wiimmfiStatus' => {'supported': supported, 'nandRecognized': true},
        'saveIdentity' => {
          'system': 'wii',
          'gameId': 'RMCP01',
          'revision': 0,
          'region': 'EUR',
        },
        _ => throw PlatformException(code: 'unexpected_call'),
      };
    });
    messenger.setMockMethodCallHandler(
      const MethodChannel('miguelruivo.flutter.plugins.filepicker'),
      (_) async => picks,
    );
    await DolphinInternalV2Service.ensureLayout();
    store = WiimmfiStore(
      Directory(p.join(root.path, 'NeoStation/Dolphin/Metadata/Wiimmfi')),
    );
  });
  setUp(() async {
    calls.clear();
    running = false;
    supported = true;
    cancelOnProtect = false;
    nativeImport = null;
    picks = null;
    await store.clear();
  });
  tearDownAll(() async {
    await root.delete(recursive: true);
  });

  test(
    'default is disabled; disabled diagnostics and launch do not make service probes',
    () async {
      expect((await store.load())['enabled'], false);
      expect(await WiimmfiService.prepareLaunch('missing.iso'), false);
      await expectLater(
        WiimmfiService.diagnose(),
        throwsA(isA<WiimmfiException>()),
      );
      expect(calls, isEmpty);
    },
  );

  test(
    'settings persist, fail closed on corruption, and clear preserves NAND and games',
    () async {
      await write(
        'NeoStation/Dolphin/User/Wii/keys.bin',
        'synthetic non-secret fixture',
      );
      await WiimmfiService.setEnabled(true);
      expect((await store.load())['enabled'], true);
      await WiimmfiService.clear();
      expect((await store.load())['enabled'], false);
      expect(
        await File(
          p.join(root.path, 'NeoStation/Dolphin/User/Wii/keys.bin'),
        ).readAsString(),
        'synthetic non-secret fixture',
      );
      await write(
        'NeoStation/Dolphin/Metadata/Wiimmfi/settings.json',
        '{broken',
      );
      await expectLater(store.load(), throwsA(isA<WiimmfiException>()));
    },
  );

  test(
    'unsupported engine and active Wii/GC sessions refuse changes',
    () async {
      supported = false;
      await expectLater(
        WiimmfiService.setEnabled(true),
        throwsA(isA<WiimmfiException>()),
      );
      supported = true;
      running = true;
      await expectLater(
        WiimmfiService.setEnabled(true),
        throwsA(isA<DolphinSystemFilesException>()),
      );
      await expectLater(
        WiimmfiService.clear(),
        throwsA(isA<DolphinSystemFilesException>()),
      );
      running = false;
      await WiimmfiService.setEnabled(true);
      expect((await store.load())['enabled'], true);
    },
  );

  test(
    'exact native identity and hash bind declaration; changed image cannot launch online',
    () async {
      final image = await write(
        'NeoStation/Dolphin/Library/wii/synthetic.iso',
        'public test bytes, no game',
      );
      await WiimmfiService.registerPatchedImage(image.path);
      await WiimmfiService.setEnabled(true);
      expect(await WiimmfiService.prepareLaunch(image.path), true);
      expect(
        await WiimmfiService.prepareLaunch(image.path, requested: false),
        false,
      );
      await image.writeAsString('modified public test bytes');
      await expectLater(
        WiimmfiService.prepareLaunch(image.path),
        throwsA(isA<WiimmfiException>()),
      );
      // A different, undeclared game retains the ordinary offline launch route.
      expect(await WiimmfiService.prepareLaunch('undeclared.iso'), false);
    },
  );

  test(
    'transaction keeps current saves, imported identity and previous NAND',
    () async {
      final current = Directory(p.join(root.path, 'transaction/Wii'));
      const save = 'title/00010004/524d4350/data/save.bin';
      await write('transaction/Wii/$save', 'current profile');
      await write('transaction/Wii/keys.bin', 'old synthetic identity');
      await DolphinSystemFiles.replaceSnapshot(current, (stage) async {
        await Directory(
          p.join(stage.path, p.dirname(save)),
        ).create(recursive: true);
        await File(p.join(stage.path, save)).writeAsString('old console save');
        await File(
          p.join(stage.path, 'keys.bin'),
        ).writeAsString('new synthetic identity');
        await preserveWiiSaveData(current, stage);
        return 1;
      });
      expect(
        await File(p.join(current.path, save)).readAsString(),
        'current profile',
      );
      expect(
        await File(p.join(current.path, 'keys.bin')).readAsString(),
        'new synthetic identity',
      );
      expect(
        await File('${current.path}.previous/keys.bin').readAsString(),
        'old synthetic identity',
      );
      await expectLater(
        DolphinSystemFiles.replaceSnapshot(current, (stage) async {
          await File(p.join(stage.path, 'partial')).writeAsString('incomplete');
          throw const WiimmfiException('cancelled');
        }),
        throwsA(isA<WiimmfiException>()),
      );
      expect(
        await File(p.join(current.path, save)).readAsString(),
        'current profile',
      );
      expect(await Directory('${current.path}.incoming').exists(), false);
    },
  );

  test(
    'save-data links abort before replacement and preserve current files',
    () async {
      final current = Directory(p.join(root.path, 'linked/Wii'));
      await write('linked/Wii/title/00010004/524d4350/data/keep', 'keep');
      await Link(
        p.join(current.path, 'title/00010004/524d4350/data/escape'),
      ).create(root.path);
      await expectLater(
        DolphinSystemFiles.replaceSnapshot(current, (stage) async {
          await preserveWiiSaveData(current, stage);
          return 1;
        }),
        throwsA(isA<DolphinSystemFilesException>()),
      );
      expect(
        await File(
          p.join(current.path, 'title/00010004/524d4350/data/keep'),
        ).readAsString(),
        'keep',
      );
    },
  );

  test('error codes keep activation separate from patch and NAND errors', () {
    expect(WiimmfiLocale.errorKey('23899'), 'activation');
    expect(WiimmfiLocale.errorKey('23904'), 'patchOld');
    expect(WiimmfiLocale.errorKey('23918'), 'nandError');
    expect(WiimmfiLocale.errorKey('86420'), 'codeUnknown');
  });

  Future<File> selectSparseBackup() async {
    final file = await write('selected-nand.bin', '');
    final handle = await file.open(mode: FileMode.write);
    await handle.truncate(0x21000400);
    await handle.close();
    picks = [
      {'name': 'nand.bin', 'path': file.path, 'size': 0x21000400},
    ];
    return file;
  }

  test(
    'BootMii orchestration excludes launch and commits after save preservation',
    () async {
      final source = await selectSparseBackup();
      final live = await DolphinInternalV2Service.rootDirectory();
      const save = 'User/Wii/title/00010004/524d4350/data/profile';
      await write('NeoStation/Dolphin/$save', 'current racing profile');
      final entered = Completer<void>();
      final release = Completer<void>();
      nativeImport = (args) async {
        entered.complete();
        await release.future;
        final stage = args['stageDirectory'] as String;
        await File(
          p.join(stage, 'keys.bin'),
        ).writeAsString('mock extracted identity');
        return 0;
      };
      final importing = WiimmfiService.importBootMii();
      await entered.future;
      await expectLater(
        DolphinInternalV2Service.launchWiiMenu(),
        throwsA(isA<DolphinSystemFilesException>()),
      );
      release.complete();
      expect(await importing, true);
      expect(
        await File(p.join(live.path, save)).readAsString(),
        'current racing profile',
      );
      expect(await source.length(), 0x21000400);
      expect(WiimmfiService.importPhase.value, 'idle');
    },
  );

  test(
    'cancellation after native extraction rolls back before commit',
    () async {
      await selectSparseBackup();
      final live = await DolphinInternalV2Service.rootDirectory();
      final keys = File(p.join(live.path, 'User/Wii/keys.bin'));
      await keys.writeAsString('identity to preserve');
      nativeImport = (args) async {
        await File(
          p.join(args['stageDirectory'] as String, 'keys.bin'),
        ).writeAsString('incomplete replacement');
        return 0;
      };
      cancelOnProtect = true;
      await expectLater(
        WiimmfiService.importBootMii(),
        throwsA(isA<WiimmfiException>()),
      );
      expect(await keys.readAsString(), 'identity to preserve');
      expect(
        await Directory(p.join(live.path, 'User/Wii.incoming')).exists(),
        false,
      );
      expect(calls, contains('wiimmfiCancelImport'));
    },
  );

  test('twelve locales retain labels and Traditional Chinese routing', () {
    final english = WiimmfiLocale.labels(const Locale('en'));
    for (final language in [
      'fr',
      'de',
      'es',
      'it',
      'pt',
      'ru',
      'id',
      'ja',
      'ko',
      'zh',
    ]) {
      expect(
        WiimmfiLocale.labels(Locale(language)).keys.toSet(),
        english.keys.toSet(),
      );
      expect(
        WiimmfiLocale.labels(Locale(language))['enabled'],
        isNot(english['enabled']),
      );
    }
    expect(
      WiimmfiLocale.labels(
        const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      )['enabled'],
      '啟用 Wiimmfi',
    );
    expect(
      WiimmfiLocale.labels(const Locale('zh', 'TW'))['enabled'],
      '啟用 Wiimmfi',
    );
  });
}
